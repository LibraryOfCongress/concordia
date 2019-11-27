from django.contrib import admin
from django.urls import path


class ConcordiaAdminSite(admin.AdminSite):
    site_header = "Concordia Admin"
    site_title = "Concordia"
    login_template = "admin/auth/admin_login.html"

    def get_urls(self):
        from concordia.admin.views import admin_bulk_import_view, admin_site_report_view

        urls = super().get_urls()

        custom_urls = [
            path("bulk-import/", admin_bulk_import_view, name="bulk-import"),
            path("site-report/", admin_site_report_view, name="site-report"),
        ]

        return custom_urls + urls
