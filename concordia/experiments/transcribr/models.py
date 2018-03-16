from django.db import models

class User(models.Model):
    email = models.EmailField()
    username = models.CharField(max_length=50)


class Collection(models.Model):
    name = models.CharField(max_length=50)


class Asset(models.Model):
    collection = models.ForeignKey(Collection, on_delete=models.CASCADE)


class Tag(models.Model):
    name = models.CharField(max_length=50)
    value = models.CharField(max_length=50)


class UserAssetTagCollection(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    asset = models.ForeignKey(Asset, on_delete=models.CASCADE)
    tags = models.ManyToManyField(Tag, blank=True)


class Trascription(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    asset = models.ForeignKey(Asset, on_delete=models.CASCADE)
    parent = models.ForeignKey('self', blank=True, null=True, on_delete=models.SET_NULL)
    text = models.TextField()
    status = models.CharField(max_length=50)    

