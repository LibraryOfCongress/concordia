# Generated by Django 3.2.18 on 2023-03-27 17:33

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("concordia", "0074_auto_20230314_1341"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="asset",
            options={"permissions": [("reopen_asset", "Can reopen asset")]},
        ),
        migrations.AlterModelOptions(
            name="userprofileactivity",
            options={"verbose_name_plural": "User profile activities"},
        ),
    ]