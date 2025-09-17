# ruff: noqa: ERA001 A003
# bandit:skip-file

import json
import uuid
from pathlib import Path

from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.core import serializers
from django.core.management import BaseCommand, call_command

from concordia.models import (
    Asset,
    Campaign,
    Item,
    Project,
    ProjectTopic,
    Topic,
    Transcription,
)

ASSETS_LIMIT_DEFAULT = 10_000
TEST_USERS_DEFAULT = 10_000
TEST_USER_PREFIX_DEFAULT = "locusttest"
TEST_USER_PASSWORD_DEFAULT = "locustpass123"  # nosec B105


def _serialize_qs(qs):
    return json.loads(serializers.serialize("json", qs))


def _serialize_list(objs):
    return json.loads(serializers.serialize("json", objs))


class Command(BaseCommand):
    help = (
        "Build a single JSON fixture for load-testing:\n"
        "- 2 published Topics by ascending `ordering`\n"
        "- Consider 5 published Campaigns by ascending `ordering`\n"
        "- Walk Items/Assets from Topic projects first (cap 10,000 assets),\n"
        "  then from Campaign projects if needed, until the cap\n"
        "- Include closure of Items/Projects/Campaigns/Topics actually used "
        "by chosen Assets\n"
        "- Include all Transcriptions for those Assets and anonymized Users "
        "from those Transcriptions\n"
        "- Add 10,000 new test users (locusttest00001..locusttest10000) "
        "with a known password\n"
        "- Include ProjectTopic rows for selected Topic+Project links\n"
        "- Write one JSON fixture"
    )

    def add_arguments(self, p):
        p.add_argument(
            "--assets-limit",
            type=int,
            default=ASSETS_LIMIT_DEFAULT,
            help=f"Max assets to include (default {ASSETS_LIMIT_DEFAULT})",
        )
        p.add_argument(
            "--test-users",
            type=int,
            default=TEST_USERS_DEFAULT,
            help=f"How many new test users to include (default {TEST_USERS_DEFAULT})",
        )
        p.add_argument(
            "--test-user-prefix",
            default=TEST_USER_PREFIX_DEFAULT,
            help=f"Prefix for test usernames (default '{TEST_USER_PREFIX_DEFAULT}')",
        )
        p.add_argument(
            "--test-user-password",
            default=TEST_USER_PASSWORD_DEFAULT,
            help=(
                f"Password for all test users (default "
                f"'{TEST_USER_PASSWORD_DEFAULT}')"
            ),
        )
        p.add_argument(
            "--output",
            default="loadtest_fixture.json",
            help="Path to write the fixture JSON (default loadtest_fixture.json)",
        )
        p.add_argument(
            "--no-validate",
            action="store_true",
            help=(
                "Do not load the fixture into a test database. "
                "WARNING: fixture will not be verified."
            ),
        )
        p.add_argument(
            "--validate-drop",
            action="store_true",
            help=(
                "Validate by loading into a fresh test DB, "
                "then drop it after loading."
            ),
        )
        p.add_argument(
            "--validate-db-name",
            default=None,
            help=(
                "Override the test DB name used for validation "
                "(default: <default.NAME>_lt)."
            ),
        )
        p.add_argument(
            "--validate-recreate",
            action="store_true",
            help="Force recreation of the validation DB if it already exists.",
        )

    def handle(self, *args, **o):
        assets_limit = int(o["assets_limit"])
        out_path = Path(o["output"]).resolve()

        # Select 2 published Topics by ordering
        topics_qs = Topic.objects.filter(published=True).order_by("ordering")[:2]
        topics = list(topics_qs)
        topic_ids = {t.id for t in topics}
        if not topics:
            self.stderr.write(
                self.style.WARNING(
                    "No published Topics found. "
                    "Proceeding with Campaign-only selection."
                )
            )

        # Projects in those topics via ProjectTopics
        proj_ids_from_topics = set(
            ProjectTopic.objects.filter(topic_id__in=topic_ids).values_list(
                "project_id", flat=True
            )
        )

        # ensure we consider 5 published Campaigns
        # campaigns connected to the topic-derived projects:
        campaigns_from_topics_qs = Campaign.objects.filter(
            published=True,
            id__in=Project.objects.filter(id__in=proj_ids_from_topics).values_list(
                "campaign_id", flat=True
            ),
        ).distinct()

        needed = max(0, 5 - campaigns_from_topics_qs.count())
        if needed > 0:
            # take extra published campaigns (not already counted) by ordering ASC
            extra_campaigns_qs = (
                Campaign.objects.filter(published=True)
                .exclude(id__in=campaigns_from_topics_qs.values_list("id", flat=True))
                .order_by("ordering")[:needed]
            )
            selected_campaigns_qs = campaigns_from_topics_qs.union(extra_campaigns_qs)
        else:
            selected_campaigns_qs = campaigns_from_topics_qs

        # We might end up with <5 if not enough published; that's fine

        # Collect assets up to cap
        asset_ids = set()
        item_ids = set()
        project_ids = set()

        # walk projects from Topics first
        for proj in (
            Project.objects.filter(id__in=proj_ids_from_topics)
            .order_by("id")
            .iterator()
        ):
            if len(asset_ids) >= assets_limit:
                break
            project_ids.add(proj.id)

            for item in (
                Item.objects.filter(project_id=proj.id).order_by("id").iterator()
            ):
                if len(asset_ids) >= assets_limit:
                    break
                item_ids.add(item.id)

                for a in (
                    Asset.objects.filter(item_id=item.id)
                    .order_by("id")
                    .values_list("id", flat=True)
                    .iterator()
                ):
                    if len(asset_ids) >= assets_limit:
                        break
                    asset_ids.add(int(a))

        # If needed, walk projects from selected campaigns (not already included)
        if len(asset_ids) < assets_limit and selected_campaigns_qs.exists():
            proj_ids_from_campaigns = set(
                Project.objects.filter(
                    campaign_id__in=selected_campaigns_qs.values_list("id", flat=True)
                )
                .exclude(id__in=project_ids)
                .values_list("id", flat=True)
            )
            for proj in (
                Project.objects.filter(id__in=proj_ids_from_campaigns)
                .order_by("id")
                .iterator()
            ):
                if len(asset_ids) >= assets_limit:
                    break
                project_ids.add(proj.id)

                for item in (
                    Item.objects.filter(project_id=proj.id).order_by("id").iterator()
                ):
                    if len(asset_ids) >= assets_limit:
                        break
                    item_ids.add(item.id)

                    for a in (
                        Asset.objects.filter(item_id=item.id)
                        .order_by("id")
                        .values_list("id", flat=True)
                        .iterator()
                    ):
                        if len(asset_ids) >= assets_limit:
                            break
                        asset_ids.add(int(a))

        # recompute exact asset set
        assets_qs = Asset.objects.filter(id__in=asset_ids)

        # Items actually referenced by chosen assets
        items_qs = Item.objects.filter(
            id__in=assets_qs.values_list("item_id", flat=True).distinct()
        )
        item_ids = set(items_qs.values_list("id", flat=True))

        # Projects from those items
        projects_qs = Project.objects.filter(
            id__in=items_qs.values_list("project_id", flat=True).distinct()
        )
        project_ids = set(projects_qs.values_list("id", flat=True))

        # Campaigns from those projects
        campaigns_qs = Campaign.objects.filter(
            id__in=projects_qs.values_list("campaign_id", flat=True).distinct()
        )

        # Topics linked to those projects
        topics_from_projects_qs = Topic.objects.filter(
            id__in=ProjectTopic.objects.filter(project_id__in=project_ids)
            .values_list("topic_id", flat=True)
            .distinct()
        )
        # Merge with the initial two topics (won't duplicate)
        topics_final_qs = Topic.objects.filter(
            id__in=set(topics_from_projects_qs.values_list("id", flat=True)) | topic_ids
        )

        # ProjectTopic rows for selected Topic+Project pairs (needed to preserve M2M)
        project_topics_final_qs = ProjectTopic.objects.filter(
            topic_id__in=topics_final_qs.values_list("id", flat=True),
            project_id__in=project_ids,
        )

        # transcriptions + users (anonymize users in-memory)
        trans_qs = Transcription.objects.filter(asset_id__in=asset_ids)
        User = get_user_model()
        user_ids = set(trans_qs.values_list("user_id", flat=True))
        users_qs = User.objects.filter(id__in=user_ids)

        # Make in-memory anonymized copies: we mutate instances but do not save
        anonymized_users = []
        for u in users_qs:
            u.username = f"Anonymized {uuid.uuid4()}"
            if hasattr(u, "first_name"):
                u.first_name = ""
            if hasattr(u, "last_name"):
                u.last_name = ""
            if hasattr(u, "email"):
                u.email = f"anon-{uuid.uuid4()}@example.com"
            if hasattr(u, "is_staff"):
                u.is_staff = False
            if hasattr(u, "is_superuser"):
                u.is_superuser = False
            if hasattr(u, "is_active"):
                u.is_active = False
            try:
                u.set_unusable_password()
            except Exception:  # nosec B110
                pass
            anonymized_users.append(u)

        # build test users
        test_user_count = int(o["test_users"])
        test_prefix = o["test_user_prefix"]
        test_pw_hash = make_password(o["test_user_password"])

        # prepare test user fixtures as explicit dicts
        # (unsaved instances may not serialize well)
        user_app_label = User._meta.app_label
        user_model_name = User._meta.model_name
        test_user_fixtures = []
        for i in range(1, test_user_count + 1):
            uname = f"{test_prefix}{i:05d}"
            test_user_fixtures.append(
                {
                    "model": f"{user_app_label}.{user_model_name}",
                    "pk": None,
                    "fields": {
                        User.USERNAME_FIELD: uname,
                        "password": test_pw_hash,
                        "email": f"{uname}@example.test",
                        "is_active": True if hasattr(User, "is_active") else True,
                        "is_staff": False if hasattr(User, "is_staff") else False,
                        "is_superuser": (
                            False if hasattr(User, "is_superuser") else False
                        ),
                        **({"first_name": ""} if hasattr(User, "first_name") else {}),
                        **({"last_name": ""} if hasattr(User, "last_name") else {}),
                    },
                }
            )

        # Serialize everything into one fixture list
        fixture_objs = []
        # Core
        fixture_objs += _serialize_qs(topics_final_qs.order_by("id"))
        fixture_objs += _serialize_qs(campaigns_qs.order_by("id"))
        fixture_objs += _serialize_qs(projects_qs.order_by("id"))
        fixture_objs += _serialize_qs(items_qs.order_by("id"))
        fixture_objs += _serialize_qs(assets_qs.order_by("id"))
        # Users must appear before Transcriptions (FK dependency)
        fixture_objs += _serialize_list(anonymized_users)
        fixture_objs += test_user_fixtures
        # Transcriptions
        fixture_objs += _serialize_qs(trans_qs.order_by("id"))
        # Through model rows
        fixture_objs += _serialize_qs(project_topics_final_qs.order_by("id"))

        # Warn if below cap, but we don't need to abort
        if len(asset_ids) < assets_limit:
            self.stderr.write(
                self.style.WARNING(
                    f"Collected {len(asset_ids)} assets "
                    f"(cap {assets_limit}). Proceeding."
                )
            )

        # write file
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(fixture_objs, indent=2), encoding="utf-8")
        self.stdout.write(
            self.style.SUCCESS(
                f"Wrote fixture with {len(fixture_objs)} objects → {out_path}"
            )
        )

        # optionally validate by loading into a test DB (migrate + loaddata)
        if o["no_validate"]:
            self.stderr.write(
                self.style.WARNING("Fixture NOT validated (--no-validate set).")
            )
        else:
            call_command(
                "prepare_load_test_db",
                db_alias="default",
                db_name=o["validate_db_name"] or None,
                recreate=bool(o["validate_recreate"]),
                fixtures=[str(out_path)],
                drop_after=bool(o["validate_drop"]),
            )
