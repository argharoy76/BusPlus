"""
Rider types (Student, Teacher, ... ) as set in content/user_types.py, checked once at start-up.

Everything that depends on "who rides the bus" reads from here: the start-page
buttons, the sign-in pages and live maps (/<key>/login, /<key>/dashboard),
which buses each type sees, and the backend's Buses and Users tabs.
"""

import re

from content.user_types import DRIVER, RIDER_TYPES

# Words already used in web addresses, so they can't be rider type keys.
RESERVED_KEYS = {"driver", "admin", "backend", "api", "static", "health"}
REQUIRED_FIELDS = ("label", "plural", "id_label", "icon", "color")


def _check_rider_types() -> None:
    """Stop with a clear message if content/user_types.py has a mistake."""
    if not RIDER_TYPES:
        raise ValueError("content/user_types.py: RIDER_TYPES needs at least one type (e.g. student).")
    for key, info in RIDER_TYPES.items():
        where = f'content/user_types.py, type "{key}"'
        if not re.fullmatch(r"[a-z]{2,20}", key) or key in RESERVED_KEYS:
            raise ValueError(f"{where}: the key must be 2-20 lowercase letters and not one of {sorted(RESERVED_KEYS)}.")
        missing = [f for f in REQUIRED_FIELDS if not str(info.get(f, "")).strip()]
        if missing:
            raise ValueError(f"{where}: missing {', '.join(missing)}.")
        if not re.fullmatch(r"#[0-9A-Fa-f]{6}", info["color"]):
            raise ValueError(f'{where}: color must look like "#059669".')


_check_rider_types()

RIDER_KEYS: tuple[str, ...] = tuple(RIDER_TYPES)   # e.g. ("student", "teacher")
DEFAULT_RIDER_KEY = RIDER_KEYS[0]                   # new buses are for this type


def rider_info(key: str) -> dict | None:
    """Label, plural, id_label, icon and color of a rider type (None if there is no such type)."""
    return RIDER_TYPES.get(key)


__all__ = ["DEFAULT_RIDER_KEY", "DRIVER", "RIDER_KEYS", "RIDER_TYPES", "rider_info"]
