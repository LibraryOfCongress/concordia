# Generated by Django 4.2.16 on 2025-02-25 19:21

from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Configuration",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "key",
                    models.CharField(
                        help_text="Unique identifier for the configuration setting",
                        max_length=255,
                        unique=True,
                    ),
                ),
                (
                    "value",
                    models.TextField(help_text="Value of the configuration setting"),
                ),
                (
                    "data_type",
                    models.CharField(
                        choices=[
                            ("text", "Plain text"),
                            ("number", "Number"),
                            ("boolean", "Boolean"),
                            ("json", "JSON"),
                            ("html", "HTML"),
                        ],
                        default="text",
                        help_text="Data type of the value",
                        max_length=10,
                    ),
                ),
                (
                    "description",
                    models.TextField(
                        blank=True,
                        help_text="Optional description of the configuration setting",
                    ),
                ),
            ],
        ),
    ]
