class ImageImportFailure(Exception):
    """
    Raised when an image import operation fails.

    This exception signals a failure while importing or downloading an asset
    image. Callers should include a concise human-readable reason in the
    exception message to aid in debugging and logging.
    """

    pass
