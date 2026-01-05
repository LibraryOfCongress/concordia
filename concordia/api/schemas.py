from ninja import Schema


def to_camel(string: str) -> str:
    """
    Convert a snake_case string to camelCase.

    Args:
        string (str): Input string using snake_case.

    Returns:
        str: camelCase version of the input. The first segment remains lowercase,
        and subsequent segments are capitalized and concatenated.
    """
    parts = string.split("_")
    return parts[0] + "".join(word.capitalize() for word in parts[1:])


class CamelSchema(Schema):
    """
    Base schema for Django Ninja that renders JSON with camelCase field names
    while keeping snake_case attribute names in Python code.
    """

    class Config(Schema.Config):
        """
        Pydantic-style configuration (ninja.Schema is a thin wrapper around Pydantic)
        that enables automatic camelCase aliases and allows population using original
        snake_case field names.
        """

        alias_generator = to_camel
        populate_by_name = True
