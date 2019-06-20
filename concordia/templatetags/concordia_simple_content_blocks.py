from django import template
from django.core.exceptions import ObjectDoesNotExist
from django.utils.safestring import mark_safe

from ..models import SimpleContentBlock

register = template.Library()


@register.simple_tag()
def simple_content_block(block_label):
    try:
        content_block = SimpleContentBlock.objects.get(label=block_label)
        # SimpleContentBlocks always contain HTML and they are entered by admins
        # and processed through Bleach:
        return mark_safe(content_block.body)  # nosec
    except ObjectDoesNotExist:
        return ""
