# concordia/templatetags/visualization_tags.py

from django import template
from django.utils.html import escape, format_html, format_html_join

register = template.Library()


@register.simple_tag
def concordia_visualization(name, **attrs):
    """
    Render a <section> with a <canvas> and include its corresponding
    visualization script.

    Usage in a template:
        {% load visualization_tags %}
        {% concordia_visualization "daily-activity" style="float:left;" class="chart" %}

    This will output:
        <div class="visualization-container chart" style="float:left;">
            <section>
                <canvas id="daily-activity"></canvas>
            </section>
        </div>

    Args:
        name (str):
            The slug identifying both the <canvas>’s id and the visualization
            script filename.
        **attrs:
            Any number of HTML attribute=value pairs to set on the <section> tag.
            Example: style="width:50%; float:left;" class="chart-wrapper" data-foo="bar"

    Returns:
        SafeString:
            The combined HTML for the <section> (with escaped attrs) and
            the <script> tag.
    """

    # Ensure 'visualization-container' is always present in class attribute
    user_classes = attrs.pop("class", "")
    combined_classes = "visualization-container"
    if user_classes:
        combined_classes += f" {user_classes}"
    attrs["class"] = combined_classes

    # Build an attribute string like: key1="value1" key2="value2"
    # Using format_html_join ensures that each key and value is properly escaped.
    if attrs:
        attr_items = ((escape(key), escape(value)) for key, value in attrs.items())
        # format_html_join(' ', '{}="{}"', attr_items) -> 'key1="value1" key2="value2"'
        attrs_str = format_html_join(" ", '{}="{}"', attr_items)
        # Prepend a space so that when we do '<div {attrs_str}>
        # we get "<div key=...>"
        attrs_str = format_html(" {}", attrs_str)
    else:
        attrs_str = format_html("")  # empty

    # Build the <div> + <section> + <canvas> line
    # We use the section in order to be able to grow the
    # canvas's container to fit the entire thing. We need
    # the outer div to be able to add elements to our display
    # (e.g., a csv) without resizing the section
    # Use format_html so that {name} is escaped if necessary.
    canvas_html = format_html(
        "<div{}>" '<section><canvas id="{}"></canvas></section>' "</div>",
        attrs_str,
        name,
    )

    # Because we used format_html, this is already safe.
    return canvas_html
