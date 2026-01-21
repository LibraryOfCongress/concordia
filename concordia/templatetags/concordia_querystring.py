"""
Query string manipulation template tag.

Originally from https://github.com/acdha/django-bittersweet
"""

from typing import Any, Optional

from django.http import QueryDict
from django.template import Library, Node, Variable
from django.template.base import Parser, Token
from django.utils.html import escape

register = Library()


class QueryStringAlterer(Node):
    """
    Template node that applies alterations to a query string.

    Behavior:
        Resolves a base query string from the template context (either a raw
        query string or a `QueryDict` such as `request.GET`) and applies a
        sequence of alterations provided as tag arguments.

        Supported alterations:
            - Assignment: `name=value`
            - Deletion by key: `delete:name`
            - Deletion by key and value (value from a literal or a variable):
              `delete_value:"name",value` or `delete_value:field_name,value`
            - Conditional add if missing: `add_if_missing:name=value`

        The result is URL-encoded and HTML-escaped. If the tag is used with an
        `as variable_name` clause, the encoded string is stored in the context
        under that name and an empty string is rendered. Otherwise, the encoded
        string is returned.

    Usage:
        The tag is registered as `qs_alter`. Provide a base query string
        (a `QueryDict` like `request.GET` or a string) followed by one or more
        alterations.

        Query string provided as `QueryDict`:

            {% qs_alter request.GET foo=bar %}
            {% qs_alter request.GET foo=bar baaz=quux %}
            {% qs_alter request.GET foo=bar baaz=quux delete:corge %}

        Remove one facet from a list:

            {% qs_alter request.GET foo=bar baaz=quux
               delete_value:"facets",value %}

        Conditionally add a parameter only if missing:

            {% qs_alter request.GET add_if_missing:foo=bar %}

        Query string provided as string:

            {% qs_alter "foo=baaz" foo=bar %}

        Store the result in a variable in the template context:

            {% qs_alter request.GET foo=bar baaz=quux delete:corge as new_qs %}

    Args (template usage):
        base_qs: Either a `QueryDict` (for example, `request.GET`) or a string
            containing a query string.
        alterations: One or more alteration arguments in the formats described
            above.
        as variable_name: Optional. If provided, the result is saved to the
            named context variable instead of being rendered.

    Returns:
        str: The encoded query string when not using `as variable_name`;
        otherwise an empty string.
    """

    def __init__(self, base_qs: str, as_variable: Optional[str], *args) -> None:
        self.base_qs = Variable(base_qs)
        self.args = args
        # Controls whether the result is returned or stored in the context.
        self.as_variable = as_variable

    def render(self, context: Any) -> str:
        """
        Render the altered query string.

        Args:
            context: Template rendering context.

        Returns:
            str: The encoded query string, or an empty string when storing the
            result via `as variable_name`.
        """
        base_qs = self.base_qs.resolve(context)

        if isinstance(base_qs, QueryDict):
            qs = base_qs.copy()
        else:
            qs = QueryDict(base_qs, mutable=True)

        for arg in self.args:
            if arg.startswith("delete:"):
                v = arg[7:]
                if v in qs:
                    del qs[v]
            elif arg.startswith("delete_value:"):
                field, value = arg[13:].split(",", 2)
                value = Variable(value).resolve(context)

                if not (field[0] == '"' and field[-1] == '"'):
                    field = Variable(field).resolve(context)
                else:
                    field = field.strip("\"'")

                f_list = qs.getlist(field)
                if value in f_list:
                    f_list.remove(value)
                    qs.setlist(field, f_list)
            elif arg.startswith("add_if_missing:"):
                k, v = arg[15:].split("=", 2)
                if k not in qs:
                    qs[k] = Variable(v).resolve(context)
            else:
                k, v = arg.split("=", 2)
                qs[k] = Variable(v).resolve(context)

        encoded_qs = escape(qs.urlencode())
        if self.as_variable:
            context[self.as_variable] = encoded_qs
            return ""
        else:
            return encoded_qs

    @classmethod
    def qs_alter_tag(cls, parser: Parser, token: Token) -> "QueryStringAlterer":
        """
        Template tag parser for `qs_alter`.

        Args:
            parser: Django template parser.
            token: Token containing the tag and its arguments.

        Returns:
            QueryStringAlterer: A compiled node ready for rendering.
        """
        bits = token.split_contents()

        if bits[-2] == "as":
            as_variable = bits[-1]
            bits = bits[0:-2]
        else:
            as_variable = None

        return QueryStringAlterer(bits[1], as_variable, *bits[2:])


register.tag("qs_alter", QueryStringAlterer.qs_alter_tag)
