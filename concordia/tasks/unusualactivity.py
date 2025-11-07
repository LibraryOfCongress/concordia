import datetime
from logging import getLogger

from django.conf import settings
from django.contrib.sites.models import Site
from django.core.mail import EmailMultiAlternatives
from django.template import loader
from django.utils import timezone

from concordia.logging import ConcordiaLogger
from concordia.models import Transcription

from ..celery import app as celery_app

logger = getLogger(__name__)
structured_logger = ConcordiaLogger.get_logger(__name__)

ENV_MAPPING = {"development": "DEV", "test": "TEST", "staging": "STAGE"}


@celery_app.task(ignore_result=True)
def unusual_activity(ignore_env=False):
    """
    Locate pages that were improperly transcribed or reviewed.
    """
    # Don't bother running unless we're in the prod env
    if settings.CONCORDIA_ENVIRONMENT == "production" or ignore_env:
        site = Site.objects.get_current()
        display_time = timezone.localtime().strftime("%b %d %Y, %I:%M %p")
        ONE_DAY_AGO = timezone.now() - datetime.timedelta(days=1)
        title = "Unusual User Activity Report for " + display_time
        if ignore_env:
            title += " [%s]" % ENV_MAPPING[settings.CONCORDIA_ENVIRONMENT]
        context = {
            "title": title,
            "domain": "https://" + site.domain,
            "transcriptions": Transcription.objects.transcribe_incidents(ONE_DAY_AGO),
            "reviews": Transcription.objects.review_incidents(ONE_DAY_AGO),
        }

        text_body_template = loader.get_template("emails/unusual_activity.txt")
        text_body_message = text_body_template.render(context)

        html_body_template = loader.get_template("emails/unusual_activity.html")
        html_body_message = html_body_template.render(context)

        to_email = ["rsar@loc.gov"]
        if settings.DEFAULT_TO_EMAIL:
            to_email.append(settings.DEFAULT_TO_EMAIL)
        message = EmailMultiAlternatives(
            subject=context["title"],
            body=text_body_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=to_email,
            reply_to=[settings.DEFAULT_FROM_EMAIL],
        )
        message.attach_alternative(html_body_message, "text/html")
        message.send()
