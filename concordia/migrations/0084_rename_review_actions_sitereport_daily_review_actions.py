# Generated by Django 3.2.19 on 2023-07-21 14:36

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("concordia", "0083_sitereport_daily_active_users"),
    ]

    operations = [
        migrations.RenameField(
            model_name="sitereport",
            old_name="review_actions",
            new_name="daily_review_actions",
        ),
    ]
