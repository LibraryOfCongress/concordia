# Generated by Django 2.1.7 on 2019-03-29 21:05

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("concordia", "0024_auto_20190211_1420")]

    operations = [
        migrations.AlterField(
            model_name="asset",
            name="difficulty",
            field=models.PositiveIntegerField(blank=True, default=0, null=True),
        )
    ]
