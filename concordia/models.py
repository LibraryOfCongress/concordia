from django.contrib.auth.models import User
from django.db import models


class UserProfile(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    myfile = models.FileField(upload_to='profile_pics/')
