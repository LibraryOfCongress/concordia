from django.core.files.storage import default_storage

# This is intentionally aliasing the default storage so we only need to change
# this value in the future if we split storage across multiple buckets:
ASSET_STORAGE = default_storage
