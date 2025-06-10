"""
See the module-level docstring for implementation details
"""

from logging import getLogger

from django.core.serializers.json import DjangoJSONEncoder
from django.core.validators import MinValueValidator
from django.db import models
from django.urls import reverse
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
        help_text="Number of times the task was retried", default=0, blank=True
    )

    failure_history = models.JSONField(
        help_text="Information about previous failures of the task, if any",
        encoder=DjangoJSONEncoder,
        default=list,
        blank=True,
    )

    status_history = models.JSONField(
        help_text="Previous statuses on the task, if any",
        encoder=DjangoJSONEncoder,
        default=list,
        blank=True,
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

    def update_status(self, status, do_save=True):
        self.status_history.append(
            {
                "status": self.status,
                "timestamp": self.modified,
            }
        )
        self.status = status
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
            self.update_status("Retrying", do_save=False)
            self.retry_count += 1
            self.save()
            return True
        else:
            new_status = (
                "Task was not marked as failed, so it will "
                "not be reset for retrying."
            )
            self.update_status(new_status)
            logger.warning(
                "Task %s was not marked as failed, so it will not be "
                "reset for retrying",
                self,
            )
            return False


class BatchedJob(TaskStatusModel):
    # Allows grouping jobs by batch.
    # `batch` is used by the task system to group jobs
    # and run them in smaller groups rather than spawning
    # an arbitrarily large number at once
    # It's also used to group jobs in the admin, allowing
    # filtering to see all the jobs spawned by a particular
    # action
    batch = models.UUIDField(blank=True, null=True, editable=False)

    class Meta:
        abstract = True

    @classmethod
    def get_batch_admin_url(cls, batch):
        if not batch:
            raise ValueError("A batch value must be provided.")

        app_label = cls._meta.app_label
        model_name = cls._meta.model_name

        admin_url = reverse(f"admin:{app_label}_{model_name}_changelist")

        return f"{admin_url}?batch={batch}"

    @property
    def batch_admin_url(self):
        # Allows getting the batch url from an instance, automatically
        # using self.batch rather than needing to call the class method
        # get_batch_admin_url if you have an instance
        return self.__class__.get_batch_admin_url(self.batch) if self.batch else None


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
                    return tasks.assets.download_asset_task.apply_async(
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
                    "Task %s has reached the maximum number of retries (%s) "
                    "and will not be repeated",
                    self,
                    max_retries,
                )
                self.update_failure_history(do_save=False)
                self.failed = timezone.now()
                new_status = (
                    "Maximum number of retries reached while retrying "
                    "image download for asset. The failure reason before retrying "
                    f"was {self.failure_reason} and the status was {self.status}"
                )
                self.update_status(new_status, do_save=False)
                self.failure_reason = TaskStatusModel.FailureReason.RETRIES
                self.save()
                return False
        return False


class VerifyAssetImageJob(BatchedJob):
    asset = models.ForeignKey("concordia.Asset", on_delete=models.CASCADE)

    def __str__(self):
        return f"VerifyAssetImageJob for {self.asset}"

    class Meta:
        unique_together = (("asset", "batch"),)


class DownloadAssetImageJob(BatchedJob):
    asset = models.ForeignKey("concordia.Asset", on_delete=models.CASCADE)

    def __str__(self):
        return f"DownloadAssetImageJob for {self.asset}"

    class Meta:
        unique_together = (("asset", "batch"),)
