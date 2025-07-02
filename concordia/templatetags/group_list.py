from django import template

register = template.Library()


@register.filter
def batch(value, size):
    size = int(size)
    return [value[i : i + size] for i in range(0, len(value), size)]
