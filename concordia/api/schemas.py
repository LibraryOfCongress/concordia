from ninja import Schema


def to_camel(string: str) -> str:
    parts = string.split("_")
    return parts[0] + "".join(word.capitalize() for word in parts[1:])


class CamelSchema(Schema):
    """
    Base schema for Django Ninja that converts field names to camelCase in JSON
    responses while using snake_case in Python code.
    """

    class Config(Schema.Config):
        alias_generator = to_camel
        populate_by_name = True
