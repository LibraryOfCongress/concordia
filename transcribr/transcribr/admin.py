from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import *


@admin.register(Collection)
class CollectionAdmin(admin.ModelAdmin):
    # todo: replace description & metadata with truncated values
    list_display = (
        'title',
        'slug',
        'description',
        'start_date',
        'end_date',
        'metadata',
        'status',
    )


@admin.register(Asset)
class AssetAdmin(admin.ModelAdmin):
    pass


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    pass


@admin.register(UserAssetTagCollection)
class UserAssetTagCollectionAdmin(admin.ModelAdmin):
    pass


@admin.register(Transcription)
class TranscriptionAdmin(admin.ModelAdmin):
    pass
