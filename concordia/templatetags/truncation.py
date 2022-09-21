import unicodedata

from django import template
from django.template.defaultfilters import stringfilter
from django.utils.text import Truncator

register = template.Library()


class WordBreakTruncator(Truncator):
    def word_break(self, num, truncate=None):
        """
        Return the text truncated to be no longer than the specified number
        of characters, but truncated on the most recent word break.
        `truncate` specifies what should be used to notify that the string has
        been truncated, defaulting to a translatable string of an ellipsis.
        """
        self._setup()
        length = int(num)
        text = unicodedata.normalize("NFC", self._wrapped)

        # Calculate the length to truncate to (max length - end_text length)
        truncate_len = length
        for char in self.add_truncation_text("", truncate):
            if not unicodedata.combining(char):
                truncate_len -= 1
                if truncate_len == 0:
                    break
        return self._text_word_break(length, truncate, text, truncate_len)

    def _text_word_break(self, length, truncate, text, truncate_len):
        """
        Truncate a string after a certain number of chars on the most recent
        word break
        """
        s_len = 0
        end_index = None
        for i, char in enumerate(text):
            if unicodedata.combining(char):
                # Don't consider combining characters
                # as adding to the string length
                continue
            s_len += 1
            if end_index is None and s_len > truncate_len:
                end_index = i
            if s_len > length:
                # Return the truncated string
                return self.add_truncation_text(
                    " ".join(text[: end_index or 0].split()[:-1]), truncate
                )

        # Return the original string since no truncation was necessary
        return text


@register.filter(is_safe=True)
@stringfilter
def truncatechars_on_word_break(value, arg):
    """
    Truncate a string after `arg` number of characters, truncating
    on the most recent word break.
    """
    try:
        length = int(arg)
    except ValueError:  # Invalid literal for int().
        return value  # Fail silently.
    return WordBreakTruncator(value).word_break(length, "[…]")
