from django.contrib.admin import ModelAdmin
from django.test import RequestFactory, TestCase
from django.utils import timezone

from concordia.admin import (
    CardAdmin,
    ItemAdmin,
    ProjectAdmin,
    ResourceAdmin,
    SiteReportAdmin,
    TranscriptionAdmin,
)
from concordia.admin.filters import (
    CardCampaignListFilter,
    ItemProjectListFilter,
    NextAssetCampaignListFilter,
    OcrGeneratedFilter,
    ProjectCampaignListFilter,
    ProjectCampaignStatusListFilter,
    SiteReportCampaignListFilter,
    SubmittedFilter,
    SupersededListFilter,
    TopicListFilter,
)
from concordia.admin_site import ConcordiaAdminSite
from concordia.models import (
    Campaign,
    Card,
    Item,
    NextTranscribableCampaignAsset,
    Project,
    Resource,
    SiteReport,
    Transcription,
)
from concordia.tests.utils import (
    CreateTestUsers,
    create_asset,
    create_card,
    create_card_family,
    create_item,
    create_project,
    create_resource,
    create_site_report,
    create_topic,
    create_transcription,
)


class NullableTimestampFilterTest(CreateTestUsers, TestCase):
    def setUp(self):
        user = self.create_user(username="tester")
        create_transcription(user=user, submitted=timezone.now())

    def test_lookups(self):
        f = SubmittedFilter(
            None, {"submitted": "null"}, Transcription, TranscriptionAdmin
        )
        transcriptions = f.queryset(None, Transcription.objects.all())
        self.assertEqual(transcriptions.count(), 0)

        f = SubmittedFilter(
            None, {"submitted": "not-null"}, Transcription, TranscriptionAdmin
        )
        transcriptions = f.queryset(None, Transcription.objects.all())
        self.assertEqual(transcriptions.count(), 1)

        f = SubmittedFilter(
            None, {"submitted": timezone.now()}, Transcription, TranscriptionAdmin
        )
        transcriptions = f.queryset(None, Transcription.objects.all())
        self.assertEqual(transcriptions.count(), 1)


class CampaignListFilterTests(CreateTestUsers, TestCase):
    def setUp(self):
        self.campaign = create_project().campaign

    def test_card_filter(self):
        request = RequestFactory().get("/admin/concordia/card/?campaign=")
        f = CardCampaignListFilter(request, {}, Card, CardAdmin)
        cards = f.queryset(None, Card.objects.all())
        self.assertEqual(cards.count(), 0)

        request = RequestFactory().get(
            "/admin/concordia/card/?campaign=%s" % self.campaign.id
        )
        f = CardCampaignListFilter(
            request, {"campaign": self.campaign.id}, Card, CardAdmin
        )
        cards = f.queryset(None, Card.objects.all())
        self.assertEqual(cards.count(), 0)

        self.campaign.card_family = create_card_family()
        self.campaign.card_family.cards.add(create_card())
        self.campaign.save()
        cards = f.queryset(None, Card.objects.all())
        self.assertEqual(cards.count(), 1)

    def test_project_filter(self):
        request = RequestFactory().get(
            "/admin/concordia/project/?campaign__id__exact=%s" % self.campaign.id
        )
        f = ProjectCampaignListFilter(
            request,
            {"campaign__id__exact": self.campaign.id},
            Project,
            ProjectAdmin,
        )
        projects = f.queryset(None, Project.objects.all())
        self.assertEqual(projects.count(), 1)

        request = RequestFactory().get("/admin/concordia/project/?campaign__status=1")
        f = ProjectCampaignListFilter(
            request, {"campaign__status": Campaign.Status.ACTIVE}, Project, ProjectAdmin
        )
        projects = f.queryset(None, Project.objects.all())
        self.assertEqual(projects.count(), 1)

    def test_site_report_filter(self):
        create_site_report(campaign=self.campaign)
        param = "campaign__id__exact"
        request = RequestFactory().get(
            "/admin/concordia/sitereport/?%s=%s" % (param, self.campaign.id)
        )
        site_report_admin = SiteReportAdmin(SiteReport, ConcordiaAdminSite())
        f = SiteReportCampaignListFilter(
            request,
            {param: self.campaign.id},
            SiteReport,
            site_report_admin,
        )
        self.assertTrue(f.has_output())

        self.assertIn(param, f.expected_parameters())

        self.login_user()
        request.user = self.user
        changelist = site_report_admin.get_changelist_instance(request)
        choices = list(f.choices(changelist))
        self.assertEqual(choices[0]["display"], "All")

        self.assertEqual(choices[1]["display"], "Test Campaign")

        self.assertEqual(choices[-1]["display"], "-")

        f.include_empty_choice = False
        self.assertFalse(f.has_output())

        choices = list(f.choices(changelist))
        self.assertEqual(choices[-1]["display"], "Test Campaign")


class ItemFilterTests(CreateTestUsers, TestCase):
    def setUp(self):
        self.project = create_item().project

    def test_project_filter(self):
        request = RequestFactory().get(
            "/admin/concordia/item/?project__in=%s" % self.project.pk
        )
        f = ItemProjectListFilter(
            request, {"project__in": (self.project.id,)}, Item, ItemAdmin
        )
        items = f.queryset(None, Item.objects.all())
        self.assertEqual(items.count(), 1)

        request = RequestFactory().get(
            "/admin/concordia/item/?project__campaign__id__exact=%s"
            % self.project.campaign.pk
        )
        f = ItemProjectListFilter(
            request,
            {"project__campaign__id__exact": self.project.campaign.pk},
            Item,
            ItemAdmin,
        )
        items = f.queryset(None, Item.objects.all())
        self.assertEqual(items.count(), 1)


class ProjectFilterTests(TestCase):
    def setUp(self):
        self.project = create_item().project

    def test_project_campaign_status_list_filter(self):
        f = ProjectCampaignStatusListFilter(None, {}, Project, ProjectAdmin)
        projects = f.queryset(None, Project.objects.all())
        self.assertEqual(projects.count(), 1)

        f = ProjectCampaignStatusListFilter(
            None, {"campaign__status": Campaign.Status.ACTIVE}, Project, ProjectAdmin
        )
        projects = f.queryset(None, Project.objects.all())
        self.assertEqual(projects.count(), 1)


class TranscriptionFilterTests(CreateTestUsers, TestCase):
    def setUp(self):
        user = self.create_user(username="tester")
        create_transcription(user=user)

    def test_ocr_filter(self):
        f = OcrGeneratedFilter("No", {}, Transcription, TranscriptionAdmin)
        transcriptions = f.queryset(None, Transcription.objects.all())
        self.assertEqual(transcriptions.count(), 1)

        f = OcrGeneratedFilter(
            "No", {"ocr_generated": False}, Transcription, TranscriptionAdmin
        )
        transcriptions = f.queryset(None, Transcription.objects.all())
        self.assertEqual(transcriptions.count(), 1)


class TopicListFilterTests(TestCase):
    def setUp(self):
        self.topic = create_topic()
        self.resource1 = create_resource(topic=self.topic)
        self.resource2 = create_resource()

    def test_resource_topic_list_filter(self):
        topic_filter = TopicListFilter(None, {}, Resource, ResourceAdmin)
        resources = topic_filter.queryset(None, Resource.objects.all())
        self.assertEqual(resources.count(), 2)

        topic_filter = TopicListFilter(
            None, {"topic__id__exact": self.topic.id}, Resource, ResourceAdmin
        )
        resources = topic_filter.queryset(None, Resource.objects.all())
        self.assertEqual(resources.count(), 1)


class NextAssetCampaignListFilterTests(TestCase):
    def setUp(self):
        asset = create_asset()
        NextTranscribableCampaignAsset.objects.create(
            asset=asset,
            campaign=asset.campaign,
            item=asset.item,
            item_item_id=asset.item.item_id,
            project=asset.item.project,
            project_slug=asset.item.project.slug,
            sequence=asset.sequence,
            transcription_status=asset.transcription_status,
        )
        self.campaign = asset.campaign

    def test_lookups_only_includes_used_campaigns(self):
        class DummyAdmin(ModelAdmin):
            model = NextTranscribableCampaignAsset

        request = RequestFactory().get(
            "/admin/concordia/nexttranscribablecampaignasset/"
        )
        dummy_admin = DummyAdmin(NextTranscribableCampaignAsset, None)
        fil = NextAssetCampaignListFilter(
            request, {}, NextTranscribableCampaignAsset, dummy_admin
        )

        lookups = list(fil.lookups(request, dummy_admin))
        self.assertEqual(len(lookups), 1)
        self.assertEqual(lookups[0][0], self.campaign.id)
        self.assertEqual(lookups[0][1], self.campaign.title)


class SupersededListFilterTests(CreateTestUsers, TestCase):
    def setUp(self):
        self.user = self.create_user(username="tester")
        self.base = create_transcription(user=self.user, text="base")
        self.superseding = create_transcription(
            user=self.user,
            supersedes=self.base,
            text="superseding",
            asset=self.base.asset,
        )
        asset2 = create_asset(item=self.base.asset.item, slug="asset-2")
        self.independent = create_transcription(
            user=self.user, text="independent", asset=asset2
        )

    def test_lookups(self):
        request = RequestFactory().get("/admin/concordia/transcription/")
        f = SupersededListFilter(request, {}, Transcription, TranscriptionAdmin)
        lookups = dict(f.lookups(request, TranscriptionAdmin(Transcription, None)))
        self.assertIn("yes", lookups)
        self.assertIn("no", lookups)
        self.assertEqual(lookups["yes"], "Superseded")
        self.assertEqual(lookups["no"], "Not superseded")

    def test_queryset_superseded_yes(self):
        f = SupersededListFilter(
            None, {"superseded": "yes"}, Transcription, TranscriptionAdmin
        )
        qs = f.queryset(None, Transcription.objects.all())
        self.assertQuerySetEqual(
            qs.order_by("id").values_list("id", flat=True),
            [self.base.id],
            transform=lambda x: x,
        )

    def test_queryset_superseded_no(self):
        f = SupersededListFilter(
            None, {"superseded": "no"}, Transcription, TranscriptionAdmin
        )
        qs = f.queryset(None, Transcription.objects.all())
        ids = set(qs.values_list("id", flat=True))
        self.assertEqual(ids, {self.superseding.id, self.independent.id})

    def test_queryset_no_param_returns_all(self):
        f = SupersededListFilter(None, {}, Transcription, TranscriptionAdmin)
        qs = f.queryset(None, Transcription.objects.all())
        ids = set(qs.values_list("id", flat=True))
        self.assertEqual(ids, {self.base.id, self.superseding.id, self.independent.id})

    def test_queryset_ignores_unknown_value(self):
        f = SupersededListFilter(
            None, {"superseded": "maybe"}, Transcription, TranscriptionAdmin
        )
        qs = f.queryset(None, Transcription.objects.all())
        ids = set(qs.values_list("id", flat=True))
        self.assertEqual(ids, {self.base.id, self.superseding.id, self.independent.id})
