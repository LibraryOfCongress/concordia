from django.contrib import admin

from .models import ImportItem, ImportItemAsset, ImportJob

admin.site.register(ImportJob)
admin.site.register(ImportItem)
admin.site.register(ImportItemAsset)
