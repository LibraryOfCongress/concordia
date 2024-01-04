# Generated by Django 3.2.23 on 2024-01-04 20:08

import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("concordia", "0090_guide"),
    ]

    operations = [
        migrations.AddField(
            model_name="card",
            name="campaign",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                to="concordia.campaign",
            ),
        ),
        migrations.AddField(
            model_name="card",
            name="created_on",
            field=models.DateTimeField(
                auto_now_add=True, default=django.utils.timezone.now
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="card",
            name="display_heading",
            field=models.CharField(blank=True, max_length=80, null=True),
        ),
    ]
