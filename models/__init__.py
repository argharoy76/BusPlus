"""
BusPlus data models.

  records.py     database tables (Flask-SQLAlchemy)
  route.py       BusRoute / BusStop used while the app runs
  bus.py         Bus (setup + live position)
  user.py        DriverUser (hashed PIN, one-phone lock)
  seed_data.py   built-in routes/buses written to an empty database
  route_paths.py road lines of the built-in routes
"""
