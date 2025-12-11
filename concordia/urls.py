from django.conf import settings
from django.contrib import admin
from django.http import Http404, HttpResponseForbidden
from django.urls import include, path
from django.urls.converters import register_converter
from django.views.defaults import page_not_found, permission_denied, server_error
from django.views.generic import RedirectView

from exporter import views as exporter_views
from prometheus_metrics.views import MetricsView

from . import converters, views

register_converter(converters.UnicodeSlugConverter, "uslug")
register_converter(converters.ItemIdConverter, "item_id")

tx_urlpatterns = (
    [
        path("", views.campaigns.CampaignListView.as_view(), name="campaign-list"),
        path(
            "completed/",
            views.campaigns.CompletedCampaignListView.as_view(),
            name="completed-campaign-list",
        ),
        path(
            "<uslug:slug>/reviewable/",
            views.campaigns.FilteredCampaignDetailView.as_view(),
            name="filtered-campaign-detail",
        ),
        path(
            "<uslug:slug>/",
            views.campaigns.CampaignDetailView.as_view(),
            name="campaign-detail",
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
            views.campaigns.ReportCampaignView.as_view(),
            name="campaign-report",
        ),
        path(
            "<uslug:campaign_slug>/<uslug:project_slug>/<item_id:item_id>/reviewable/",
            views.items.FilteredItemDetailView.as_view(),
            name="filtered-item-detail",
        ),
        path(
            (
                "<uslug:campaign_slug>/<uslug:project_slug>/"
                "<item_id:item_id>/<uslug:slug>/"
            ),
            views.assets.AssetDetailView.as_view(),
            name="asset-detail",
        ),
        # n.b. this must be above project-detail to avoid being seen as a project slug:
        path(
            "<uslug:campaign_slug>/next-transcribable-asset/",
            views.assets.redirect_to_next_transcribable_campaign_asset,
            name="redirect-to-next-transcribable-campaign-asset",
        ),
        path(
            "<uslug:campaign_slug>/next-reviewable-asset/",
            views.assets.redirect_to_next_reviewable_campaign_asset,
            name="redirect-to-next-reviewable-campaign-asset",
        ),
        path(
            "<uslug:campaign_slug>/<uslug:slug>/reviewable/",
            views.projects.FilteredProjectDetailView.as_view(),
            name="filtered-project-detail",
        ),
        path(
            "<uslug:campaign_slug>/<uslug:slug>/",
            views.projects.ProjectDetailView.as_view(),
            name="project-detail",
        ),
        path(
            "<uslug:campaign_slug>/<uslug:project_slug>/<item_id:item_id>/",
            views.items.ItemDetailView.as_view(),
            name="item-detail",
        ),
    ],
    "transcriptions",
)

urlpatterns = [
    path("", views.HomeView.as_view(), name="homepage"),
    path("healthz", views.healthz, name="health-check"),
    path("letter", views.accounts.account_letter, name="user-letter"),
    path("about/", views.simple_pages.about_simple_page, name="about"),
    # These patterns are to make sure various links to help-center URLs don't break
    # when the URLs are changed to not include help-center and can be removed after
    # all links are updated.
    path(
        "help-center/",
        RedirectView.as_view(pattern_name="welcome-guide"),
        name="help-center",
    ),
    path(
        "help-center/welcome-guide/", RedirectView.as_view(pattern_name="welcome-guide")
    ),
    path(
        "help-center/welcome-guide-esp/",
        RedirectView.as_view(pattern_name="welcome-guide-spanish"),
    ),
    path(
        "help-center/<slug:page_slug>-esp/",
        views.simple_pages.HelpCenterSpanishRedirectView.as_view(),
    ),
    path(
        "help-center/<slug:page_slug>/",
        views.simple_pages.HelpCenterRedirectView.as_view(),
    ),
    # End of help-center patterns
    path("get-started/", views.simple_pages.simple_page, name="welcome-guide"),
    path(
        "get-started/how-to-transcribe/",
        views.simple_pages.simple_page,
        name="transcription-basic-rules",
    ),
    path(
        "get-started/how-to-review/",
        views.simple_pages.simple_page,
        name="how-to-review",
    ),
    path("get-started/how-to-tag/", views.simple_pages.simple_page, name="how-to-tag"),
    path(
        "get-started/<uslug:slug>/", views.simple_pages.simple_page, name="simple-page"
    ),
    path(
        "get-started-esp/",
        views.simple_pages.simple_page,
        name="welcome-guide-spanish",
    ),
    path(
        "get-started-esp/how-to-transcribe-esp/",
        views.simple_pages.simple_page,
        name="how-to-transcribe-spanish",
    ),
    path(
        "get-started-esp/how-to-review-esp/",
        views.simple_pages.simple_page,
        name="how-to-review-spanish",
    ),
    path(
        "get-started-esp/how-to-tag-esp/",
        views.simple_pages.simple_page,
        name="how-to-tag-spanish",
    ),
    path(
        "get-started-esp/<uslug:slug>/",
        views.simple_pages.simple_page,
        name="simple-page-spanish",
    ),
    path("for-educators/", views.simple_pages.simple_page, name="for-educators"),
    path("for-staff/", views.simple_pages.simple_page, name="for-staff"),
    path("resources/", views.simple_pages.simple_page, name="resources"),
    path("service/", views.simple_pages.simple_page, name="service"),
    path(
        "latest/",
        RedirectView.as_view(pattern_name="about", permanent=True, query_string=True),
    ),
    path("questions/", views.simple_pages.simple_page, name="questions"),
    path(
        "contact/",
        RedirectView.as_view(url="https://ask.loc.gov/crowd"),
        name="contact",
    ),
    path(
        "help-center/",
        RedirectView.as_view(pattern_name="welcome-guide"),
        name="help-center",
    ),
    path(
        "campaigns-topics/",
        views.campaigns.CampaignTopicListView.as_view(),
        name="campaign-topic-list",
    ),
    path(
        "topics/<uslug:slug>/",
        views.topics.TopicDetailView.as_view(),
        name="topic-detail",
    ),
    path(
        "topics/<uslug:topic_slug>/next-transcribable-asset/",
        views.assets.redirect_to_next_transcribable_topic_asset,
        name="redirect-to-next-transcribable-topic-asset",
    ),
    path(
        "topics/<uslug:topic_slug>/next-reviewable-asset/",
        views.assets.redirect_to_next_reviewable_topic_asset,
        name="redirect-to-next-reviewable-topic-asset",
    ),
    path(
        "next-transcribable-asset/",
        views.assets.redirect_to_next_transcribable_asset,
        name="redirect-to-next-transcribable-asset",
    ),
    path(
        "next-reviewable-asset/",
        views.assets.redirect_to_next_reviewable_asset,
        name="redirect-to-next-reviewable-asset",
    ),
    path("campaigns/", include(tx_urlpatterns, namespace="transcriptions")),
    path(
        "reserve-asset/<int:asset_pk>/", views.ajax.reserve_asset, name="reserve-asset"
    ),
    path(
        "assets/<int:asset_pk>/transcriptions/save/",
        views.ajax.save_transcription,
        name="save-transcription",
    ),
    path(
        "transcriptions/<int:pk>/submit/",
        views.ajax.submit_transcription,
        name="submit-transcription",
    ),
    path(
        "transcriptions/<int:pk>/review/",
        views.ajax.review_transcription,
        name="review-transcription",
    ),
    path(
        "assets/<int:asset_pk>/transcriptions/generate-ocr/",
        views.ajax.generate_ocr_transcription,
        name="generate-ocr-transcription",
    ),
    path(
        "assets/<int:asset_pk>/transcriptions/rollback/",
        views.ajax.rollback_transcription,
        name="rollback-transcription",
    ),
    path(
        "assets/<int:asset_pk>/transcriptions/rollforward/",
        views.ajax.rollforward_transcription,
        name="rollforward-transcription",
    ),
    path(
        "assets/<int:asset_pk>/tags/submit/", views.ajax.submit_tags, name="submit-tags"
    ),
    path(
        "account/ajax-status/",
        views.ajax.ajax_session_status,
        name="ajax-session-status",
    ),
    path("account/ajax-messages/", views.ajax.ajax_messages, name="ajax-messages"),
    path(
        "account/register/",
        views.accounts.ConcordiaRegistrationView.as_view(),
        name="registration_register",
    ),
    path(
        "account/login/",
        views.accounts.ConcordiaLoginView.as_view(),
        name="registration_login",
    ),
    path("account/get_pages/", views.accounts.get_pages, name="get_pages"),
    path(
        "account/profile/",
        views.accounts.AccountProfileView.as_view(),
        name="user-profile",
    ),
    path(
        "account/password_reset/",
        views.accounts.ConcordiaPasswordResetRequestView.as_view(),
        name="password_reset",
    ),
    path(
        "account/reset/<uidb64>/<token>/",
        views.accounts.ConcordiaPasswordResetConfirmView.as_view(),
        name="password_reset_confirm",
    ),
    path("account/", include("django_registration.backends.activation.urls")),
    path("account/", include("django.contrib.auth.urls")),
    path(
        "account/email_confirmation/<str:confirmation_key>/",
        views.accounts.EmailReconfirmationView.as_view(),
        name="email-reconfirmation",
    ),
    path(
        "account/delete/",
        views.accounts.AccountDeletionView.as_view(),
        name="account-deletion",
    ),
    path(
        ".well-known/change-password",  # https://wicg.github.io/change-password-url/
        RedirectView.as_view(pattern_name="password_change"),
    ),
    path("admin/", admin.site.urls),
    # Internal support assists:
    path("error/500/", server_error),
    path("error/404/", page_not_found, {"exception": Http404()}),
    path("error/429/", views.rate_limit.ratelimit_view),
    path("error/403/", permission_denied, {"exception": HttpResponseForbidden()}),
    path("tinymce/", include("tinymce.urls")),
    path("metrics", MetricsView.as_view(), name="prometheus-django-metrics"),
    path("robots.txt", include("robots.urls")),
    path(
        "maintenance-mode/off/",
        views.maintenance_mode.maintenance_mode_off,
        name="maintenance_mode_off",
    ),
    path(
        "maintenance-mode/on/",
        views.maintenance_mode.maintenance_mode_on,
        name="maintenance_mode_on",
    ),
    path(
        "maintenance-mode/frontend/available",
        views.maintenance_mode.maintenance_mode_frontend_available,
        name="maintenance_mode_frontend_available",
    ),
    path(
        "maintenance-mode/frontend/unavailable",
        views.maintenance_mode.maintenance_mode_frontend_unavailable,
        name="maintenance_mode_frontend_unavailable",
    ),
    path(
        "api/visualization/<slug:name>/",
        views.visualizations.VisualizationDataView.as_view(),
        name="visualization",
    ),
]

if settings.DEBUG:
    import debug_toolbar
    from django.conf.urls.static import static
    from django.views.generic import TemplateView

    from concordia.api import api as concordia_api

    urlpatterns = [path("__debug__/", include(debug_toolbar.urls))] + urlpatterns

    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

    urlpatterns += (
        path(
            "transcription/",
            TemplateView.as_view(template_name="transcriptions/transcription.html"),
            name="transcription",
        ),
        path("api/", concordia_api.urls, name="api"),
    )
