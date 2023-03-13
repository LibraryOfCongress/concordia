# Generated by Django 2.2.3 on 2019-07-31 22:09

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("concordia", "0037_carouselslide")]

    operations = [
        migrations.AddField(
            model_name="sitereport",
            name="topic",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.DO_NOTHING,
                to="concordia.Topic",
            ),
        )
    ]
