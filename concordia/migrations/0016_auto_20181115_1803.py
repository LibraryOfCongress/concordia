# Generated by Django 2.0.9 on 2018-11-15 23:03

from django.db import migrations

from concordia.models import TranscriptionStatus


def update_new_statuses(apps, schema_editor):
    Asset = apps.get_model("concordia", "Asset")

    Asset.objects.filter(transcription_status="in progress").update(
        transcription_status=TranscriptionStatus.IN_PROGRESS
    )
    Asset.objects.filter(transcription_status="not started").update(
        transcription_status=TranscriptionStatus.NOT_STARTED
    )


class Migration(migrations.Migration):
    dependencies = [("concordia", "0015_auto_20181115_1436")]

    operations = [migrations.RunPython(update_new_statuses)]
