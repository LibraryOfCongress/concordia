from functools import lru_cache

from django import template

register = template.Library()


@register.filter(name="has_group")
@lru_cache(maxsize=200)
def has_group(user, group_name):
    return user.groups.filter(name=group_name).exists()
