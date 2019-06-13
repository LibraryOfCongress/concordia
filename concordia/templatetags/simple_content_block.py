from django import template

from ..models import SimpleContentBlock

register = template.Library()


@register.simple_tag()
def simple_content_block(block_label):
    content_block = SimpleContentBlock.objects.get(label=block_label)
    return content_block.body
