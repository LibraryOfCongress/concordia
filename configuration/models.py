import json

from django import template
from django.db import models


class Configuration(models.Model):
    class DataType(models.TextChoices):
        TEXT = "text", "Plain text"
        NUMBER = "number", "Number"
        BOOLEAN = "boolean", "Boolean"
        JSON = "json", "JSON"
        HTML = "html", "HTML"

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

    def __str__(self):
        return self.key

    def get_value(self):
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
        else:
            # DataType.TEXT or an unkonwn type,
            # so just return the value itself
            return self.value
