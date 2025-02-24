class RateLimitExceededError(Exception):
    def __init__(self, user_message="Rate Limit Exceeded", *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.user_message = user_message
