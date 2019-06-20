from django.core.exceptions import ObjectDoesNotExist
from django.template import Library, Template
from django.utils.safestring import mark_safe

from ..models import SimpleContentBlock

register = Library()


@register.simple_tag(takes_context=True)
def simple_content_block(context, block_label):
    try:
        content_block = SimpleContentBlock.objects.get(label=block_label)
    except ObjectDoesNotExist:
        return ""

    # SimpleContentBlocks always contain HTML and they are entered by admins and
    # processed through Bleach so we'll mark the output as safe to avoid
    # double-escaping:
    template = Template(content_block.body)
    return mark_safe(template.render(context))  # nosec
