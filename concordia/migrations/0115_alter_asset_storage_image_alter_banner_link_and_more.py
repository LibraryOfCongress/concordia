# Generated by Django 4.2.22 on 2025-06-16 13:24

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("concordia", "0114_create_daily_activity_periodic_task"),
    ]

    operations = [
        migrations.AlterField(
            model_name="banner",
            name="link",
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
    ]
