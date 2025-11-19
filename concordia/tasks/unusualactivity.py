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
def unusual_activity(ignore_env: bool = False) -> None:
    """
    Send an email report about suspect transcription or review activity.

    By default this task runs only when ``CONCORDIA_ENVIRONMENT`` is
    set to ``"production"``. Setting ``ignore_env`` to true forces the
    report to be generated in other environments and adds an
    environment tag to the subject line.

    The report includes:

    * Transcriptions flagged by ``transcribe_incidents`` in the past day
    * Reviews flagged by ``review_incidents`` in the past day

    Both plain text and HTML versions of the report are rendered from
    templates and emailed to the monitoring recipients.

    Args:
        ignore_env: Generate and send the report even if the current
            environment is not production.

    Returns:
        None
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
