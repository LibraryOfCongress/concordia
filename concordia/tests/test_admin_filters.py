from django.test import RequestFactory, TestCase
from django.utils import timezone

from concordia.admin import CardAdmin, ItemAdmin, ProjectAdmin, TranscriptionAdmin
from concordia.admin.filters import (
    CardCampaignListFilter,
    ItemProjectListFilter,
    OcrGeneratedFilter,
    ProjectCampaignListFilter,
    ProjectCampaignStatusListFilter,
    SubmittedFilter,
)
from concordia.models import Campaign, Card, Item, Project, Transcription
from concordia.tests.utils import (
    CreateTestUsers,
    create_campaign,
    create_card,
    create_card_family,
    create_item,
    create_project,
    create_site_report,
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
        self.campaign.card_family = create_card_family()
        self.campaign.card_family.cards.add(create_card())
        request = RequestFactory().get(
            "/admin/concordia/card/?campaign=%s" % self.campaign.id
        )
        f = CardCampaignListFilter(
            request, {"campaign": self.campaign.id}, Card, CardAdmin
        )
        cards = f.queryset(None, Card.objects.all())
        self.assertEqual(cards.count(), 0)

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


class SiteReportCampaignListFilterTests(TestCase):
    def setUp(self):
        create_campaign()
        create_site_report()

    def test_lookups(self):
        pass


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
