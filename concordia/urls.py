from django.conf import settings
from django.conf.urls import url
from django.contrib import admin
from django.http import Http404, HttpResponseForbidden
from django.urls import include, path
from django.urls.converters import register_converter
from django.views.defaults import page_not_found, permission_denied, server_error
from django.views.generic import RedirectView

from exporter import views as exporter_views

from . import converters, views

register_converter(converters.UnicodeSlugConverter, "uslug")
register_converter(converters.ItemIdConverter, "item_id")

tx_urlpatterns = (
    [
        path("", views.CampaignListView.as_view(), name="campaign-list"),
        path(
            "<uslug:slug>/", views.CampaignDetailView.as_view(), name="campaign-detail"
        ),
        path(
            "<uslug:campaign_slug>/export/csv/",
            exporter_views.ExportCampaignToCSV.as_view(),
            name="campaign-export-csv",
        ),
        path(
            "<uslug:campaign_slug>/export/bagit/",
            exporter_views.ExportCampaignToBagIt.as_view(),
            name="campaign-export-bagit",
        ),
        path(
            "<uslug:campaign_slug>/<uslug:project_slug>/export/bagit/",
            exporter_views.ExportProjectToBagIt.as_view(),
            name="project-export-bagit",
        ),
        path(
            (
                "<uslug:campaign_slug>/<uslug:project_slug>/"
                "<item_id:item_id>/export/bagit/"
            ),
            exporter_views.ExportItemToBagIt.as_view(),
            name="item-export-bagit",
        ),
        path(
            "<uslug:campaign_slug>/report/",
            views.ReportCampaignView.as_view(),
            name="campaign-report",
        ),
        path(
            (
                "<uslug:campaign_slug>/<uslug:project_slug>/"
                "<item_id:item_id>/<uslug:slug>/"
            ),
            views.AssetDetailView.as_view(),
            name="asset-detail",
        ),
        # n.b. this must be above project-detail to avoid being seen as a project slug:
        path(
            "<uslug:campaign_slug>/next-transcribable-asset/",
            views.redirect_to_next_transcribable_asset,
            name="redirect-to-next-transcribable-asset",
        ),
        path(
            "<uslug:campaign_slug>/next-reviewable-asset/",
            views.redirect_to_next_reviewable_asset,
            name="redirect-to-next-reviewable-asset",
        ),
        path(
            "<uslug:campaign_slug>/<uslug:slug>/",
            views.ProjectDetailView.as_view(),
            name="project-detail",
        ),
        path(
            "<uslug:campaign_slug>/<uslug:project_slug>/<item_id:item_id>/",
            views.ItemDetailView.as_view(),
            name="item-detail",
        ),
    ],
    "transcriptions",
)

urlpatterns = [
    path("", views.HomeView.as_view(), name="homepage"),
    path("healthz", views.healthz, name="health-check"),
    path("about/", views.simple_page, name="about"),
    path("help-center/", views.simple_page, name="help-center"),
    path("help-center/welcome-guide/", views.simple_page, name="welcome-guide"),
    path("help-center/how-to-transcribe/", views.simple_page, name="how-to-transcribe"),
    path("help-center/how-to-review/", views.simple_page, name="how-to-review"),
    path("help-center/how-to-tag/", views.simple_page, name="how-to-tag"),
    path("for-educators/", views.simple_page, name="for-educators"),
    path("resources/", views.simple_page, name="resources"),
    path("tags/", views.AllTagsView.as_view(), name="all-tags"),
    path(
        "latest/",
        RedirectView.as_view(pattern_name="about", permanent=True, query_string=True),
    ),
    path("questions/", views.simple_page, name="questions"),
    path("contact/", views.ContactUsView.as_view(), name="contact"),
    path("act/", views.action_app, name="action-app"),
    path(
        "campaigns-topics/",
        views.CampaignTopicListView.as_view(),
        name="campaign-topic-list",
    ),
    path("topics/", views.TopicListView.as_view(), name="topic-list"),
    path("topics/<uslug:slug>/", views.TopicDetailView.as_view(), name="topic-detail"),
    path(
        "topics/<uslug:topic_slug>/next-transcribable-asset/",
        views.redirect_to_next_transcribable_topic_asset,
        name="redirect-to-next-transcribable-topic-asset",
    ),
    path(
        "topics/<uslug:topic_slug>/next-reviewable-asset/",
        views.redirect_to_next_reviewable_topic_asset,
        name="redirect-to-next-reviewable-topic-asset",
    ),
    path("campaigns/", include(tx_urlpatterns, namespace="transcriptions")),
    path("reserve-asset/<int:asset_pk>/", views.reserve_asset, name="reserve-asset"),
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
    path("assets/<int:asset_pk>/tags/submit/", views.submit_tags, name="submit-tags"),
    path("assets/", views.AssetListView.as_view(), name="asset-list"),
    path(
        "transcribe/", views.TranscribeListView.as_view(), name="transcribe-asset-list"
    ),
    path("review/", views.ReviewListView.as_view(), name="review-asset-list"),
    path("account/ajax-status/", views.ajax_session_status, name="ajax-session-status"),
    path("account/ajax-messages/", views.ajax_messages, name="ajax-messages"),
    path(
        "account/register/",
        views.ConcordiaRegistrationView.as_view(),
        name="registration_register",
    ),
    path(
        "account/login/", views.ConcordiaLoginView.as_view(), name="registration_login"
    ),
    path("account/profile/", views.AccountProfileView.as_view(), name="user-profile"),
    path("account/", include("django_registration.backends.activation.urls")),
    path("account/", include("django.contrib.auth.urls")),
    path(
        ".well-known/change-password",  # https://wicg.github.io/change-password-url/
        RedirectView.as_view(pattern_name="password_change"),
    ),
    path("captcha/ajax/", views.ajax_captcha, name="ajax-captcha"),
    path("captcha/", include("captcha.urls")),
    path("admin/", admin.site.urls),
    # Internal support assists:
    path("error/500/", server_error),
    path("error/404/", page_not_found, {"exception": Http404()}),
    path("error/429/", views.ratelimit_view),
    path("error/403/", permission_denied, {"exception": HttpResponseForbidden()}),
    url("", include("django_prometheus_metrics.urls")),
    path("robots.txt", include("robots.urls")),
]

if settings.DEBUG:
    import debug_toolbar
    from django.conf.urls.static import static

    urlpatterns = [path("__debug__/", include(debug_toolbar.urls))] + urlpatterns

    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
