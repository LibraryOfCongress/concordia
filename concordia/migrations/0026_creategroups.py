from django.db import migrations
from django.conf import settings


def create_groups(apps, schema_editor):
    Group = apps.get_model("auth", "Group")

    cm_group_exists = False
    newsletter_group_exists = False

    try:
        cm_group_exists = Group.objects.get(name=settings.COMMUNITY_MANAGER_GROUP_NAME)
    except:
        if not cm_group_exists:
            Group.objects.create(name=settings.COMMUNITY_MANAGER_GROUP_NAME)

    try:
        newsletter_group_exists = Group.objects.get(name=settings.NEWSLETTER_GROUP_NAME)
    except:
        if not newsletter_group_exists:
            Group.objects.create(name=settings.NEWSLETTER_GROUP_NAME)


class Migration(migrations.Migration):

    dependencies = [("concordia", "0025_auto_20180924_2022"), ("auth", "0001_initial")]

    operations = [migrations.RunPython(create_groups)]
