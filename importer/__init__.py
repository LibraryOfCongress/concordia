"""
Design
======

The importer currently only supports loading items from www.loc.gov

General goals:

* All state is stored in the database and visible for reporting
* Celery tasks are ephemeral and while they may be configured to retry they will
  always check the database to avoid conflicts and use transactions to prevent
  race conditions

The import process works like this:

1. A user submits a request to import a URL. This can be an item page, a
   collection page, or an arbitrary search result set.
2. An ImportJob is created which records that request and a background Celery
   task is launched to determine what items it contains (this can potentially be
   well into the thousands)
3. For collection and search URLs (which share a common data format) the task
   loads the JSON representation and queues item import tasks for each item. For
   item URLs, the item import task is directly queued.
4. When the item import task runs it creates an ImportItem record, loads the
   item metadata, and creates ImportItem and ImportItemAsset records to track
   subsequent import work. It creates the Item and Asset records which will hold
   the actual item data as well because this allows review while a large import
   is in progress and our community managers quality review items before making
   them visible to the community. The asset import tasks are queued at the end
   of this step.
5. When the asset import task runs, it downloads the remote file and saves it in
   Concordia's working storage. Each asset is processed independently so
   completed downloads will not consume local storage until the [potentially
   very large] item has completely downloaded, which could potentially take
   hours or days if there are service availability issues requiring retries.
6. When all of the asset tasks are completed the item will be marked as
   completed.
7. When all of the item tasks are completed the job will be marked as completed.
"""
