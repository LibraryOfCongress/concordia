# Generated by Django 4.2.16 on 2025-04-10 13:52

from django.db import migrations


def add_renew_next_asset_cache_task(apps, schema_editor):
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
    IntervalSchedule = apps.get_model("django_celery_beat", "IntervalSchedule")

    schedule, _ = IntervalSchedule.objects.get_or_create(every=1, period="hours")

    PeriodicTask.objects.update_or_create(
        name="Renew next asset cache",
        defaults={
            "interval": schedule,
            "task": "concordia.tasks.renew_next_asset_cache",
            "enabled": True,
            "description": (
                "Run every hour to refresh cache of transcribable and reviewable assets"
            ),
        },
    )


def remove_renew_next_asset_cache_task(apps, schema_editor):
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
    PeriodicTask.objects.filter(name="Renew next asset cache").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("concordia", "0107_alter_nextreviewablecampaignasset_options_and_more"),
        ("django_celery_beat", "0019_alter_periodictasks_options"),
    ]

    operations = [
        migrations.RunPython(
            add_renew_next_asset_cache_task,
            reverse_code=remove_renew_next_asset_cache_task,
        ),
    ]
