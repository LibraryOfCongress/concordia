"""
Ensure that basic site configuration has been applied.

This command is intended for automated scenarios: a fresh database should be
configured on first run, but a newly launched container should not make any
changes. For convenience with Docker, default values for each argument are
read from environment variables.

Usage:
    python manage.py ensure_initial_site_configuration
    python manage.py ensure_initial_site_configuration \
        --admin-username admin --admin-email admin@example.com \
        --site-name "Example" --site-domain example.com

Environment defaults:
    CONCORDIA_ADMIN_USERNAME -> --admin-username (default: "admin")
    CONCORDIA_ADMIN_EMAIL    -> --admin-email    (default: "crowd@loc.gov")
    HOST_NAME                -> --site-name and --site-domain
                                (default: "example.com")

Tasks performed:
  1. Ensure at least one admin user exists. If missing, create one with an
     unusable password so the password reset flow must be used.
  2. Ensure the Sites framework has the intended site name and domain.
"""

import os
from argparse import ArgumentParser

from django.contrib.auth.models import User
from django.contrib.sites.models import Site
from django.core.management.base import BaseCommand
from django.db.transaction import atomic


class Command(BaseCommand):
    help = "Ensure that core site configuration has been applied"  # NOQA: A003

    def add_arguments(self, parser: ArgumentParser) -> None:
        """
        Add command-line arguments with environment-based defaults.

        Notes:
            The defaults mirror container-friendly env vars so this command can
            run non-interactively during provisioning.
        """
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
    def handle(
        self,
        *,
        admin_username: str,
        admin_email: str,
        site_name: str,
        site_domain: str,
        **options,
    ) -> None:
        """
        Ensure an admin user and the Site record are in the desired state.

        Behavior:
            - Get or create a superuser with the provided username and email.
              If created, set an unusable password.
            - Update the user's email if it differs.
            - If the site domain is not the placeholder "example.com", update
              all Site rows to use the provided name and domain.

        Args:
            admin_username (str): Username for the admin user.
            admin_email (str): Email for the admin user.
            site_name (str): Desired Site.name value.
            site_domain (str): Desired Site.domain value.

        Returns:
            None
        """
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
            updated = Site.objects.update(name=site_name, domain=site_domain)
            if updated:
                self.stdout.write(
                    f"Configured site with name {site_name} and domain {site_domain}"
                )
