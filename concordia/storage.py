from django.core.files.storage import storages
from django.utils.functional import LazyObject


class LazyAssetStorage(LazyObject):
    def _setup(self):
        self._wrapped = storages["assets"]


class LazyVisualizationStorage(LazyObject):
    def _setup(self):
        self._wrapped = storages["visualizations"]


# This is an intentional alias so we can change this value in the future
# if we need to split storage across multiple buckets
# We use a LazyObject so the value isn't evaluated when the code is loaded,
# which is needed to override the setting during tests

ASSET_STORAGE = LazyAssetStorage()

VISUALIZATION_STORAGE = LazyVisualizationStorage()
