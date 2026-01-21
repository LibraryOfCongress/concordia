import unicodedata

from django import template
from django.template.defaultfilters import stringfilter
from django.utils.text import Truncator, add_truncation_text

register = template.Library()


class WordBreakTruncator(Truncator):
    def word_break(self, num: int, truncate: str | None = None) -> str:
        """
        Return the text truncated to no longer than the given number of
        characters, cutting at the most recent word break.

        This method follows the behavior of `django.utils.text.Truncator`, but
        differs by ensuring the cut occurs on a word boundary when possible.
        It also counts only non-combining Unicode code points toward the
        character limit.

        Args:
            num (int): Maximum length of the resulting string, including any
                truncation text.
            truncate (str | None): The text to append when truncation occurs.
                If not provided, the default from `add_truncation_text` is used.

        Returns:
            str: The truncation marker
            appended.
        """
        self._setup()
        length = int(num)
        text = unicodedata.normalize("NFC", self._wrapped)

        # Calculate the length to truncate to (max length - end_text length).
        truncate_len = length
        for char in add_truncation_text("", truncate):
            if not unicodedata.combining(char):
                truncate_len -= 1
                if truncate_len == 0:
                    break
        return self._text_word_break(length, truncate, text, truncate_len)

    def _text_word_break(
        self, length: int, truncate: str | None, text: str, truncate_len: int
    ) -> str:
        """
        Truncate a string after a given number of characters, cutting at the
        most recent word break.

        Args:
            length (int): Maximum length of the resulting string, including any
                truncation text.
            truncate (str | None): The text to append when truncation occurs.
            text (str): The normalized source string.
            truncate_len (int): The effective content length budget after
                subtracting the truncation text length.
        Returns:
            str: The original string if no truncation is needed; otherwise the
            truncated string with truncation text appended.
        """
        s_len = 0
        end_index = None
        for i, char in enumerate(text):
            if unicodedata.combining(char):
                # Do not count combining characters toward the visible length.
                continue
            s_len += 1
            if end_index is None and s_len > truncate_len:
                end_index = i
            if s_len > length:
                # Return the truncated string at the prior word boundary.
                return add_truncation_text(
                    " ".join(text[: end_index or 0].split()[:-1]), truncate
                )

        # Return the original string since no truncation was necessary.
        return text


@register.filter(is_safe=True)
@stringfilter
def truncatechars_on_word_break(value: str, arg: int | str) -> str:
    """
    Truncate a string after a given number of characters, cutting at the most
    recent word break.

    Behavior:
        - Counts only non-combining Unicode code points toward the limit.
        - If truncation occurs, appends a truncation marker.
        - Preserves whole words by backing up to the nearest word boundary.

    Usage:
        In a template:

            {% load truncation %}
            {{ long_text|truncatechars_on_word_break:120 }}

        In Python:

            truncatechars_on_word_break("alpha beta gamma", 8)
            # returns "alpha […]" (truncated at a word boundary)

    Args:
        value (str): The source text to truncate.
        arg (int | str): Maximum length. If a string is provided, it is cast
            to an integer. Invalid values cause the original text to be
            returned unchanged.

    Returns:
        str: The truncated string, or the original string if no truncation is
        needed or the argument is invalid.
    """
    try:
        length = int(arg)
    except ValueError:
        # Invalid literal for int(); fail silently and return original.
        return value
    return WordBreakTruncator(value).word_break(length, "[…]")
