"""
"BUS SCHEDULE" POP-UP - opened from the menu on the rider map (students, teachers, staff).
Change only the right side of each line. (Help: content/words/__init__.py)
"""

WORDS = {
    "Bus schedule": "Bus schedule",               # pop-up title
    "Today": "Today",                             # "Today · Sunday"
    "Close": "Close",
    "Route": "Route",
    "Morning": "Morning",                         # tab
    "Afternoon": "Afternoon",                     # tab
    "Reaches campus": "Reaches campus",           # the time shown for morning buses
    "Leaves campus": "Leaves campus",             # the time shown for afternoon buses
    "No bus today": "No bus today",
    "Could not load. Check your internet.": "Could not load. Check your internet.",
    "AM": "AM",
    "PM": "PM",
}

# Day names, used in the pop-up ("Today · Sunday") and the backend's Schedules tab.
# The week starts on Saturday in Bangladesh. Change only the right side.
DAY_NAMES = {
    "sat": "Saturday",
    "sun": "Sunday",
    "mon": "Monday",
    "tue": "Tuesday",
    "wed": "Wednesday",
    "thu": "Thursday",
    "fri": "Friday",
}
