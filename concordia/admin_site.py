"""Admin site customizations for Concordia.

Provides a subclass of Django's ``AdminSite`` that adds project-specific
admin URLs alongside the default admin views.
"""

from django.contrib import admin
from django.urls import path


class ConcordiaAdminSite(admin.AdminSite):
    """Custom admin site with additional Concordia tools and views."""

    site_header = "Concordia Admin"
    site_title = "Concordia"

    def get_urls(self) -> list:
        """Return admin URL patterns including Concordia-specific routes.

        This extends ``admin.AdminSite.get_urls`` by prepending a set of
        project routes for bulk import, bulk review, Celery task review,
        site reporting, project-level export, JSON object inspection
        and the cache-clearing tool. The base admin URLs are returned
        unchanged after the custom routes.

        Returns:
            list: URL patterns for the custom admin views followed by the
            default admin URLs.
        """
        from concordia.admin import views

        urls = super().get_urls()

        custom_urls = [
            path("bulk-import/", views.admin_bulk_import_view, name="bulk-import"),
            path("bulk-review/", views.admin_bulk_import_review, name="bulk-review"),
            path("celery-review/", views.celery_task_review, name="celery-review"),
            path("site-report/", views.admin_site_report_view, name="site-report"),
            path(
                "retired-site-report/",
                views.admin_retired_site_report_view,
                name="retired-site-report",
            ),
            path(
                "project-level-export/",
                views.project_level_export,
                name="project-level-export",
            ),
            path(
                "serialized_object/",
                views.SerializedObjectView.as_view(),
                name="serialized_object",
            ),
            path("clear-cache/", views.ClearCacheView.as_view(), name="clear-cache"),
        ]

        return custom_urls + urls
