# Generated by Django 4.2.13 on 2024-05-09 19:22

from django.db import migrations


def set_simplepages(apps, schema_editor):
    SimplePage = apps.get_model("concordia", "SimplePage")
    Guide = apps.get_model("concordia", "Guide")
    for guide in Guide.objects.all():
        page = SimplePage.objects.get(title=guide.title)
        guide.page = page
        guide.save()


def backwards(apps, schema_editor):
    Guide = apps.get_model("concordia", "Guide")
    for guide in Guide.objects.all():
        guide.page = None
        guide.save()


class Migration(migrations.Migration):

    dependencies = [
        ("concordia", "0091_guide_simple_page"),
    ]

    operations = [
        migrations.RunPython(set_simplepages, backwards),
    ]
