# Creating a specfic error for this, since our pre-commit
# checks will not allow us to test for generic exceptions
class CacheLockedError(Exception):
    def __init__(self, message, details=None):
        super().__init__(message)
        self.details = details


class RateLimitExceededError(Exception):
    pass
