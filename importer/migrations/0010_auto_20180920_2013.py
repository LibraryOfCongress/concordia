# Generated by Django 2.0.8 on 2018-09-20 20:13

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("importer", "0009_convert_project_text_to_keys")]

    operations = [
        migrations.AlterField(
            model_name="campaigntaskdetails",
            name="project",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE, to="concordia.Project"
            ),
        ),
        migrations.AlterUniqueTogether(
            name="campaigntaskdetails", unique_together=set()
        ),
        migrations.RemoveField(model_name="campaigntaskdetails", name="campaign_name"),
        migrations.RemoveField(model_name="campaigntaskdetails", name="campaign_slug"),
        migrations.RemoveField(model_name="campaigntaskdetails", name="project_name"),
        migrations.RemoveField(model_name="campaigntaskdetails", name="project_slug"),
    ]
