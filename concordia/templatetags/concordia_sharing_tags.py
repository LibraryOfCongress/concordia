from django import template

register = template.Library()


@register.inclusion_tag("fragments/sharing-button-group.html")
def share_buttons(url, title):
    return {"title": title, "url": url}
