from django.contrib import messages

from ..models import Asset


def publish_item_action(modeladmin, request, queryset):
    """
    Mark all of the selected items and their related assets as published
    """

    count = queryset.filter(published=False).update(published=True)
    asset_count = Asset.objects.filter(item__in=queryset, published=False).update(
        published=True
    )

    messages.info(request, f"Published {count} items and {asset_count} assets")


publish_item_action.short_description = "Publish selected items and assets"


def unpublish_item_action(modeladmin, request, queryset):
    """
    Mark all of the selected items and their related assets as unpublished
    """

    count = queryset.filter(published=True).update(published=False)
    asset_count = Asset.objects.filter(item__in=queryset, published=True).update(
        published=False
    )

    messages.info(request, f"Unpublished {count} items and {asset_count} assets")


unpublish_item_action.short_description = "Unpublish selected items and assets"


def publish_action(modeladmin, request, queryset):
    """
    Mark all of the selected objects as published
    """

    count = queryset.filter(published=False).update(published=True)
    messages.info(request, f"Published {count} objects")


publish_action.short_description = "Publish selected"


def unpublish_action(modeladmin, request, queryset):
    """
    Mark all of the selected objects as unpublished
    """

    count = queryset.filter(published=True).update(published=False)
    messages.info(request, f"Unpublished {count} objects")


unpublish_action.short_description = "Unpublish selected"
