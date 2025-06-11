from typing import Any


def get_logging_user_id(user: Any) -> str:
    """
    Return a consistent identifier for logging purposes.

    Args:
        user (Any): A Django user object (possibly anonymous).

    Returns:
        user_id (str): User's ID or "anonymous" if unauthenticated, represents
                         the Concordia anonymous user, or has no ID.
    """
    if not getattr(user, "is_authenticated", False):
        return "anonymous"

    if getattr(user, "username", None) == "anonymous":
        return "anonymous"

    user_id = getattr(user, "id", None)
    if user_id is None:
        return "anonymous"

    return str(user_id)
