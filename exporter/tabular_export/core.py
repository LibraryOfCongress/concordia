# encoding: utf-8
"""Exports to tabular (2D) formats

This module contains functions which take (headers, rows) pairs and return
HttpResponses with either XLSX or CSV downloads

The ``export_to_FORMAT_response`` functions accept a ``filename``, and
``headers`` and ``rows``. This allows full control over the data using
non-database data-sources, the Django ORM's various aggregations and
optimization methods, generators for large responses, control over the
column names, or post-processing using methods like ``get_FOO_display()``
to format the data for display.

The ``flatten_queryset`` utility used to generate lists from QuerySets
intentionally does not attempt to handle foreign-key fields to avoid
performance issues. If you need to include such data, prepare it in advance
using whatever optimizations are possible and pass the data in directly.

If your Django settings module sets ``TABULAR_RESPONSE_DEBUG`` to ``True``
the data will be dumped as an HTML table and will not be delivered as a
download.

Originally from
https://github.com/LibraryOfCongress/django-tabular-export/blob/master/tabular_export/core.py
"""

import csv
import datetime
from functools import wraps
from itertools import chain
from typing import Any, Callable, Iterable, Mapping, Sequence
from urllib.parse import quote

import xlsxwriter
from django.conf import settings
from django.db.models import QuerySet
from django.http import HttpResponse, StreamingHttpResponse
from django.utils.encoding import force_str

ResponseType = HttpResponse | StreamingHttpResponse


def get_field_names_from_queryset(qs: QuerySet[Any]) -> list[str]:
    """
    Derive field names from a queryset, including extra and aggregate columns.

    The queryset is first coerced to a ``values()`` queryset so that extra
    selects and annotations appear with the same names Django would use for
    ``values()`` results.

    Args:
        qs: QuerySet to introspect.

    Returns:
        List of field and annotation names in the order they will appear in
        ``qs.values()``.
    """

    # We'll set the queryset to include all fields including calculated
    # aggregates using the same names which a values() queryset would return:
    v_qs = qs.values()

    field_names: list[str] = []
    field_names.extend(i.target.name for i in v_qs.query.select)
    field_names.extend(v_qs.query.extra_select.keys())
    field_names.extend(v_qs.query.annotation_select.keys())

    return field_names


def flatten_queryset(
    qs: QuerySet[Any],
    field_names: Iterable[str] | None = None,
    extra_verbose_names: Mapping[str, str] | None = None,
) -> tuple[list[str], Iterable[Sequence[Any]]]:
    """
    Convert a queryset into headers and row tuples for tabular export.

    By default the column headers are derived from the queryset's field
    names (as returned by ``get_field_names_from_queryset``) and the rows
    use ``values_list()`` for efficient iteration.

    If ``field_names`` is provided, only those fields are included and they
    are used to order both headers and row values.

    The ``extra_verbose_names`` mapping can override the verbose names for
    specific fields, including related lookups or calculated values.

    Args:
        qs: Base queryset to flatten.
        field_names: Optional explicit list of field names to include.
        extra_verbose_names: Optional mapping of field names to friendly
            column labels. This can be used to provide proper names for
            related lookups (for example,
            ``{"institution__title": "Institution"}``) or calculated values
            (for example, ``{"items__count": "Item Count"}``).

    Returns:
        A 2-tuple of ``(headers, rows)`` where ``headers`` is a list of
        column labels and ``rows`` is an iterable of sequences of values.
    """

    if field_names is None:
        field_names = get_field_names_from_queryset(qs)

    # Headers will use the verbose names where available and fall back to the
    # field name if not (e.g. custom aggregate or extra fields):
    verbose_names = {i.name: i.verbose_name for i in qs.model._meta.fields}
    if extra_verbose_names is not None:
        verbose_names.update(extra_verbose_names)

    headers = [verbose_names.get(i, i) for i in field_names]

    return headers, qs.values_list(*field_names)


def convert_value_to_unicode(v: Any) -> str:
    """
    Convert a value to a display-safe string for tabular export.

    ``None`` is rendered as an empty string. ``date`` and ``datetime``
    instances are converted using ``isoformat()``. All other values are
    coerced via ``force_str``.

    Args:
        v: Value to convert.

    Returns:
        String representation suitable for CSV, HTML, or XLSX output.
    """

    if v is None:
        return ""
    elif hasattr(v, "isoformat"):
        return v.isoformat()
    else:
        return force_str(v)


def set_content_disposition(
    f: Callable[..., ResponseType],
) -> Callable[..., ResponseType]:
    """
    Decorator that applies a Content-Disposition header using the filename.

    The wrapped function must accept ``filename`` as its first positional
    argument and return an ``HttpResponse`` (or subclass). The decorator
    sets the ``Content-Disposition`` header using RFC 5987 encoding for the
    provided filename.

    Args:
        f: Callable that builds the HTTP response for a given filename.

    Returns:
        Wrapped callable that always sets ``Content-Disposition`` on the
        response.
    """

    @wraps(f)
    def inner(filename: str, *args: Any, **kwargs: Any) -> ResponseType:
        response = f(filename, *args, **kwargs)
        # See RFC 5987 for the filename* spec:
        response["Content-Disposition"] = "attachment; filename*=UTF-8''%s" % quote(
            filename
        )
        return response

    return inner


def return_debug_reponse(
    f: Callable[..., ResponseType],
) -> Callable[..., ResponseType]:
    """
    Decorator to swap export responses for an HTML debug table.

    When the ``TABULAR_RESPONSE_DEBUG`` setting is truthy, the wrapped
    function is not called. Instead ``export_to_debug_html_response`` is
    used and the ``Content-Disposition`` header is removed so the browser
    renders the table inline.

    Args:
        f: Export callable to wrap.

    Returns:
        Wrapped callable that either returns the original export response or
        an HTML debug response, depending on settings.
    """

    @wraps(f)
    def inner(filename: str, *args: Any, **kwargs: Any) -> ResponseType:
        if not getattr(settings, "TABULAR_RESPONSE_DEBUG", False):
            return f(filename, *args, **kwargs)
        else:
            resp = export_to_debug_html_response(filename, *args, **kwargs)
            del resp["Content-Disposition"]  # Don't trigger a download
            return resp

    return inner


def export_to_debug_html_response(
    filename: str,
    headers: Iterable[Any],
    rows: Iterable[Sequence[Any]],
) -> StreamingHttpResponse:
    """
    Build an HTML table response for inspection of tabular export data.

    This is used when ``TABULAR_RESPONSE_DEBUG`` is enabled. It renders the
    headers and rows into a simple Bootstrap-styled HTML table and returns a
    ``StreamingHttpResponse``.

    Args:
        filename: Suggested filename for the export (kept for API parity).
        headers: Iterable of header labels.
        rows: Iterable of row sequences.

    Returns:
        StreamingHttpResponse streaming the HTML document.
    """

    def output_generator():
        # Note the use of bytestrings to avoid unnecessary Unicode-bytes cycles:
        yield b"<!DOCTYPE html><html>"
        yield b'<head><meta charset="utf-8"><title>TABULAR DEBUG</title>'
        yield b'<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css">'  # noqa
        yield b"</head>"
        yield b'<body class="container-fluid"><div class="table-responsive"><table class="table table-striped">'  # noqa
        yield b"<thead><tr><th>"
        yield b"</th><th>".join(
            convert_value_to_unicode(i).encode("utf-8") for i in headers
        )
        yield b"</th></tr></thead>"

        yield b"<tbody>"
        for row in rows:
            values = map(convert_value_to_unicode, row)
            values = [i.encode("utf-8").replace(b"\n", b"<br>") for i in values]
            yield b"<tr><td>%s</td></tr>" % b"</td><td>".join(values)
        yield b"</tbody>"
        yield b"</table></div></body></html>"

    return StreamingHttpResponse(
        output_generator(), content_type="text/html; charset=UTF-8"
    )


@return_debug_reponse
@set_content_disposition
def export_to_excel_response(
    filename: str,
    headers: Iterable[Any],
    rows: Iterable[Sequence[Any]],
) -> HttpResponse:
    """
    Return an XLSX ``HttpResponse`` for the given headers and rows.

    The payload is constructed using ``xlsxwriter`` with a constant-memory
    workbook and a default ``yyyy-mm-dd`` date format. ``datetime`` and
    ``date`` values are written with Excel date formatting; all other values
    are coerced to strings.

    Args:
        filename: Download filename used in the ``Content-Disposition``
            header.
        headers: Iterable of header labels for the first row.
        rows: Iterable of row sequences.

    Returns:
        HttpResponse containing the XLSX file.
    """

    # See http://technet.microsoft.com/en-us/library/ee309278%28office.12%29.aspx
    content_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

    # This cannot be a StreamingHttpResponse because XLSX files are .zip format and
    # the Python ZipFile library doesn't offer a generator form (which would also
    # not be called per-row but per-chunk)

    resp = HttpResponse(content_type=content_type)

    workbook = xlsxwriter.Workbook(
        resp,
        {
            "constant_memory": True,
            "in_memory": True,
            "default_date_format": "yyyy-mm-dd",
        },
    )

    date_format = workbook.add_format({"num_format": "yyyy-mm-dd"})

    worksheet = workbook.add_worksheet()

    for y, row in enumerate(chain((headers,), rows)):
        for x, col in enumerate(row):
            if isinstance(col, datetime.datetime):
                # xlsxwriter cannot handle timezones:
                worksheet.write_datetime(y, x, col.replace(tzinfo=None), date_format)
            elif isinstance(col, datetime.date):
                worksheet.write_datetime(y, x, col, date_format)
            else:
                worksheet.write(y, x, force_str(col, strings_only=True))

    workbook.close()

    return resp


class Echo(object):
    # See
    # https://docs.djangoproject.com/en/1.8/howto/outputting-csv/#streaming-csv-files

    def write(self, value: str) -> str:
        return value


@return_debug_reponse
@set_content_disposition
def export_to_csv_response(
    filename: str,
    headers: Iterable[Any],
    rows: Iterable[Sequence[Any]],
) -> StreamingHttpResponse:
    """
    Return a CSV ``StreamingHttpResponse`` for the given headers and rows.

    Values are converted to strings via ``convert_value_to_unicode`` and
    written using the standard library ``csv`` module. The response streams
    each rendered row to avoid holding the entire CSV in memory.

    Args:
        filename: Download filename used in the ``Content-Disposition``
            header.
        headers: Iterable of header labels for the header row.
        rows: Iterable of row sequences.

    Returns:
        StreamingHttpResponse streaming the CSV content.
    """
    pseudo_buffer = Echo()

    writer = csv.writer(pseudo_buffer)

    def row_generator() -> Iterable[Iterable[str]]:
        yield map(convert_value_to_unicode, headers)

        for row in rows:
            yield map(convert_value_to_unicode, row)

    # This works because csv.writer.writerow calls the underlying
    # file-like .write method *and* returns the result. We cannot
    # use the same approach for Excel because xlsxwriter doesn't
    # have a way to emit chunks from ZipFile and StreamingHttpResponse
    # does not offer a file-like handle.

    return StreamingHttpResponse(
        (writer.writerow(row) for row in row_generator()),
        content_type="text/csv; charset=utf-8",
    )


def force_utf8_encoding(
    f: Callable[[], Iterable[Sequence[Any]]],
) -> Callable[[], Iterable[Sequence[bytes]]]:
    """
    Decorator that forces all values yielded by a row generator to UTF-8 bytes.

    The wrapped callable must return an iterable of row sequences. Each value
    in each row is encoded as UTF-8 bytes.

    Args:
        f: Callable returning an iterable of rows.

    Returns:
        Callable that yields rows with all values encoded as UTF-8 bytes.
    """

    @wraps(f)
    def inner() -> Iterable[Sequence[bytes]]:
        for row in f():
            yield [i.encode("utf-8") for i in row]

    return inner
