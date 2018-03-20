from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import TranscribrUser

admin.site.register(TranscribrUser, UserAdmin)
