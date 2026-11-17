"""
SIGN-IN PAGE - the student / teacher / staff (and any other rider type) sign-in page.
Change only the right side of each line. (Help: content/words/__init__.py)
"""

WORDS = {
    # ---- Top of the page ----
    "Back": "Back",                          # the arrow at the top left (read out by screen readers)
    "{who} login": "{who} login",            # page title; {who} = Student / Teacher / Staff ...
    "Name": "Name",
    "Connection error. Please check your internet and try again.":
        "Connection error. Please check your internet and try again.",

    # ---- The form ----
    "Enter your name": "Enter your name",    # grey hint inside the name box
    "See map": "See map",                    # the button
    "Please enter your name and ID.": "Please enter your name and ID.",
    "Login failed. Please try again.": "Login failed. Please try again.",
    # (the ID box's label comes from "id_label" in content/user_types.py)
}
