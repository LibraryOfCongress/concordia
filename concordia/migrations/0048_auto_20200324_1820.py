# Generated by Django 2.2.11 on 2020-03-24 22:20

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("concordia", "0047_auto_20200324_1103"),
    ]

    operations = [
        migrations.RemoveIndex(
            model_name="asset",
            name="concordia_a_id_0c37bf_idx",
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
        migrations.AddIndex(
            model_name="asset",
            index=models.Index(
                fields=["id", "item", "published", "transcription_status"],
                name="concordia_a_id_137ca8_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="item",
            index=models.Index(
                fields=["project", "published"], name="concordia_i_project_d8caf0_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="project",
            index=models.Index(
                fields=["id", "campaign", "published"], name="concordia_p_id_17c9c9_idx"
            ),
        ),
    ]
