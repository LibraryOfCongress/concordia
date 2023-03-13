# Generated by Django 3.2.15 on 2022-12-17 20:47

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("concordia", "0058_banner_slug"),
    ]

    operations = [
        migrations.CreateModel(
            name="ResourceFile",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("name", models.CharField(max_length=255)),
                ("resource", models.FileField(upload_to="cm-uploads/")),
            ],
            options={
                "ordering": ["name"],
            },
        ),
    ]
