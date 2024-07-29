from concordia.tests.utils import create_project
from importer.models import ImportJob


def create_import_job(*, project=None, **kwargs):
    if project is None:
        project = create_project()
    import_job = ImportJob(project=project, **kwargs)
    import_job.save()
    return import_job
