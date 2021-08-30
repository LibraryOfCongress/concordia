from django.contrib import admin
from django.urls import path


class ConcordiaAdminSite(admin.AdminSite):
    site_header = "Concordia Admin"
    site_title = "Concordia"

    def get_urls(self):
        from concordia.admin.views import (
            admin_bulk_import_review,
            admin_bulk_import_view,
            admin_site_report_view,
            celery_task_review,
            redownload_images_view,
            process_bagit_view,
        )

        urls = super().get_urls()

        custom_urls = [
            path("bulk-import/", admin_bulk_import_view, name="bulk-import"),
            path("bulk-review/", admin_bulk_import_review, name="bulk-review"),
            path("celery-review/", celery_task_review, name="celery-review"),
            path("site-report/", admin_site_report_view, name="site-report"),
            path(
                "redownload-images/", redownload_images_view, name="redownload-images"
            ),
            path("process-bagit/", process_bagit_view, name="process-bagit"),
        ]

        return custom_urls + urls
