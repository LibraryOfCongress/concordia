from ninja import Schema
from pydantic import ConfigDict
from pydantic.alias_generators import to_camel


class CamelSchema(Schema):
    """
    Base schema for Django Ninja that renders JSON with camelCase field names
    while keeping snake_case attribute names in Python code.
    """

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
