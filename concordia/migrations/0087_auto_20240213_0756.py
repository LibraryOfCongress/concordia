# Generated by Django 3.2.23 on 2024-02-13 12:56

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("concordia", "0086_auto_20231215_1311"),
    ]

    operations = [
        migrations.CreateModel(
            name="Card",
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
                ("image_alt_text", models.TextField(blank=True)),
                (
                    "image",
                    models.ImageField(blank=True, null=True, upload_to="card_images"),
                ),
                ("title", models.CharField(max_length=80)),
                ("body_text", models.TextField(blank=True)),
                ("created_on", models.DateTimeField(auto_now_add=True)),
                ("updated_on", models.DateTimeField(auto_now=True, null=True)),
                (
                    "display_heading",
                    models.CharField(blank=True, max_length=80, null=True),
                ),
            ],
            options={
                "ordering": ("title",),
            },
        ),
        migrations.CreateModel(
            name="CardFamily",
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
                (
                    "slug",
                    models.SlugField(allow_unicode=True, max_length=80, unique=True),
                ),
                ("default", models.BooleanField(default=False)),
            ],
            options={
                "verbose_name_plural": "card families",
            },
        ),
        migrations.CreateModel(
            name="Guide",
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
                ("title", models.CharField(max_length=80)),
                ("body", models.TextField(blank=True)),
                ("order", models.IntegerField(default=1)),
                ("link_text", models.CharField(blank=True, max_length=80, null=True)),
                ("link_url", models.CharField(blank=True, max_length=255, null=True)),
            ],
        ),
        migrations.CreateModel(
            name="TutorialCard",
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
                ("order", models.IntegerField(default=0)),
                (
                    "card",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE, to="concordia.card"
                    ),
                ),
                (
                    "tutorial",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="concordia.cardfamily",
                    ),
                ),
            ],
            options={
                "verbose_name_plural": "cards",
            },
        ),
        migrations.DeleteModel(
            name="SimpleContentBlock",
        ),
        migrations.AddField(
            model_name="cardfamily",
            name="cards",
            field=models.ManyToManyField(
                through="concordia.TutorialCard", to="concordia.Card"
            ),
        ),
        migrations.AddField(
            model_name="campaign",
            name="card_family",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                to="concordia.cardfamily",
            ),
        ),
    ]