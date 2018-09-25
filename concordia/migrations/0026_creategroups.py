from django.db import migrations


def create_groups(apps, schema_editor):
    Group = apps.get_model("auth", "Group")

    Group.objects.create(name="CM")

    Group.objects.create(name="Newsletter")


class Migration(migrations.Migration):

    dependencies = [("concordia", "0025_auto_20180924_2022"), ("auth", "0001_initial")]

    operations = [migrations.RunPython(create_groups)]
