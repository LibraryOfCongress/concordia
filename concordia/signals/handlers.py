from django.conf import settings
from django.contrib.auth.models import Group
from django_registration.signals import user_registered
from django.dispatch import receiver


@receiver(user_registered)
def add_user_to_newsletter(sender, user, request, **kwargs):
    if (
        request.POST
        and "newsletterOptIn" in request.POST
        and request.POST["newsletterOptIn"]
    ):
        newsletter_group = Group.objects.get(name=settings.NEWSLETTER_GROUP_NAME)
        newsletter_group.user_set.add(user)
        newsletter_group.save()
