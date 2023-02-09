# Generated by Django 3.2.15 on 2022-09-19 19:16

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("concordia", "0054_banner_active"),
    ]

    operations = [
        migrations.AddField(
            model_name="campaign",
            name="status",
            field=models.IntegerField(
                choices=[(1, "Active"), (2, "Completed"), (3, "Retired")], default=1
            ),
        ),
    ]
