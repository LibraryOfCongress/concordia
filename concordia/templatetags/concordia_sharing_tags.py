from typing import Dict

from django import template

register = template.Library()


@register.inclusion_tag("fragments/sharing-button-group.html")
def share_buttons(url: str, title: str) -> Dict[str, str]:
    """
    Build the context for the sharing button fragment and render it.

    Behavior:
        This is an inclusion tag. Django will render
        `fragments/sharing-button-group.html` with the returned context and
        insert the resulting HTML at the call site.

    Usage:
        Render inline:

            {% load concordia_sharing_buttons %}
            {% share_buttons request.build_absolute_uri object.title %}

        Capture the rendered HTML, then output it later:

            {% share_buttons page_url page_title as share_html %}
            {{ share_html|safe }}

        Notes:
            - The value captured with `as` is rendered HTML, not a context
              dictionary. Do not pass it to `{% include %}` as context.

    Args:
        url: Absolute URL to share.
        title: Display title to accompany the share action.

    Returns:
        dict: Mapping used by `fragments/sharing-button-group.html` with keys:
            - `title` (str)
            - `url` (str)
    """
    return {"title": title, "url": url}
