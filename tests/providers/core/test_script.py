#!/usr/bin/python
# -*- coding: utf-8 -*-

"""Tests for script provider"""

import __builtin__
import json
import logging
import os
import unittest2 as unittest
from urlparse import urlunparse

import mox
from mox import In, IsA, And, IgnoreArg, ContainsKeyValue, Not

# Init logging before we load the database, 3rd party, and 'noisy' modules

from checkmate.utils import init_console_logging
from unittest.case import skip
import checkmate
init_console_logging()
LOG = logging.getLogger(__name__)

from checkmate import test, utils
from checkmate.deployments import Deployment, plan
from checkmate.middleware import RequestContext
from checkmate.providers import base, register_providers
from checkmate.providers.core import script
from checkmate.workflows import create_workflow_deploy


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
