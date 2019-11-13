# Generated by Django 2.2 on 2019-05-29 18:11

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [("concordia", "0031_auto_20190509_1142")]

    operations = [
        migrations.AddField(
            model_name="topic",
            name="ordering",
            field=models.IntegerField(
                default=0,
                help_text="Sort order override: lower values will be listed first",
            ),
        )
    ]
