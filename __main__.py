# -*- coding: utf-8 -*-
"""Translate HHS+ events to Python code

Copyright (C) 2017 Radomir Matveev GPL 3.0+
"""

# --------------------------------------------------------------------------- #
# Import libraries
# --------------------------------------------------------------------------- #
import logging
from pathlib import Path

import translator


# --------------------------------------------------------------------------- #
# Execute
# --------------------------------------------------------------------------- #
logging.basicConfig(level=logging.INFO)
print("Running event2py")
events = Path(__file__).parent.parent / "Events"
assert events.exists()
vefile = events / "FunctionLibrary/PutPersonInLocationByName.ve.xml"
# vefile = events / "Location/Beach/BeachJetSki.ve.xml"
assert vefile.exists()
event = translator.VisualEventModel.from_path(vefile)
script = event.to_script()
print("script:\n")
print(script)
