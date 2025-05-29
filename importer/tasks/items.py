import os
import re
from logging import getLogger
from urllib.parse import urljoin, urlparse

import requests
from celery import group
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.text import slugify
from django.utils.timezone import now
from requests.exceptions import HTTPError

from concordia.models import Asset, Item, MediaType
from importer import models
from importer.celery import app

from .assets import download_asset_task
from .decorators import update_task_status

#: P1 has generic search / item pages and a number of top-level format-specific
#: “context portals” which expose the same JSON interface.
#: jq 'to_entries[] | select(.value.type == "context-portal") | .key' < manifest.json
ACCEPTED_P1_URL_PREFIXES = [
    "collections",
    "search",
    "item",
    "audio",
    "books",
    "film-and-videos",
    "manuscripts",
    "maps",
    "newspapers",
    "notated-music",
    "photos",
    "websites",
]

logger = getLogger(__name__)

# Tasks


@app.task(
    bind=True,
    autoretry_for=(HTTPError,),
    retry_backoff=60 * 60,
    retry_backoff_max=8 * 60 * 60,
    retry_jitter=True,
    retry_kwargs={"max_retries": 3},
    rate_limit=2,
)
def create_item_import_task(self, import_job_pk, item_url, redownload=False):
    """
    Create an ImportItem record using the provided import job and URL by
    requesting the metadata from the URL

    Enqueues the actual import for the item once we have the metadata
    """

    import_job = models.ImportJob.objects.get(pk=import_job_pk)

    # Load the Item record with metadata from the remote URL:
    resp = requests.get(item_url, params={"fo": "json"}, timeout=30)
    resp.raise_for_status()
    item_data = resp.json()

    item, item_created = Item.objects.get_or_create(
        item_id=get_item_id_from_item_url(item_data["item"]["id"]),
        defaults={"item_url": item_url, "project": import_job.project},
    )

    import_item, import_item_created = import_job.items.get_or_create(
        url=item_url, item=item
    )

    if not item_created and redownload is False:
        # Item has already been imported and we're not redownloading
        # all items
        asset_urls, item_resource_url = get_asset_urls_from_item_resources(
            item.metadata.get("resources", [])
        )
        if item.asset_set.count() >= len(asset_urls):
            # The item has all of its assets, so we can skip it
            logger.warning("Not reprocessing existing item with all asssets: %s", item)
            import_item.update_status(
                f"Not reprocessing existing item with all assets: {item}", do_save=False
            )
            import_item.completed = import_item.last_started = now()
            import_item.task_id = self.request.id
            import_item.full_clean()
            import_item.save()
            return
        else:
            # The item is missing one or more of its assets, so we will reprocess it
            # to import the missing asssets
            logger.warning("Reprocessing existing item %s that is missing assets", item)

    import_item.item.metadata.update(item_data)

    populate_item_from_data(import_item.item, item_data["item"])

    item.full_clean()
    item.save()

    return import_item_task.delay(import_item.pk)


@app.task(bind=True)
def import_item_task(self, import_item_pk):
    i = models.ImportItem.objects.select_related("item").get(pk=import_item_pk)
    return import_item(self, i)


@update_task_status
def import_item(self, import_item):
    # Using transaction.atomic here ensures the data is available in the
    # database for the download_asset_task calls. If we don't do this, some
    # of the tasks could execute before the transaction is committed, causing
    # those tasks to fail since the ImportItemAsset it needs won't be in the database
    with transaction.atomic():
        item_assets = []
        import_assets = []
        item_resource_url = None

        asset_urls, item_resource_url = get_asset_urls_from_item_resources(
            import_item.item.metadata.get("resources", [])
        )
        relative_asset_file_path = "/".join(
            [
                import_item.item.project.campaign.slug,
                import_item.item.project.slug,
                import_item.item.item_id,
            ]
        )

        for sequence, asset_url in enumerate(asset_urls, start=1):
            asset_title = f"{import_item.item.item_id}-{sequence}"
            file_extension = (
                os.path.splitext(urlparse(asset_url).path)[1].lstrip(".").lower()
            )
            item_asset = Asset(
                item=import_item.item,
                campaign=import_item.item.project.campaign,
                title=asset_title,
                slug=slugify(asset_title, allow_unicode=True),
                sequence=sequence,
                media_type=MediaType.IMAGE,
                download_url=asset_url,
                resource_url=item_resource_url,
                storage_image="/".join(
                    [relative_asset_file_path, f"{sequence}.{file_extension}"]
                ),
            )
            # Previously, any asset that raised a validation error was just ignored.
            # We don't want that--we want to see if an asset fails validation
            try:
                item_asset.full_clean()
            except ValidationError as exc:
                raise ValidationError(
                    f"Importing asset with slug '{item_asset.slug}' for "
                    f"item '{item_asset.item}' with resource URL "
                    f"'{item_asset.resource_url}' failed with the following "
                    f"exception: {exc}"
                ) from exc
            item_assets.append(item_asset)

        Asset.objects.bulk_create(item_assets)

        for asset in item_assets:
            import_asset = models.ImportItemAsset(
                import_item=import_item,
                asset=asset,
                url=asset.download_url,
                sequence_number=asset.sequence,
            )
            import_asset.full_clean()
            import_assets.append(import_asset)

        import_item.assets.bulk_create(import_assets)

        import_item.full_clean()
        import_item.save()

    download_asset_group = group(download_asset_task.s(i.pk) for i in import_assets)

    return download_asset_group()


# End tasks


def import_item_count_from_url(import_url):
    """
    Given a loc.gov URL, return count of files from the resources section
    """
    try:
        resp = requests.get(import_url, params={"fo": "json"}, timeout=30)
        resp.raise_for_status()
        item_data = resp.json()
        output = len(item_data["resources"][0]["files"])
        return f"{import_url} - Asset Count: {output}", output
    except Exception as exc:
        return f"Unhandled exception importing {import_url} {exc}", 0


def get_item_info_from_result(result):
    """
    Given a P1 result, return the item ID and URL if it represents a collection
    item

    :return: (item_id, item_url) tuple or None if the URL does not represent a
             supported item type
    """

    ignored_formats = {"collection", "web page"}

    item_id = result["id"]
    original_format = result["original_format"]

    if ignored_formats.intersection(original_format):
        logger.info(
            "Skipping result %s because it contains an unsupported format: %s",
            item_id,
            original_format,
            extra={"data": {"result": result}},
        )
        return

    image_url = result.get("image_url")
    if not image_url:
        logger.info(
            "Skipping result %s because it lacks an image_url",
            item_id,
            extra={"data": {"result": result}},
        )
        return

    item_url = result["url"]

    m = re.search(r"loc.gov/item/([^/]+)", item_url)
    if not m:
        logger.info(
            "Skipping %s because the URL %s doesn't appear to be an item!",
            item_id,
            item_url,
            extra={"data": {"result": result}},
        )
        return

    return m.group(1), item_url


def get_item_id_from_item_url(item_url):
    """
    extracts item id from the item url and returns it
    :param item_url: item url
    :return: item id
    """
    if item_url.endswith("/"):
        item_id = item_url.split("/")[-2]
    else:
        item_id = item_url.split("/")[-1]

    return item_id


def import_items_into_project_from_url(
    requesting_user, project, import_url, redownload=False
):
    """
    Given a loc.gov URL, return the task ID for the import task
    """

    parsed_url = urlparse(import_url)

    m = re.match(
        r"^/(%s)/" % "|".join(map(re.escape, ACCEPTED_P1_URL_PREFIXES)), parsed_url.path
    )
    if not m:
        raise ValueError(
            f"{import_url} doesn't match one of the known importable patterns"
        )
    url_type = m.group(1)

    import_job = models.ImportJob(
        project=project, created_by=requesting_user, url=import_url
    )
    import_job.full_clean()
    import_job.save()

    if url_type == "item":
        create_item_import_task.delay(import_job.pk, import_url, redownload)
    else:
        # Both collections and search results return the same format JSON
        # reponse so we can use the same code to process them:
        from .collections import import_collection_task

        import_collection_task.delay(import_job.pk, redownload)

    return import_job


def populate_item_from_data(item, item_info):
    """
    Populates a Concordia.Item from the data retrieved from a loc.gov URL
    """

    for k in ("title", "description"):
        v = item_info.get(k)
        if v:
            setattr(item, k, v)

    # FIXME: this was never set before so we don't have selection logic:
    thumb_urls = [i for i in item_info["image_url"] if ".jpg" in i]
    if thumb_urls:
        item.thumbnail_url = urljoin(item.item_url, thumb_urls[0])


def get_asset_urls_from_item_resources(resources):
    """
    Given a loc.gov JSON response, return the list of asset URLs matching our
    criteria (JPEG, largest version available)
    """

    assets = []
    try:
        item_resource_url = resources[0]["url"] or ""
    except (IndexError, KeyError):
        item_resource_url = ""

    for resource in resources:
        # The JSON response for each file is a list of available image versions
        # we will attempt to save the highest resolution jpg, falling back to
        # to the highest resolution gif if there are none

        for item_file in resource.get("files", []):
            candidates = []
            backup_candidates = []

            for variant in item_file:

                if any(i for i in ("url", "height", "width") if i not in variant):
                    continue

                url = variant["url"]
                height = variant["height"]
                width = variant["width"]
                mimetype = variant.get("mimetype")

                # We prefer jpgs, but if there are none,
                # we'll fallback to gifs
                if mimetype == "image/jpeg":
                    candidates.append((url, height * width))
                elif mimetype == "image/gif":
                    backup_candidates.append((url, height * width))

            if candidates:
                candidates.sort(key=lambda i: i[1], reverse=True)
                assets.append(candidates[0][0])
            elif backup_candidates:
                backup_candidates.sort(key=lambda i: i[1], reverse=True)
                assets.append(backup_candidates[0][0])

    return assets, item_resource_url
