# encoding: utf-8
"""
Helpers for exporting Django admin querysets as Excel or CSV files.

Usage in a ModelAdmin:

    actions = (export_to_excel_action, export_to_csv_action)

These actions take the current queryset and export it using the same field
selection you would get from `values()` by default. The download filename is
derived from the `ModelAdmin.model._meta.verbose_name_plural` unless a custom
filename is passed.

These helpers are adapted from the original django-tabular-export implementation:
https://github.com/LibraryOfCongress/django-tabular-export/blob/master/tabular_export/admin.py
"""

from functools import wraps
from typing import Any, Callable, Iterable

from django.contrib.admin import ModelAdmin
from django.db.models import QuerySet
from django.http import HttpRequest, HttpResponse
from django.utils.encoding import force_str as force_text
from django.utils.translation import gettext_lazy as _

from .core import (
    export_to_csv_response,
    export_to_excel_response,
    flatten_queryset,
)


def ensure_filename(suffix: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """
    Decorator factory to ensure a default filename for export admin actions.

    If the wrapped action is called with ``filename=None``, the filename is
    built from ``modeladmin.model._meta.verbose_name_plural`` plus the given
    suffix.

    Args:
        suffix (str): File extension to append (for example, ``"csv"`` or
            ``"xlsx"``).

    Returns:
        Callable[[Callable[..., Any]], Callable[..., Any]]: A decorator that
        wraps an admin action and injects a default filename when needed.
    """

    def outer(f: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(f)
        def inner(
            modeladmin: ModelAdmin,
            request: HttpRequest,
            queryset: QuerySet[Any],
            filename: str | None = None,
            *args: Any,
            **kwargs: Any,
        ) -> HttpResponse:
            if filename is None:
                filename = "%s.%s" % (
                    force_text(modeladmin.model._meta.verbose_name_plural),
                    suffix,
                )
            return f(
                modeladmin,
                request,
                queryset,
                *args,
                filename=filename,
                **kwargs,
            )

        return inner

    return outer


@ensure_filename("xlsx")
def export_to_excel_action(
    modeladmin: ModelAdmin,
    request: HttpRequest,
    queryset: QuerySet[Any],
    filename: str | None = None,
    field_names: Iterable[str] | None = None,
    extra_verbose_names: dict[str, str] | None = None,
) -> HttpResponse:
    """
    Django admin action that exports selected records as an Excel XLSX download.

    The queryset is first flattened via :func:`flatten_queryset`, optionally
    restricted to the provided ``field_names`` and ``extra_verbose_names``,
    then returned as an XLSX file response.

    Args:
        modeladmin (ModelAdmin): The Django admin class that owns this action.
        request (HttpRequest): The current admin request.
        queryset (QuerySet[Any]): The selected objects to export.
        filename (str | None): Optional download filename. When omitted, a
            name is generated from the model's ``verbose_name_plural`` and the
            ``"xlsx"`` suffix.
        field_names (Iterable[str] | None): Optional iterable of field names to
            include in the export. When omitted, the default flattening logic
            is used.
        extra_verbose_names (dict[str, str] | None): Optional mapping of field
            names to custom column headers.

    Returns:
        HttpResponse: A response containing the XLSX file.
    """
    headers, rows = flatten_queryset(
        queryset,
        field_names=field_names,
        extra_verbose_names=extra_verbose_names,
    )
    return export_to_excel_response(filename, headers, rows)


export_to_excel_action.short_description = _("Export to Excel")


@ensure_filename("csv")
def export_to_csv_action(
    modeladmin: ModelAdmin,
    request: HttpRequest,
    queryset: QuerySet[Any],
    filename: str | None = None,
    field_names: Iterable[str] | None = None,
    extra_verbose_names: dict[str, str] | None = None,
) -> HttpResponse:
    """
    Django admin action that exports selected records as a CSV download.

    The queryset is first flattened via :func:`flatten_queryset`, optionally
    restricted to the provided ``field_names`` and ``extra_verbose_names``,
    then returned as a CSV file response.

    Args:
        modeladmin (ModelAdmin): The Django admin class that owns this action.
        request (HttpRequest): The current admin request.
        queryset (QuerySet[Any]): The selected objects to export.
        filename (str | None): Optional download filename. When omitted, a
            name is generated from the model's ``verbose_name_plural`` and the
            ``"csv"`` suffix.
        field_names (Iterable[str] | None): Optional iterable of field names to
            include in the export. When omitted, the default flattening logic
            is used.
        extra_verbose_names (dict[str, str] | None): Optional mapping of field
            names to custom column headers.

    Returns:
        HttpResponse: A response containing the CSV file.
    """
    headers, rows = flatten_queryset(
        queryset,
        field_names=field_names,
        extra_verbose_names=extra_verbose_names,
    )
    return export_to_csv_response(filename, headers, rows)


export_to_csv_action.short_description = _("Export to CSV")
