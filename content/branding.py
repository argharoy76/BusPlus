"""
NAME AND LOGO - shown on every page (start page, sign-in pages, maps, backend, browser tab).
"""

# The app's name: big title on the start page, top of the maps and menus, browser tab, backend.
APP_NAME = "BusPlus"

# The university: under the app name on the start page and in the browser tab.
UNIVERSITY_NAME = "Khulna University"

# The logo: this emoji on a rounded square in the brand colour (content/colors.py, THEME "brand").
# It is used on the start page, sign-in pages, map buttons, driver button, backend and browser tab icon.
LOGO_EMOJI = "🚌"

# Browser tab title. {app} = APP_NAME, {university} = UNIVERSITY_NAME, {page} = the page's own name.
TAB_TITLE = "{page} · {app}"
START_PAGE_TAB_TITLE = "{app} · {university}"
