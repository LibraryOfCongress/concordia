from django.contrib import messages

ASSETS_PER_PAGE = 36
PROJECTS_PER_PAGE = 36
ITEMS_PER_PAGE = 36
URL_REGEX = r"http[s]?://"

MESSAGE_LEVEL_NAMES = dict(
    zip(
        messages.DEFAULT_LEVELS.values(),
        map(str.lower, messages.DEFAULT_LEVELS.keys()),
        strict=False,
    )
)
