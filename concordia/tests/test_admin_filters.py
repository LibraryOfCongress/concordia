from django.test import RequestFactory, TestCase
from django.utils import timezone

from concordia.admin import ProjectAdmin, TranscriptionAdmin
from concordia.admin.filters import ProjectCampaignListFilter, SubmittedFilter
from concordia.models import Campaign, Project, Transcription
from concordia.tests.utils import CreateTestUsers, create_project, create_transcription


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


class CampaignListFilterTest(CreateTestUsers, TestCase):
    def setUp(self):
        self.project = create_project()

    def test_lookups(self):
        request = RequestFactory().get("/admin/concordia/project/?campaign__status=1")
        f = ProjectCampaignListFilter(
            request,
            {"campaign__id__exact": self.project.campaign.id},
            Project,
            ProjectAdmin,
        )
        projects = f.queryset(None, Project.objects.all())
        self.assertEqual(projects.count(), 1)

        f = ProjectCampaignListFilter(
            request, {"campaign__status": Campaign.Status.ACTIVE}, Project, ProjectAdmin
        )
        projects = f.queryset(None, Project.objects.all())
        self.assertEqual(projects.count(), 1)
