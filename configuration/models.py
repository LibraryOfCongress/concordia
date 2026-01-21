import json
from typing import Any

from django import template
from django.core.exceptions import ValidationError
from django.db import models

from configuration.validation import validate_rate


class Configuration(models.Model):
    """
    Key/value configuration model with typed decoding.

    Purpose:
        Store site configuration as string values and expose a helper that
        converts the stored text into a concrete Python type based on
        `data_type`.

    Fields:
        key (models.CharField): Unique identifier for the setting.
        data_type (models.CharField): One of `DataType` choices indicating how
            `value` should be interpreted.
        value (models.TextField): Raw text representation of the value.
        description (models.TextField): Optional human-readable description.

    Meta:
        ordering: Sorted by `key`.
    """

    class DataType(models.TextChoices):
        """
        Supported data types for decoding `value` in `get_value`.
        """

        TEXT = "text", "Plain text"
        NUMBER = "number", "Number"
        BOOLEAN = "boolean", "Boolean"
        JSON = "json", "JSON"
        HTML = "html", "HTML"
        RATE = "rate", "Rate"

    key = models.CharField(
        max_length=255,
        unique=True,
        help_text="Unique identifier for the configuration setting",
    )
    data_type = models.CharField(
        max_length=10,
        choices=DataType.choices,
        default=DataType.TEXT,
        help_text="Data type of the value",
    )
    value = models.TextField(help_text="Value of the configuration setting")
    description = models.TextField(
        blank=True, help_text="Optional description of the configuration setting"
    )

    class Meta:
        ordering = ["key"]

    def __str__(self) -> str:
        """
        Return the configuration key for display.
        """
        return self.key

    def get_value(self) -> "Any":
        """
        Decode and return `value` according to `data_type`.

        Behavior:
            - `NUMBER`: Try `int(value)`, else try `float(value)`, else return 0.
            - `BOOLEAN`: Return True if `value.lower() == "true"`, else False.
            - `JSON`: Parse with `json.loads(value)` and return the result.
            - `HTML`: Render `value` through Django's template engine with an
              empty context and return the rendered string.
            - `RATE`: Validate using `validate_rate(value)`. If validation
              fails, return an empty string. Otherwise return the validated
              value as provided by `validate_rate`.
            - `TEXT` or any unrecognized type: Return `value` unchanged.

        Returns:
            Any: Decoded value. The concrete type depends on `data_type` and
            may be `int`, `float`, `bool`, `str`, `dict`, `list`, or a value
            returned by `validate_rate`.

        Raises:
            json.JSONDecodeError: If `data_type` is `JSON` and `value` is not
            valid JSON.
        """
        if self.data_type == Configuration.DataType.NUMBER:
            try:
                return int(self.value)
            except ValueError:
                try:
                    return float(self.value)
                except ValueError:
                    return 0
        elif self.data_type == Configuration.DataType.BOOLEAN:
            if self.value.lower() == "true":
                return True
            else:
                return False
        elif self.data_type == Configuration.DataType.JSON:
            return json.loads(self.value)
        elif self.data_type == Configuration.DataType.HTML:
            value = template.Template(self.value)
            return value.render(template.Context({}))
        elif self.data_type == Configuration.DataType.RATE:
            try:
                return validate_rate(self.value)
            except ValidationError:
                return ""
        else:
            # DataType.TEXT or an unknown type,
            # so just return the value itself
            return self.value
