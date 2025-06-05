# concordia/templatetags/visualization_tags.py

from django import template
from django.templatetags.static import static
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
        <section style="float:left;" class="chart">
            <canvas id="daily-activity"></canvas>
        </section>
        <script
            type="module"
            src="{% static 'js/visualizations/daily-activity.js' %}"
        ></script>

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

    # Build an attribute string like: key1="value1" key2="value2"
    # Using format_html_join ensures that each key and value is properly escaped.
    if attrs:
        attr_items = ((escape(key), escape(value)) for key, value in attrs.items())
        # format_html_join(' ', '{}="{}"', attr_items) -> 'key1="value1" key2="value2"'
        attrs_str = format_html_join(" ", '{}="{}"', attr_items)
        # Prepend a space so that when we do '<section {attrs_str}>'
        # we get "<section key=…>"
        attrs_str = format_html(" {}", attrs_str)
    else:
        attrs_str = format_html("")  # empty

    # Build the <section> + <canvas> line
    # Use format_html so that {name} is escaped if necessary.
    section_html = format_html(
        '<section{}><canvas id="{}"></canvas></section>', attrs_str, name
    )

    # Build the <script> tag, pointing at /static/js/visualizations/{name}.js
    script_src = static(f"js/visualizations/{name}.js")
    script_html = format_html('<script type="module" src="{}"></script>', script_src)

    # Because we used format_html, this is already safe.
    return section_html + script_html
