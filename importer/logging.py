import logging

from celery import current_task


class CeleryTaskIDFilter(logging.Filter):
    def filter(self, record):
        task = current_task
        if task and task.request.id:
            record.task_id = f"/[{task.request.id}]"
        else:
            record.task_id = ""
        # This just tells the logger to not discard this record
        return True
