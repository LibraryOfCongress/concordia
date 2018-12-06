"""
Ensure that our basic site configuration has been applied

This is intended for automated scenarios such as a fresh database server should
be configured on first run but a newly-launched container should not make any
changes. For convenience with Docker, the default values for each command-line
argument will be retrieved from the environment.

Tasks:
1. Ensure that at least one admin user account exists. If not, a new one will be
   created but it will have an unusable password to force use of the password
   reset process.
2. Ensure that the Sites framework has the intended site name & domain
"""

import os

from django.contrib.auth.models import User
from django.contrib.sites.models import Site
from django.core.management.base import BaseCommand
from django.db.transaction import atomic


class Command(BaseCommand):
    help = "Ensure that core site configuration has been applied"

    def add_arguments(self, parser):
        parser.add_argument(
            "--admin-username",
            default=os.environ.get("CONCORDIA_ADMIN_USERNAME", "admin"),
            help="Admin user's username (default=%(default)s)",
        )
        parser.add_argument(
            "--admin-email",
            default=os.environ.get("CONCORDIA_ADMIN_EMAIL", "crowd@loc.gov"),
            help="Admin user's email address (default=%(default)s)",
        )
        parser.add_argument(
            "--site-name",
            default=os.environ.get("HOST_NAME", "example.com"),
            help="Site name (default=%(default)s)",
        )
        parser.add_argument(
            "--site-domain",
            default=os.environ.get("HOST_NAME", "example.com"),
            help="Site domain (default=%(default)s)",
        )

    @atomic
    def handle(self, *, admin_username, admin_email, site_name, site_domain, **options):
        user, user_created = User.objects.get_or_create(
            username=admin_username, defaults={"email": admin_email}
        )
        user.is_staff = user.is_superuser = True

        if user.email != admin_email:
            self.stdout.write(
                f"Changing {admin_username} email from {user.email} to {admin_email}"
            )
            user.email = admin_email

        if user_created:
            user.set_unusable_password()

        user.full_clean()
        user.save()

        if user_created:
            self.stdout.write(
                f"Created superuser {admin_username} account for {admin_email}."
                " Use the password reset form to change the unusable password."
            )

        if site_domain != "example.com":
            updated = Site.objects.filter(domain="example.com").update(
                name=site_name, domain=site_domain
            )
            if updated:
                self.stdout.write(
                    f"Configured site with name {site_name} and domain {site_domain}"
                )
