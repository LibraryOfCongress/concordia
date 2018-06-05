import datetime
from django.db import models
from django.contrib.auth.models import User
from django.utils.translation import ugettext_lazy as _


class FAQ(models.Model):
    question = models.TextField(
        _("question"), help_text=_("The actual question itself.")
    )
    answer = models.TextField(_("answer"), blank=True, help_text=_("The answer text."))
    slug = models.SlugField(_("slug"), max_length=100)
    created_on = models.DateTimeField(_("created on"), default=datetime.datetime.now)
    updated_on = models.DateTimeField(_("updated on"))
    created_by = models.ForeignKey(
        User,
        verbose_name=_("created by"),
        null=True,
        related_name="+",
        on_delete=models.CASCADE,
    )
    updated_by = models.ForeignKey(
        User,
        verbose_name=_("updated by"),
        null=True,
        related_name="+",
        on_delete=models.CASCADE,
    )
