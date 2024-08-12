# Generated by Django 4.2.13 on 2024-07-29 17:40

from django.conf import settings
from django.db import migrations


def create_and_populate_profiles(apps, schema_editor):
    User = apps.get_model("auth", "User")
    UserProfile = apps.get_model("concordia", "UserProfile")
    db_alias = schema_editor.connection.alias
    for user in User.objects.using(db_alias).all().iterator(chunk_size=10000):
        profile, created = UserProfile.objects.using(db_alias).get_or_create(user=user)
        for activity in user.userprofileactivity_set.all():
            profile.transcribe_count += activity.transcribe_count
            profile.review_count += activity.review_count
        profile.save()


def revert_create_and_populate_profiles(apps, schema_editor):
    # We can't actually revert the data to the state it was before,
    # and there's no actual need to, but we need this function to be
    # able to reverse this migration
    pass


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        (
            "concordia",
            "0097_alter_sitereport_options_userprofile_review_count_and_more",
        ),
    ]

    operations = [
        migrations.RunPython(
            create_and_populate_profiles, revert_create_and_populate_profiles
        ),
    ]
