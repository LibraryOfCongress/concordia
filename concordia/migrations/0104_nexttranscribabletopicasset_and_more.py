# Generated by Django 4.2.16 on 2025-04-04 18:55

import uuid

import django.contrib.postgres.fields
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("concordia", "0103_alter_item_title"),
    ]

    operations = [
        migrations.CreateModel(
            name="NextTranscribableTopicAsset",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("item_item_id", models.CharField(max_length=100)),
                ("project_slug", models.SlugField(allow_unicode=True, max_length=80)),
                ("sequence", models.PositiveIntegerField(default=1)),
                ("created_on", models.DateTimeField(auto_now_add=True)),
                (
                    "transcription_status",
                    models.CharField(
                        choices=[
                            ("not_started", "Not Started"),
                            ("in_progress", "In Progress"),
                            ("submitted", "Needs Review"),
                            ("completed", "Completed"),
                        ],
                        db_index=True,
                        default="not_started",
                        editable=False,
                        max_length=20,
                    ),
                ),
                (
                    "asset",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="concordia.asset",
                    ),
                ),
                (
                    "item",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE, to="concordia.item"
                    ),
                ),
                (
                    "project",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="concordia.project",
                    ),
                ),
                (
                    "topic",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="concordia.topic",
                    ),
                ),
            ],
            options={
                "abstract": False,
            },
        ),
        migrations.CreateModel(
            name="NextTranscribableCampaignAsset",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("item_item_id", models.CharField(max_length=100)),
                ("project_slug", models.SlugField(allow_unicode=True, max_length=80)),
                ("sequence", models.PositiveIntegerField(default=1)),
                ("created_on", models.DateTimeField(auto_now_add=True)),
                (
                    "transcription_status",
                    models.CharField(
                        choices=[
                            ("not_started", "Not Started"),
                            ("in_progress", "In Progress"),
                            ("submitted", "Needs Review"),
                            ("completed", "Completed"),
                        ],
                        db_index=True,
                        default="not_started",
                        editable=False,
                        max_length=20,
                    ),
                ),
                (
                    "asset",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="concordia.asset",
                    ),
                ),
                (
                    "campaign",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="concordia.campaign",
                    ),
                ),
                (
                    "item",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE, to="concordia.item"
                    ),
                ),
                (
                    "project",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="concordia.project",
                    ),
                ),
            ],
            options={
                "abstract": False,
            },
        ),
        migrations.CreateModel(
            name="NextReviewableTopicAsset",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("item_item_id", models.CharField(max_length=100)),
                ("project_slug", models.SlugField(allow_unicode=True, max_length=80)),
                ("sequence", models.PositiveIntegerField(default=1)),
                ("created_on", models.DateTimeField(auto_now_add=True)),
                (
                    "transcriber_ids",
                    django.contrib.postgres.fields.ArrayField(
                        base_field=models.IntegerField(),
                        blank=True,
                        default=list,
                        size=None,
                    ),
                ),
                (
                    "asset",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="concordia.asset",
                    ),
                ),
                (
                    "item",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE, to="concordia.item"
                    ),
                ),
                (
                    "project",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="concordia.project",
                    ),
                ),
                (
                    "topic",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="concordia.topic",
                    ),
                ),
            ],
            options={
                "abstract": False,
            },
        ),
        migrations.CreateModel(
            name="NextReviewableCampaignAsset",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("item_item_id", models.CharField(max_length=100)),
                ("project_slug", models.SlugField(allow_unicode=True, max_length=80)),
                ("sequence", models.PositiveIntegerField(default=1)),
                ("created_on", models.DateTimeField(auto_now_add=True)),
                (
                    "transcriber_ids",
                    django.contrib.postgres.fields.ArrayField(
                        base_field=models.IntegerField(),
                        blank=True,
                        default=list,
                        size=None,
                    ),
                ),
                (
                    "asset",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="concordia.asset",
                    ),
                ),
                (
                    "campaign",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="concordia.campaign",
                    ),
                ),
                (
                    "item",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE, to="concordia.item"
                    ),
                ),
                (
                    "project",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="concordia.project",
                    ),
                ),
            ],
            options={
                "abstract": False,
            },
        ),
    ]
