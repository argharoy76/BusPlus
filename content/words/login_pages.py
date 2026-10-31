"""
SIGN-IN PAGES - the driver sign-in page and the student / teacher (and any other rider type) sign-in page.
Change only the right side of each line. (Help: content/words/__init__.py)
"""

WORDS = {
    # ---- On both pages ----
    "Back": "Back",                          # the arrow at the top left (read out by screen readers)
    "{who} login": "{who} login",            # page title; {who} = Driver / Student / Teacher ...
    "Name": "Name",
    "Connection error. Please check your internet and try again.":
        "Connection error. Please check your internet and try again.",

    # ---- Student / teacher sign-in ----
    "Enter your name": "Enter your name",    # grey hint inside the name box
    "See map": "See map",                    # the button
    "Please enter your name and ID.": "Please enter your name and ID.",
    "Login failed. Please try again.": "Login failed. Please try again.",
    # (the ID box's label comes from "id_label" in content/user_types.py)

    # ---- Driver sign-in ----
    "Your name": "Your name",                # grey hint inside the name box
    "Route": "Route",
    "Select route": "Select route",
    "PIN": "PIN",
    "Log in": "Log in",                      # the button
    "Wrong name or PIN. Please try again.": "Wrong name or PIN. Please try again.",
}
