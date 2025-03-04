"""
See the module-level docstring for implementation details
"""

from logging import getLogger

from django.core.serializers.json import DjangoJSONEncoder
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

from configuration.utils import configuration_value
from importer import tasks

logger = getLogger(__name__)

# FIXME: these classes should have names which more accurately represent what they do


class TaskStatusModel(models.Model):
    class FailureReason(models.TextChoices):
        IMAGE = "Image"
        RETRIES = "Retries"

    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)

    last_started = models.DateTimeField(
        help_text="Last time when a worker started processing this job",
        null=True,
        blank=True,
    )
    completed = models.DateTimeField(
        help_text="Time when the job completed without error", null=True, blank=True
    )
    failed = models.DateTimeField(
        help_text="Time when the job failed due to an error", null=True, blank=True
    )

    status = models.TextField(
        help_text="Status message, if any, from the last worker", blank=True, default=""
    )

    task_id = models.UUIDField(
        help_text="UUID of the last Celery task to process this record",
        null=True,
        blank=True,
    )

    failure_reason = models.CharField(
        help_text="Reason the task failed, if one was provided",
        max_length=50,
        blank=True,
        default="",
        choices=FailureReason.choices,
    )

    retry_count = models.IntegerField(
        help_text="Number of times the task was retried", default=0
    )

    failure_history = models.JSONField(
        help_text="Information about previous failures of the task, if any",
        encoder=DjangoJSONEncoder,
        default=list,
    )

    class Meta:
        abstract = True

    def retry_if_possible(self):
        return False

    def update_failure_history(self, do_save=True):
        self.failure_history.append(
            {
                "failed": self.failed,
                "failure_reason": self.failure_reason,
                "status": self.status,
            }
        )
        if do_save:
            self.save()

    def reset_for_retry(self):
        if self.failed:
            logger.info(
                "Resetting task %s for retrying",
                self,
            )
            self.update_failure_history(do_save=False)
            self.failed = None
            self.failure_reason = ""
            self.status = "Retrying"
            self.retry_count += 1
            self.save()
            return True
        else:
            self.status = (
                "Task was not marked as failed, so it will "
                "not be reset for retrying."
            )
            self.save()
            logger.warning(
                "Task %s was not marked as failed, so it will not be "
                "reset for retrying",
                self,
            )
            return False


class ImportJob(TaskStatusModel):
    """
    Represents a request by a user to import item(s) from a remote URL
    """

    created_by = models.ForeignKey("auth.User", null=True, on_delete=models.SET_NULL)

    project = models.ForeignKey("concordia.Project", on_delete=models.CASCADE)

    url = models.URLField(verbose_name="Source URL for the entire job")

    def __str__(self):
        return "ImportJob(created_by=%s, project=%s, url=%s)" % (
            self.created_by.username if self.created_by else None,
            self.project.title,
            self.url,
        )


class ImportItem(TaskStatusModel):
    """
    Record of the task status for each Item being imported
    """

    job = models.ForeignKey(ImportJob, on_delete=models.CASCADE, related_name="items")

    url = models.URLField()

    item = models.ForeignKey("concordia.Item", on_delete=models.CASCADE)

    class Meta:
        unique_together = (("job", "item"),)

    def __str__(self):
        return "ImportItem(job=%s, url=%s)" % (self.job, self.url)


class ImportItemAsset(TaskStatusModel):
    """
    Record of the task status for each Asset being imported
    """

    import_item = models.ForeignKey(
        ImportItem, on_delete=models.CASCADE, related_name="assets"
    )

    url = models.URLField()
    sequence_number = models.PositiveIntegerField(validators=[MinValueValidator(1)])

    asset = models.ForeignKey("concordia.Asset", on_delete=models.CASCADE)

    class Meta:
        unique_together = (("import_item", "sequence_number"), ("import_item", "asset"))

    def __str__(self):
        return "ImportItemAsset(import_item=%s, url=%s)" % (self.import_item, self.url)

    def retry_if_possible(self):
        if self.failure_reason == TaskStatusModel.FailureReason.IMAGE:
            max_retries = configuration_value("asset_image_import_max_retries")
            retry_delay = configuration_value("asset_image_import_max_retry_delay")
            if self.retry_count < max_retries and retry_delay > 0:
                if self.reset_for_retry():
                    return tasks.download_asset_task.apply_async(
                        (self.pk,), countdown=retry_delay * 60  # Convert to seconds
                    )
                else:
                    logger.warning(
                        "Task %s was not reset for retrying, so it will not be retried",
                        self,
                    )
                    return False
            else:
                logger.warning(
                    "Task %s has reached the maximum number of retries %s "
                    "and will not be repeated",
                    self,
                    max_retries,
                )
                self.update_failure_history(do_save=False)
                self.failed = timezone.now()
                self.status = (
                    "Maximum number of retries reached while retrying "
                    "image download for asset. The failure reason before retrying "
                    "was {self.failure_reason} and the status was {self.status}"
                )
                self.failure_reason = TaskStatusModel.FailureReason.RETRIES
                self.save()
                return False
        return False
