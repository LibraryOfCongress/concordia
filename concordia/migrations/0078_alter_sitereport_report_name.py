# Generated by Django 3.2.18 on 2023-05-08 15:13

from django.db import migrations, models


def update_report_names(apps, schema_editor):
    SiteReport = apps.get_model("concordia", "SiteReport")
    for report in SiteReport.objects.filter(report_name="RETIRED_TOTAL"):
        report.report_name = "Retired campaigns"
        report.save()
    for report in SiteReport.objects.filter(report_name="TOTAL"):
        report.report_name = "Active and completed campaigns"
        report.save()


def backwards(apps, schema_editor):
    SiteReport = apps.get_model("concordia", "SiteReport")
    for report in SiteReport.objects.filter(report_name="Retired campaigns"):
        report.report_name = "RETIRED_TOTAL"
        report.save()
    for report in SiteReport.objects.filter(
        report_name="Active and completed campaigns"
    ):
        report.report_name = "TOTAL"
        report.save()


class Migration(migrations.Migration):
    dependencies = [
        ("concordia", "0077_alter_sitereport_report_name"),
    ]

    operations = [
        migrations.AlterField(
            model_name="sitereport",
            name="report_name",
            field=models.CharField(
                blank=True,
                choices=[
                    (
                        "Active and completed campaigns",
                        "Active and completed campaigns",
                    ),
                    ("Retired campaigns", "Retired campaigns"),
                ],
                default="",
                max_length=80,
            ),
        ),
        migrations.RunPython(update_report_names, backwards),
    ]