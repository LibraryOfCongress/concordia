from urllib.parse import urljoin

from django import template
from django.conf import settings

register = template.Library()


@register.simple_tag()
def asset_media_url(asset):
    return urljoin(
        settings.MEDIA_URL,
        "/".join(
            (
                asset.project.campaign.slug,
                asset.project.slug,
                asset.item.item_id,
                asset.media_url,
            )
        ),
    )
