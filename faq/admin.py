from django.contrib import admin
from .models import FAQ


@admin.register(FAQ)
class FAQAdmin(admin.ModelAdmin):
    # todo: replace question & answer with truncated values
    list_display = (
        "id",
        "slug",
        "question",
        "answer",
        "created_on",
        "updated_on",
        "created_by",
        "updated_by",
    )
    list_display_links = ("id", "slug", "question")
