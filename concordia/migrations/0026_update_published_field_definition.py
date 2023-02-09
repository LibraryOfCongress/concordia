# Generated by Django 2.2 on 2019-04-19 15:41

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("concordia", "0025_unicode_slugs")]

    operations = [
        migrations.AlterField(
            model_name="asset",
            name="published",
            field=models.BooleanField(blank=True, default=False),
        ),
        migrations.AlterField(
            model_name="campaign",
            name="published",
            field=models.BooleanField(blank=True, default=False),
        ),
        migrations.AlterField(
            model_name="item",
            name="published",
            field=models.BooleanField(blank=True, default=False),
        ),
        migrations.AlterField(
            model_name="project",
            name="published",
            field=models.BooleanField(blank=True, default=False),
        ),
    ]
