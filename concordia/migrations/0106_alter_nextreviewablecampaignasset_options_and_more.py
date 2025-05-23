# Generated by Django 4.2.16 on 2025-04-09 17:44

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        (
            "concordia",
            "0105_nextreviewablecampaignasset_concordia_n_transcr_aafdba_gin_and_more",
        ),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="nextreviewablecampaignasset",
            options={"get_latest_by": "created_on", "ordering": ("-created_on",)},
        ),
        migrations.AlterModelOptions(
            name="nextreviewabletopicasset",
            options={"get_latest_by": "created_on", "ordering": ("-created_on",)},
        ),
        migrations.AlterModelOptions(
            name="nexttranscribablecampaignasset",
            options={"get_latest_by": "created_on", "ordering": ("-created_on",)},
        ),
        migrations.AlterModelOptions(
            name="nexttranscribabletopicasset",
            options={"get_latest_by": "created_on", "ordering": ("-created_on",)},
        ),
        migrations.AlterField(
            model_name="nextreviewablecampaignasset",
            name="asset",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE, to="concordia.asset"
            ),
        ),
        migrations.AlterField(
            model_name="nextreviewabletopicasset",
            name="asset",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE, to="concordia.asset"
            ),
        ),
        migrations.AlterUniqueTogether(
            name="nextreviewabletopicasset",
            unique_together={("asset", "topic")},
        ),
        migrations.AlterUniqueTogether(
            name="nexttranscribabletopicasset",
            unique_together={("asset", "topic")},
        ),
    ]
