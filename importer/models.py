"""
See the module-level docstring for implementation details
"""

from django.core.validators import MinValueValidator
from django.db import models

# FIXME: these classes should have names which more accurately represent what they do


class TaskStatusModel(models.Model):
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

    class Meta:
        abstract = True


class ImportJob(TaskStatusModel):
    """
    Represents a request by a user to import item(s) from a remote URL
    """

    created_by = models.ForeignKey("auth.User", null=True, on_delete=models.SET_NULL)

    project = models.ForeignKey("concordia.Project", on_delete=models.CASCADE)

    url = models.URLField(verbose_name="Source URL for the entire job")

    def __str__(self):
        return "ImportJob(created_by=%s, project=%s, url=%s)" % (
            self.created_by.username,
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
