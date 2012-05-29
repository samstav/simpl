#!/usr/bin/env python

import gettext

# This installs the _(...) function as a built-in so all other modules
# don't need to.
gettext.install('checkmate')

__version__ = '0.1'
__release__ = 'alpha'


def version():
    return "%s %s - released on 2012.05.28" % (__version__, __release__)
