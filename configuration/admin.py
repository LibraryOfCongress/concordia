from django.contrib import admin
from django.utils.html import format_html

from .models import Configuration


@admin.register(Configuration)
class ConfigurationAdmin(admin.ModelAdmin):
    list_display = ("key", "value", "description")
    readonly_fields = ("validated_value",)

    def validated_value(self, obj):
        return format_html(
            "<div>{}</div><div style='color: #777; font-size: 0.9em;'>{}</div>",
            obj.get_value(),
            "This is the interpreted value based on the selected data type. "
            "This value is what will be seen by the code that uses this configuration.",
        )
