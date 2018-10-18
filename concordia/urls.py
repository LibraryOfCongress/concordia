from django.conf import settings
from django.conf.urls import url
from django.contrib import admin
from django.http import Http404, HttpResponseForbidden
from django.urls import include, path
from django.views.defaults import page_not_found, permission_denied, server_error

from concordia.admin import admin_bulk_import_view
from exporter import views as exporter_views

from . import views, views_ws

for key, value in getattr(settings, "ADMIN_SITE", {}).items():
    setattr(admin.site, key, value)


tx_urlpatterns = (
    [
        path("", views.CampaignListView.as_view(), name="campaigns"),
        path("<slug:slug>/", views.CampaignDetailView.as_view(), name="campaign"),
        path(
            "exportCSV/<slug:campaign_slug>/",
            exporter_views.ExportCampaignToCSV.as_view(),
            name="export-csv",
        ),
        path(
            "exportBagIt/<slug:campaign_slug>/",
            exporter_views.ExportCampaignToBagit.as_view(),
            name="export-bagit",
        ),
        path(
            "<slug:campaign_slug>/report/",
            views.ReportCampaignView.as_view(),
            name="campaign-report",
        ),
        path(
            "<slug:campaign_slug>/<slug:project_slug>/<slug:item_id>/<slug:slug>/",
            views.AssetDetailView.as_view(),
            name="asset-detail",
        ),
        path(
            "<slug:campaign_slug>/<slug:slug>/",
            views.ConcordiaProjectView.as_view(),
            name="project-detail",
        ),
        path(
            "<slug:campaign_slug>/<slug:project_slug>/next-transcribable-asset/",
            views.redirect_to_next_transcribable_asset,
            name="redirect-to-next-transcribable-asset",
        ),
        path(
            "<slug:campaign_slug>/<slug:project_slug>/<slug:item_id>/",
            views.ItemDetailView.as_view(),
            name="item-detail",
        ),
    ],
    "transcriptions",
)

urlpatterns = [
    path("", views.HomeView.as_view(), name="homepage"),
    path("healthz", views.healthz, name="health-check"),
    path("about/", views.static_page, name="about"),
    path("help-center/", views.static_page, name="help-center"),
    path("help-center/welcome-guide/", views.static_page, name="welcome-guide"),
    path("help-center/how-to-transcribe/", views.static_page, name="how-to-transcribe"),
    path("help-center/how-to-review/", views.static_page, name="how-to-review"),
    path("help-center/how-to-tag/", views.static_page, name="how-to-tag"),
    path("for-educators/", views.static_page, name="for-educators"),
    path("latest/", views.static_page, name="latest"),
    path("contact/", views.ContactUsView.as_view(), name="contact"),
    path("campaigns/", include(tx_urlpatterns, namespace="transcriptions")),
    path(
        "reserve-asset-for-transcription/<int:asset_pk>/",
        views.reserve_asset_transcription,
        name="reserve-asset-for-transcription",
    ),
    path(
        "assets/<int:asset_pk>/transcriptions/save/",
        views.save_transcription,
        name="save-transcription",
    ),
    path(
        "transcriptions/<int:pk>/submit/",
        views.submit_transcription,
        name="submit-transcription",
    ),
    path(
        "transcriptions/<int:pk>/review/",
        views.review_transcription,
        name="review-transcription",
    ),
    path(
        "assets/<int:asset_pk>/tags/",
        views_ws.UserAssetTagsGet().as_view(),
        name="get-tags",
    ),
    path(
        "assets/<int:asset_pk>/tags/submit/",
        views_ws.TagCreate.as_view(),
        name="submit-tags",
    ),
    path("account/ajax-status/", views.ajax_session_status, name="ajax-session-status"),
    path(
        "account/register/",
        views.ConcordiaRegistrationView.as_view(),
        name="registration_register",
    ),
    path("account/profile/", views.AccountProfileView.as_view(), name="user-profile"),
    path("account/", include("django_registration.backends.activation.urls")),
    path("account/", include("django.contrib.auth.urls")),
    path("captcha/ajax/", views.ajax_captcha, name="ajax-captcha"),
    path("captcha/", include("captcha.urls")),
    # TODO: when we upgrade to Django 2.1 we can use the admin site override
    # mechanism (the old one is broken in 2.0): see
    # https://code.djangoproject.com/ticket/27887
    path("admin/bulk-import", admin_bulk_import_view, name="admin-bulk-import"),
    path("admin/", admin.site.urls),
    # Internal support assists:
    path("maintenance-mode/", include("maintenance_mode.urls")),
    path("error/500/", server_error),
    path("error/404/", page_not_found, {"exception": Http404()}),
    path("error/403/", permission_denied, {"exception": HttpResponseForbidden()}),
    url("", include("django_prometheus_metrics.urls")),
    path("robots.txt", include("robots.urls")),
]

if settings.DEBUG:
    import debug_toolbar
    from django.conf.urls.static import static

    urlpatterns = [path("__debug__/", include(debug_toolbar.urls))] + urlpatterns

    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
