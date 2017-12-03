# -*- coding: utf-8 -*-
"""Translate HHS+ events to Python code

Copyright (C) 2017 Radomir Matveev GPL 3.0+
"""

# --------------------------------------------------------------------------- #
# Define classes
# --------------------------------------------------------------------------- #
class GeneratedEvent(object):
    """The base class for all event classes generated with event2py.
    
    You should inherit from this class to create the events.Event class 
    which all generated events require. Alternatively, you could also create an alias
    to this class in the events package, like so:
        
        events.Event = event2py.GeneratedEvent
    """
    
    def __init__(self):
        # the name of the event is the same as the name of the class
        self.name = self.__class__.__name__

        
# --------------------------------------------------------------------------- #
# Define package contents
# --------------------------------------------------------------------------- #
from translator import *
