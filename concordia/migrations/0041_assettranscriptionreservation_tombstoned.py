# Generated by Django 2.2.7 on 2020-01-30 18:29

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("concordia", "0040_assettranscriptionreservation_last_reserve_time"),
    ]

    operations = [
        migrations.AddField(
            model_name="assettranscriptionreservation",
            name="tombstoned",
            field=models.BooleanField(blank=True, default=False),
        ),
    ]
