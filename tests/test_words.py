"""
Checks that the content/words/ files and the code agree:
  * every text the code asks for is listed in its page's words file (so all of it is editable)
  * every line in a words file is still used by the code (no dead lines)
  * the right side only uses {blanks} that the code fills in
"""

import ast
import json
import re
import string
from pathlib import Path

from services.words import PAGES, WORDS, fill, say, words

ROOT = Path(__file__).resolve().parent.parent

# Which look-up name each JavaScript file uses, and for which page.
JS_FILES = {
    "static/js/student_tracker.js": ("RT", "rider_map"),
    "static/js/driver_tracker.js": ("DT", "driver_map"),
    "static/js/google_maps_helper.js": ("MT", "map"),
    "static/js/schedule.js": ("ST", "bus_schedule"),
    "static/js/admin.js": ("AT", "backend"),
}
STRING = r'"((?:[^"\\\n]|\\.)*)"'


def _uses() -> dict[str, set[str]]:
    """page -> every original text the code asks for."""
    used: dict[str, set[str]] = {page: set() for page in PAGES}

    for template in (ROOT / "templates").glob("*.html"):
        src = template.read_text(encoding="utf-8")
        pages = re.findall(r'\{%-?\s*set\s+t\s*=\s*words\("(\w+)"\)', src)
        calls = re.findall(r"\bt\(\s*" + STRING, src)
        if calls:
            assert len(pages) == 1, f"{template.name}: needs exactly one {{% set t = words(...) %}}"
            used[pages[0]].update(json.loads(f'"{c}"') for c in calls)

    for rel, (name, page) in JS_FILES.items():
        src = (ROOT / rel).read_text(encoding="utf-8")
        used[page].update(json.loads(f'"{c}"') for c in re.findall(rf"\b{name}\(\s*" + STRING, src))

    code = [*ROOT.glob("controllers/*.py"), *ROOT.glob("services/*.py"), *ROOT.glob("models/*.py"), ROOT / "app.py"]
    for py in [p for p in code if p.name != "words.py"]:       # words.py only shows examples
        src = py.read_text(encoding="utf-8")
        assert not re.search(r"\bsay\(\s*f[\"']", src), f"{py.name}: say() needs a plain text, use {{blanks}}"
        used["server_messages"].update(ast.literal_eval(f'"{c}"') for c in re.findall(r"\bsay\(\s*" + STRING, src))
    return used


def _blanks(text: str) -> set[str]:
    return {name for _, name, _, _ in string.Formatter().parse(text) if name}


def test_every_text_is_in_the_content_folder():
    for page, originals in _uses().items():
        missing = sorted(originals - set(WORDS[page]))
        assert not missing, f"content/words/{page}.py is missing: {missing}"


def test_no_unused_lines_in_the_content_folder():
    for page, originals in _uses().items():
        unused = sorted(set(WORDS[page]) - originals)
        assert not unused, f"content/words/{page}.py has lines nothing uses: {unused}"


def test_blanks_match():
    for page, table in WORDS.items():
        for original, shown in table.items():
            extra = _blanks(shown) - _blanks(original)
            assert not extra, f"content/words/{page}.py: {original!r} uses unknown blanks {extra}"


def test_lookup_helpers():
    assert fill("{name} added.", name="Karim") == "Karim added."
    assert fill("{nmae} added.", name="Karim") == "{nmae} added."      # typo: shown as written
    assert fill("50% {off", x=1) == "50% {off"                          # broken braces: no crash
    assert words("rider_map")("not listed") == "not listed"
    assert say("not listed") == "not listed"


def test_changing_a_word_changes_the_page(client, monkeypatch):
    monkeypatch.setitem(WORDS["login_pages"], "See map", "Open the map")
    original = "Please enter your name and {id_label}."
    monkeypatch.setitem(WORDS["server_messages"], original, "Name and {id_label}, please.")
    assert "Open the map" in client.get("/student/login").get_data(as_text=True)
    reply = client.post("/api/auth/student/login", json={"full_name": "", "rider_id": ""}).get_json()
    assert reply["message"] == "Name and Student ID, please."
