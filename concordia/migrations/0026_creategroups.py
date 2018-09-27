from django.db import migrations
from django.conf import settings


def create_groups(apps, schema_editor):
    Group = apps.get_model("auth", "Group")

    Group.objects.get_or_create(name=settings.COMMUNITY_MANAGER_GROUP_NAME)
    Group.objects.get_or_create(name=settings.NEWSLETTER_GROUP_NAME)


class Migration(migrations.Migration):

    dependencies = [("concordia", "0025_auto_20180924_2022"), ("auth", "0001_initial")]

    operations = [migrations.RunPython(create_groups)]
