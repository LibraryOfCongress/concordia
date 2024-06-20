# Generated by Django 4.2.13 on 2024-06-17 17:13

import django.db.models.deletion
from django.db import migrations, models


def set_field_values(apps, schema_editor):
    Asset = apps.get_model("concordia", "asset")
    db_alias = schema_editor.connection.alias
    assets = (
        Asset.objects.using(db_alias)
        .select_related("item__project__campaign")
        .only("item__project__campaign", "campaign")
        .iterator(chunk_size=10000)
    )

    updated = []
    for asset in assets:
        # Can't use an F object across tables
        # using update/bulk_update, so we have
        # loop through all of them
        asset.campaign = asset.item.project.campaign
        updated.append(asset)
        # To avoid running out of memory, we only
        # keep 1000 assets in memory at a time
        if len(updated) >= 10000:
            Asset.objects.bulk_update(updated, ["campaign"])
            updated = []
    if updated:
        Asset.objects.bulk_update(updated, ["campaign"])


def revert_field_values(apps, schema_editor):
    # We can't actually revert the data, and there's
    # no need to, but we need this function to be
    # able to reverse this migration
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("concordia", "0093_asset_campaign"),
    ]

    operations = [
        migrations.RunPython(set_field_values, revert_field_values),
        migrations.AlterField(
            model_name="asset",
            name="campaign",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE, to="concordia.campaign"
            ),
        ),
    ]
