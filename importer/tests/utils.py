from django.utils.text import slugify

from concordia.tests.utils import create_asset, create_item, create_project
from importer.models import ImportItem, ImportItemAsset, ImportJob


def create_import_job(*, project=None, **kwargs):
    # project is a concordia.models.Project instance
    if project is None:
        project = create_project()
    import_job = ImportJob(project=project, **kwargs)
    import_job.save()
    return import_job


def create_import_item(item=None, project=None, import_job=None, **kwargs):
    # item is a concordia.models.Item instance
    # project is a concordia.models.Project instance
    # import_job is an importer.models.ImportJob instance
    if import_job is None:
        import_job = create_import_job(project=project)
    if item is None:
        item = create_item(project=import_job.project)
    import_item = ImportItem(item=item, job=import_job, **kwargs)
    import_item.save()
    return import_item


def create_import_asset(
    sequence_number,
    asset=None,
    item=None,
    import_item=None,
    project=None,
    import_job=None,
    **kwargs,
):
    # asset is a concordia.models.Asset instance
    # item is a concordia.models.Item instance
    # import_item is an importer.models.ImportItem instance
    # project is a concordia.models.Project instance
    # import_job is an importer.models.ImportJob instance
    if import_item is None:
        import_item = create_import_item(
            item=item, import_job=import_job, project=project
        )
    if asset is None:
        item_slug = slugify(import_item.item.title)
        slug = f"{item_slug}-{sequence_number}"
        asset = create_asset(item=import_item.item, slug=slug)
    import_asset = ImportItemAsset(
        sequence_number=sequence_number, asset=asset, import_item=import_item, **kwargs
    )
    import_asset.save()
    return import_asset
