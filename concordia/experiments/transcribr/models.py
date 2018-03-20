from django.db import models
from django.urls import reverse
from django.conf import settings
from django.contrib.auth.models import AbstractUser, BaseUserManager

class TranscribrUserManager(BaseUserManager):
    pass


class TranscribrUser(AbstractUser):
    
    USERNAME_FIELD = 'username'
    objects = TranscribrUserManager()


class Collection(models.Model):
    name = models.CharField(max_length=50)
    description = models.TextField(blank=True)
    start_date = models.DateTimeField(null=True, blank=True)
    end_date = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=8)

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse('transcribr:collection', args=[self.id])


class Asset(models.Model):
    title = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    url = models.URLField(max_length=255)
    collection = models.ForeignKey(Collection, on_delete=models.CASCADE)
    status = models.CharField(max_length=8)

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse('transcribr:asset', args=[self.collection.id, self.id])


class Tag(models.Model):
    name = models.CharField(max_length=50)
    value = models.CharField(max_length=50)


class UserAssetTagCollection(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    asset = models.ForeignKey(Asset, on_delete=models.CASCADE)
    tags = models.ManyToManyField(Tag, blank=True)


class Trascription(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    asset = models.ForeignKey(Asset, on_delete=models.CASCADE)
    parent = models.ForeignKey('self', blank=True, null=True, on_delete=models.SET_NULL)
    text = models.TextField(blank=True)
    status = models.CharField(max_length=8)    

