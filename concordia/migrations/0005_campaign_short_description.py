# Generated by Django 2.0.9 on 2018-10-10 19:31

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("concordia", "0004_auto_20181010_1715")]

    operations = [
        migrations.AddField(
            model_name="campaign",
            name="short_description",
            field=models.TextField(blank=True),
        )
    ]
