from django.db import migrations


def populate_configuration(apps, schema_editor):
    Configuration = apps.get_model("configuration", "Configuration")

    initial_data = [
        {
            "key": "next_asset_rate_limit",
            "data_type": "rate",
            "value": "4/m",
            "description": "Rate limit of anonymous users for the next_*_asset views. Format is 'X/u', where 'X' is the number of requests and 'u' is 's', 'm', 'h' or'd' (second, minute, hour or day). '5/s' means 'five per second'.",
        },
    ]

    for entry in initial_data:
        Configuration.objects.update_or_create(key=entry["key"], defaults=entry)


def revert_populate_configuration(apps, schema_editor):
    # We can't actually revert the data to the state it was before,
    # and there's no actual need to, but we need this function to be
    # able to reverse this migration
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("configuration", "0005_alter_configuration_data_type"),
    ]

    operations = [
        migrations.RunPython(populate_configuration, revert_populate_configuration),
    ]
