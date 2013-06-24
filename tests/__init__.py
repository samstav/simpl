#!/usr/bin/env python
'''Developer (non-UI) tests belong here'''

import os
# isolate tests from environment
for key in os.environ.keys():
    if key.startswith('CHECKMATE_') or key.startswith('CELERY_'):
        del os.environ[key]

os.environ['CHECKMATE_CONNECTION_STRING'] = 'sqlite://'
from checkmate import celeryconfig
reload(celeryconfig)
