from datetime import UTC, datetime, timedelta
from unittest import mock

from django.test import TestCase, override_settings
from django.utils import timezone

from concordia.tasks.unusualactivity import unusual_activity


class UnusualActivityTaskTests(TestCase):
    @override_settings(CONCORDIA_ENVIRONMENT="development")
    def test_noop_when_not_production_and_not_ignored(self):
        # Should not render templates or send mail.
        with (
            mock.patch(
                "concordia.tasks.unusualactivity.loader.get_template"
            ) as m_get_tmpl,
            mock.patch(
                "concordia.tasks.unusualactivity.EmailMultiAlternatives"
            ) as m_email,
            mock.patch(
                "concordia.tasks.unusualactivity.Transcription.objects"
            ) as m_mgr,
        ):
            unusual_activity(ignore_env=False)

        m_get_tmpl.assert_not_called()
        m_email.assert_not_called()
        # Manager methods should not be called either.
        self.assertFalse(m_mgr.transcribe_incidents.called)
        self.assertFalse(m_mgr.review_incidents.called)

    @override_settings(
        CONCORDIA_ENVIRONMENT="production",
        DEFAULT_FROM_EMAIL="noreply@example.com",
        DEFAULT_TO_EMAIL="",
    )
    def test_runs_in_production_without_default_to(self):
        # Executes, builds subject without env suffix, and sends to one addr.
        fixed_now_dt = timezone.make_aware(datetime(2025, 1, 1, 12, 0), timezone=UTC)
        expected_one_day_ago = fixed_now_dt - timedelta(days=1)

        with (
            mock.patch(
                "concordia.tasks.unusualactivity.Site.objects.get_current"
            ) as m_site,
            mock.patch(
                "concordia.tasks.unusualactivity.timezone.localtime"
            ) as m_localtime,
            mock.patch(
                "concordia.tasks.unusualactivity.timezone.now",
                return_value=fixed_now_dt,
            ),
            mock.patch(
                "concordia.tasks.unusualactivity.loader.get_template"
            ) as m_get_tmpl,
            mock.patch(
                "concordia.tasks.unusualactivity.EmailMultiAlternatives"
            ) as m_email,
            mock.patch(
                "concordia.tasks.unusualactivity.Transcription.objects"
            ) as m_mgr,
        ):
            lt = mock.Mock()
            lt.strftime.return_value = "STAMP"
            m_localtime.return_value = lt

            m_site.return_value = mock.Mock(domain="example.com")

            txt_tmpl = mock.Mock()
            html_tmpl = mock.Mock()
            txt_tmpl.render.return_value = "TEXT"
            html_tmpl.render.return_value = "HTML"
            m_get_tmpl.side_effect = lambda name: (
                txt_tmpl if name.endswith(".txt") else html_tmpl
            )

            m_mgr.transcribe_incidents.return_value = []
            m_mgr.review_incidents.return_value = []

            msg = mock.Mock()
            m_email.return_value = msg

            unusual_activity(ignore_env=False)

        expected_subject = "Unusual User Activity Report for STAMP"
        args, kwargs = m_email.call_args
        self.assertEqual(kwargs["subject"], expected_subject)
        self.assertEqual(kwargs["from_email"], "noreply@example.com")
        self.assertEqual(kwargs["to"], ["rsar@loc.gov"])
        self.assertEqual(kwargs["reply_to"], ["noreply@example.com"])

        txt_tmpl.render.assert_called_once()
        html_tmpl.render.assert_called_once()
        self.assertEqual(
            m_mgr.transcribe_incidents.call_args[0][0], expected_one_day_ago
        )
        self.assertEqual(m_mgr.review_incidents.call_args[0][0], expected_one_day_ago)
        msg.attach_alternative.assert_called_once_with("HTML", "text/html")
        msg.send.assert_called_once()

    @override_settings(
        CONCORDIA_ENVIRONMENT="test",
        DEFAULT_FROM_EMAIL="notify@example.com",
        DEFAULT_TO_EMAIL="extra@example.com",
    )
    def test_ignore_env_appends_suffix_and_includes_default_to(self):
        fixed_now_dt = timezone.make_aware(datetime(2025, 1, 2, 9, 30), timezone=UTC)
        expected_one_day_ago = fixed_now_dt - timedelta(days=1)

        with (
            mock.patch(
                "concordia.tasks.unusualactivity.Site.objects.get_current"
            ) as m_site,
            mock.patch(
                "concordia.tasks.unusualactivity.timezone.localtime"
            ) as m_localtime,
            mock.patch(
                "concordia.tasks.unusualactivity.timezone.now",
                return_value=fixed_now_dt,
            ),
            mock.patch(
                "concordia.tasks.unusualactivity.loader.get_template"
            ) as m_get_tmpl,
            mock.patch(
                "concordia.tasks.unusualactivity.EmailMultiAlternatives"
            ) as m_email,
            mock.patch(
                "concordia.tasks.unusualactivity.Transcription.objects"
            ) as m_mgr,
        ):
            lt = mock.Mock()
            lt.strftime.return_value = "STAMP2"
            m_localtime.return_value = lt

            m_site.return_value = mock.Mock(domain="example.net")

            txt_tmpl = mock.Mock()
            html_tmpl = mock.Mock()
            txt_tmpl.render.return_value = "TEXT2"
            html_tmpl.render.return_value = "HTML2"
            m_get_tmpl.side_effect = lambda name: (
                txt_tmpl if name.endswith(".txt") else html_tmpl
            )

            m_mgr.transcribe_incidents.return_value = []
            m_mgr.review_incidents.return_value = []

            msg = mock.Mock()
            m_email.return_value = msg

            unusual_activity(ignore_env=True)

        expected_subject = "Unusual User Activity Report for STAMP2 [TEST]"
        args, kwargs = m_email.call_args
        self.assertEqual(kwargs["subject"], expected_subject)
        self.assertEqual(kwargs["to"], ["rsar@loc.gov", "extra@example.com"])
        self.assertEqual(kwargs["from_email"], "notify@example.com")
        self.assertEqual(kwargs["reply_to"], ["notify@example.com"])

        txt_tmpl.render.assert_called_once()
        html_tmpl.render.assert_called_once()
        self.assertEqual(
            m_mgr.transcribe_incidents.call_args[0][0], expected_one_day_ago
        )
        self.assertEqual(m_mgr.review_incidents.call_args[0][0], expected_one_day_ago)
        msg.attach_alternative.assert_called_once_with("HTML2", "text/html")
        msg.send.assert_called_once()
