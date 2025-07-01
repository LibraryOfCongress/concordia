from django import template

register = template.Library()


@register.simple_tag()
def asset_media_url(asset):
    return asset.storage_image.url
