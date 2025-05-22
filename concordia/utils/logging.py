from typing import Union


def get_logging_user_id(user) -> Union[int, str]:
    """
    Return a consistent identifier for logging purposes.

    Args:
        user (User): A Django user object (possibly anonymous).

    Returns:
        Union[int, str]: User's ID or "anonymous" if unauthenticated.
    """
    return getattr(user, "id", None) if user.is_authenticated else "anonymous"
