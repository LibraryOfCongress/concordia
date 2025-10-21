from typing import Any

from django import template

register = template.Library()


@register.simple_tag()
def asset_media_url(asset: Any) -> str:
    """
    Return the media URL for an asset's stored image.

    Behavior:
        Reads `asset.storage_image.url` and returns the URL string. This tag
        does not perform existence checks; it assumes the attribute is present
        on the given object.

    Usage:
        Inline `src` attribute:

            {% load concordia_media_tags %}
            <img src="{% asset_media_url asset %}" alt="">

        Store in a variable:

            {% asset_media_url asset as image_url %}
            <img src="{{ image_url }}" alt="">

    Args:
        asset: An object that exposes `storage_image.url`.

    Returns:
        str: The URL of the stored image.
    """
    return asset.storage_image.url
