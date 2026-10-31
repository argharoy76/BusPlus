"""
The words of the website, read from the content/words/ folder.

Every page has one file there with a WORDS list:   "Original text": "Text shown on the page"
The code always asks for the ORIGINAL text (left side) and gets back whatever the
right side says now, so changing the right side changes the page.

    Python (server messages):   say("Driver '{name}' added.", name="Karim")
    HTML templates:             {% set t = words("rider_map") %}  ...  {{ t("Home") }}
    JavaScript:                 const RT = words("rider_map");   ...  RT("Home saved")

{name}-style blanks are filled in by the code. A missing or misspelled blank never
crashes the site: it is simply shown as written.
"""

import importlib
import string

# One file per page in content/words/ (the file name without .py).
PAGES = (
    "login_pages",
    "rider_map",
    "driver_map",
    "bus_schedule",
    "map",
    "backend_login",
    "backend",
    "server_messages",
)

WORDS: dict[str, dict[str, str]] = {
    page: importlib.import_module(f"content.words.{page}").WORDS for page in PAGES
}


class _KeepUnknown(dict):
    """Leaves {blank} as it is when the code has no value for it."""

    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def fill(text: str, **values) -> str:
    """Put values into the {blanks} of a text. Broken braces are shown as typed."""
    if not values:
        return text
    try:
        return string.Formatter().vformat(text, (), _KeepUnknown(values))
    except (ValueError, IndexError, AttributeError):
        return text


def word(page: str, original: str, **values) -> str:
    """The text the page shows for `original` (falls back to the original itself)."""
    return fill(WORDS.get(page, {}).get(original, original), **values)


def words(page: str):
    """A t(original, **values) function for one page (used by the HTML templates)."""
    if page not in WORDS:
        raise KeyError(f"No words file content/words/{page}.py")
    return lambda original, **values: word(page, original, **values)


def page_words(*pages: str) -> dict[str, dict[str, str]]:
    """The words of some pages, sent to the browser for the JavaScript (window.WORDS)."""
    return {page: WORDS[page] for page in pages}


def say(original: str, **values) -> str:
    """A message from the server (errors, "saved", arrival alerts): content/words/server_messages.py."""
    return word("server_messages", original, **values)
