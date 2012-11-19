#!/usr/bin/env python

import gettext
import os
from ConfigParser import ConfigParser
import re

configfile = os.path.join(os.path.dirname(__file__), 'rook.cfg')
config = ConfigParser()
config.read(configfile)

__version__ = config.get("rook", "version")
__release__ = None


def load_release():
    global __release__
    import pkg_resources
    val = "unknown"
    try:
        dist = pkg_resources.get_distribution("rook")
        match = re.search('((\d+\.)+)(\D.+)', dist.version)
        if match:
            val = match.group(match.lastindex)
    except:
        pass
    __release__ = val

load_release()


def version():
    return "%s-%s" % (__version__, __release__)
