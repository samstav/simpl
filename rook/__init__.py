#!/usr/bin/env python
import gettext
import os
from ConfigParser import ConfigParser
import re

configfile = os.path.join(os.path.dirname(__file__), 'rook.cfg')
config = ConfigParser()
config.read(configfile)

__version__ = config.get("rook", "version")


def version():
    '''Return rook server version as a string.'''
    return __version__
