# Generated by Django 4.2.16 on 2025-03-18 20:01

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("configuration", "0003_populate_retry_configurations"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="configuration",
            options={"ordering": ["key"]},
        ),
    ]
