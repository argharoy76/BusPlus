"""
WHO USES THE APP - the buttons on the start page.

The Driver button is always first. After it comes one button for every entry
in RIDER_TYPES below. Each rider type automatically gets EVERYTHING:
  * a button on the start page
  * its own sign-in page   (/<key>/login)   asking for name + ID
  * its own live map       (/<key>/dashboard) showing only "its" buses
  * a choice in the backend's Buses tab ("This bus is for: ...")
  * its people listed in the backend's Users tab

HOW TO ADD A NEW TYPE (example: Passenger)
  1. Copy one block below, e.g. the "teacher" block.
  2. Paste it under the last block and change the values:
        "passenger": {
            "label": "Passenger",          # one person, on buttons and titles
            "plural": "Passengers",        # many people, in the backend
            "id_label": "Phone number",    # what the sign-in page asks for as the ID
            "icon": "🧳",                  # any emoji
            "color": "#EA580C",            # button colour
        },
  3. Save and restart the app. Then, in the backend, set some buses to
     "Passengers" so passengers have buses to see.

HOW TO REMOVE A TYPE: delete its block (buses that were for it disappear
from the maps until you give them another type in the backend).

The KEY (the word before the colon, like "passenger") is used in web
addresses: use lowercase English letters only, no spaces.
"""

RIDER_TYPES = {
    "student": {
        "label": "Student",
        "plural": "Students",
        "id_label": "Student ID",
        "icon": "🎓",
        "color": "#059669",
    },
    "teacher": {
        "label": "Teacher",
        "plural": "Teachers",
        "id_label": "Teacher ID",
        "icon": "👩‍🏫",
        "color": "#7C3AED",
    },
}

# The Driver button on the start page.
DRIVER = {
    "label": "Driver",
    "icon": "👨‍✈️",
    "color": "#0866FF",
}
