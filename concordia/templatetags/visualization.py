# concordia/templatetags/visualization.py

from django import template
from django.utils.html import escape, format_html, format_html_join
from django.utils.safestring import SafeString

register = template.Library()


@register.simple_tag
def concordia_visualization(name: str, **attrs) -> SafeString:
    """
    Render a container with a section and a canvas for a named visualization.

    This tag outputs a `<div>` that always includes the
    `visualization-container` class, wrapping a `<section>` with a `<canvas>`
    whose `id` is set to the provided `name`. Any extra attributes passed to
    the tag are applied to the outer `<div>` after being safely escaped.

    Usage:
        Load the tag library, then invoke the tag with a name and optional
        HTML attributes.

        Template:

            {% load visualization %}
            {% concordia_visualization "daily-activity"
                style="float:left;" class="chart" data-role="viz" %}

        Output:

            <div class="visualization-container chart" style="float:left;"
                 data-role="viz">
                <section>
                    <canvas id="daily-activity"></canvas>
                </section>
            </div>

        Notes:
            - The `class` attribute you pass is appended to
              `visualization-container`.
            - All attribute names and values are escaped.
            - This tag does not include any `<script>` tags. Visualization
              scripts are included in the site-wide JavaScript rollup.

    Args:
        name (str): The slug used as the `id` of the `<canvas>` element.
        **attrs: Any HTML attributes to apply to the outer `<div>` container.

    Returns:
        SafeString: Escaped HTML for the container, section, and canvas.
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
