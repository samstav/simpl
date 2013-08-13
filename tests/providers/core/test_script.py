#!/usr/bin/python
# -*- coding: utf-8 -*-
# pylint: disable=C0103,C0111,R0903,R0904,W0212,W0232
'''Tests for script provider'''

import logging
import unittest

from checkmate import test
from checkmate.providers.core import script

LOG = logging.getLogger(__name__)


class TestScriptProvider(test.ProviderTester):

    klass = script.Provider


if __name__ == '__main__':

    # Run tests. Handle our parameters separately

    import sys
    args = sys.argv[:]

    # Our --debug means --verbose for unitest

    if '--debug' in args:
        args.pop(args.index('--debug'))
        if '--verbose' not in args:
            args.insert(1, '--verbose')
    unittest.main(argv=args)
