"""
COLOURS - hex codes like "#2563EB" (pick one at https://htmlcolorcodes.com).
"""

# The look of the whole website (start page, sign-in pages, maps, pop-ups and backend).
THEME = {
    "brand": "#0866FF",            # logo square, main buttons, links, selected tabs, browser bar on phones
    "page_background": "#F4F6F9",  # behind the cards on the start and sign-in pages
    "text": "#0F172A",             # normal text
    "muted_text": "#64748B",       # small grey text (hints, labels, second lines)
    "danger": "#DC2626",           # delete buttons, errors, "Sign out"
    "bus_trail": "#DC2626",        # the line drawn behind a moving bus on the map
}

# A new bus gets the first colour from this list that no other bus uses yet.
# (Each bus's colour can also be changed in the backend: Buses > Edit.)
BUS_COLORS = [
    "#E11D48", "#0891B2", "#EA580C", "#7C3AED", "#16A34A",
    "#DB2777", "#CA8A04", "#4F46E5", "#0D9488", "#9333EA",
]

# A new route gets the first colour from this list that no other route uses yet.
ROUTE_COLORS = [
    "#2563EB", "#059669", "#D97706", "#DB2777", "#7C3AED", "#0891B2", "#65A30D", "#DC2626",
]
