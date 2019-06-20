from django import template
from django.core.exceptions import ObjectDoesNotExist

from ..models import SimpleContentBlock

register = template.Library()


@register.simple_tag()
def simple_content_block(block_label):
    content_block_body = ""
    try:
        content_block = SimpleContentBlock.objects.get(label=block_label)
        content_block_body = content_block.body
    except ObjectDoesNotExist:
        pass
    return content_block_body
