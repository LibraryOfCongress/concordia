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
the data will be dumped as an HTML table and will not be delivered as a download.

Originally from
https://github.com/LibraryOfCongress/django-tabular-export/blob/master/tabular_export/core.py
"""

import csv
import datetime
from functools import wraps
from itertools import chain
from urllib.parse import quote

import xlsxwriter
from django.conf import settings
from django.http import HttpResponse, StreamingHttpResponse
from django.utils.encoding import force_str


def get_field_names_from_queryset(qs):
    """
    Return a list of field names for a queryset, including extra and
    aggregate columns
    """

    # We'll set the queryset to include all fields including calculated
    # aggregates using the same names which a values() queryset would return:
    v_qs = qs.values()

    field_names = []
    field_names.extend(i.target.name for i in v_qs.query.select)
    field_names.extend(v_qs.query.extra_select.keys())
    field_names.extend(v_qs.query.annotation_select.keys())

    return field_names


def flatten_queryset(qs, field_names=None, extra_verbose_names=None):
    """Return a tuple of named column headers and a list of data values

    By default headers will use the keys from ``qs.values()`` and rows will use
    the more-efficient ``values_list()``.

    If a list of ``field_names`` are passed, only the included fields will
    be returned.

    An optional dictionary of ``extra_verbose_names`` may be passed to provide
    friendly names for fields and will override the field's ``verbose_name``
    attribute if present. This can be used to provide proper names for related
    lookups (e.g. `{"institution__title": "Institution"}`) or calculated values
    (`e.g. {"items__count": "Item Count"}`).
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


def convert_value_to_unicode(v):
    """Return the UTF-8 bytestring representation of the provided value

    date/datetime instances will be converted to ISO 8601 format
    None will be returned as an empty string
    """

    if v is None:
        return ""
    elif hasattr(v, "isoformat"):
        return v.isoformat()
    else:
        return force_str(v)


def set_content_disposition(f):
    """
    Ensure that an HttpResponse has the Content-Disposition header set using
    the input filename= kwarg
    """

    @wraps(f)
    def inner(filename, *args, **kwargs):
        response = f(filename, *args, **kwargs)
        # See RFC 5987 for the filename* spec:
        response["Content-Disposition"] = "attachment; filename*=UTF-8''%s" % quote(
            filename
        )
        return response

    return inner


def return_debug_reponse(f):
    """
    Returns a debugging-friendly HTML response when TABULAR_RESPONSE_DEBUG is set
    """

    @wraps(f)
    def inner(filename, *args, **kwargs):
        if not getattr(settings, "TABULAR_RESPONSE_DEBUG", False):
            return f(filename, *args, **kwargs)
        else:
            resp = export_to_debug_html_response(filename, *args, **kwargs)
            del resp["Content-Disposition"]  # Don't trigger a download
            return resp

    return inner


def export_to_debug_html_response(filename, headers, rows):
    """
    Returns a downloadable StreamingHttpResponse using an HTML payload for debugging
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
def export_to_excel_response(filename, headers, rows):
    """
    Returns a downloadable HttpResponse using an XLSX payload generated from
    headers and rows
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

    def write(self, value):
        return value


@return_debug_reponse
@set_content_disposition
def export_to_csv_response(filename, headers, rows):
    """
    Returns a downloadable StreamingHttpResponse using an CSV payload
    generated from headers and rows
    """
    pseudo_buffer = Echo()

    writer = csv.writer(pseudo_buffer)

    def row_generator():
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


def force_utf8_encoding(f):
    @wraps(f)
    def inner():
        for row in f():
            yield [i.encode("utf-8") for i in row]

    return inner
