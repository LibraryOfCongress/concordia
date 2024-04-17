# encoding: utf-8
"""
Query String manipulation filters
Originally from https://github.com/acdha/django-bittersweet
"""

from django.http import QueryDict
from django.template import Library, Node, TemplateSyntaxError, Variable
from django.utils.html import escape
from django.utils.translation import gettext_lazy as _

register = Library()


class QueryStringAlterer(Node):
    """
    Query String alteration template tag

    Receives a query string (either text or a QueryDict such as request.GET)
    and a list of changes to apply. The result will be returned as text query
    string, allowing use like this::

        <a href="?{% qs_alter request.GET type=object.type %}">{{ label }}</a>

    There are two available alterations:

        Assignment:

            name=var

        Deletion - removes the named parameter:

            delete:name

        Delete a parameter matching a value:

            delete_value:"name",value

        Delete a parameter matching a value from another variable:

            delete_value:field_name,value

    Examples:

    Query string provided as QueryDict::

        {% qs_alter request.GET foo=bar %}
        {% qs_alter request.GET foo=bar baaz=quux %}
        {% qs_alter request.GET foo=bar baaz=quux delete:corge %}

    Remove one facet from a list::

        {% qs_alter request.GET foo=bar baaz=quux delete_value:"facets",value %}

    Query string provided as string::

        {% qs_alter "foo=baaz" foo=bar %}

    Any query string may be stored in a variable in the local template context by
    making the last argument "as variable_name"::

        {% qs_alter request.GET foo=bar baaz=quux delete:corge as new_qs %}
    """

    def __init__(self, base_qs, as_variable, *args):
        self.base_qs = Variable(base_qs)
        self.args = args
        # Control whether we return the result or save it to the context:
        self.as_variable = as_variable

    def render(self, context):
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
    def qs_alter_tag(cls, parser, token):
        try:
            bits = token.split_contents()
        except ValueError as err:
            raise TemplateSyntaxError(
                _(
                    "qs_alter requires at least two arguments: the initial query string"
                    " and at least one alteration"
                )
            ) from err

        if bits[-2] == "as":
            as_variable = bits[-1]
            bits = bits[0:-2]
        else:
            as_variable = None

        return QueryStringAlterer(bits[1], as_variable, *bits[2:])


register.tag("qs_alter", QueryStringAlterer.qs_alter_tag)
