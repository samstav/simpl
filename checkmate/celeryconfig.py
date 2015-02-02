# Copyright (c) 2011-2015 Rackspace US, Inc.
# All Rights Reserved.
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

"""This is where celery picks up its settings."""

import copy
import json
import logging
import os
import sys


LOG = logging.getLogger(__name__)

# XXX: Enable back-ported error propagation for chords. Not needed
# after update to Celery 3.1 as its the default behavior
CELERY_CHORD_PROPAGATES = True

# For debugging, thise make all calls synchronous
if '--eager' in sys.argv:
    CELERY_ALWAYS_EAGER = True
else:
    CELERY_ALWAYS_EAGER = os.environ.get("CELERY_ALWAYS_EAGER",
                                         "false").lower() in ["true", "1"]
if CELERY_ALWAYS_EAGER:
    LOG.warning("Celery is running synchronously because the "
                "CELERY_ALWAYS_EAGER setting is true")

if 'CHECKMATE_CELERY_LOGCONFIG' in os.environ:
    CHECKMATE_CELERY_LOGCONFIG = os.environ.get('CHECKMATE_CELERY_LOGCONFIG')
else:
    CHECKMATE_CELERY_LOGCONFIG = "/etc/default/checkmate-celeryqueue-log.conf"


if 'CHECKMATE_BROKER_URL' in os.environ:
    BROKER_URL = os.environ['CHECKMATE_BROKER_URL']
elif 'CHECKMATE_BROKER_HOST' in os.environ:
    BROKER_INFO = {
        'username': os.environ.get('CHECKMATE_BROKER_USERNAME'),
        'password': os.environ.get('CHECKMATE_BROKER_PASSWORD'),
        'host': os.environ.get('CHECKMATE_BROKER_HOST', 'localhost'),
        'port': os.environ.get('CHECKMATE_BROKER_PORT', '5672'),
    }
    BROKER_URL = "amqp://%s:%s@%s:%s/checkmate" % (BROKER_INFO['username'],
                                                   BROKER_INFO['password'],
                                                   BROKER_INFO['host'],
                                                   BROKER_INFO['port'])
else:
    # Only use this for development
    LOG.warning("An in-memory database is being used as a broker. Only use "
                "this setting when testing or during development")
    BROKER_URL = "sqla+sqlite://"

# This would be a message queue only config, but won't work with Checkmate
# since checkmate needs to query task results and status
#CELERY_RESULT_BACKEND = "amqp"
#
# Use this if we want to track status and let clients query it
CELERY_RESULT_BACKEND = os.environ.get('CHECKMATE_RESULT_BACKEND', "database")

if CELERY_RESULT_BACKEND == "database":
    DEFAULT_BACKEND_PATH = os.path.expanduser(os.path.normpath(
        os.path.join(os.path.dirname(__file__), os.pardir, 'data',
                     'celerydb.sqlite')))
    DEFAULT_BACKEND_URI = "sqlite:///%s" % DEFAULT_BACKEND_PATH
elif CELERY_RESULT_BACKEND == "mongodb":
    # Get CHECKMATE settings, fall back to CELERY, and then default
    DEFAULT_SETTINGS = dict(host="localhost",
                            database="checkmate",
                            taskmeta_collection="celery_task_meta")
    CELERY_SETTING = os.environ.get('CELERY_MONGODB_BACKEND_SETTINGS')
    CHECKMATE_SETTING = os.environ.get('CHECKMATE_MONGODB_BACKEND_SETTINGS')
    CELERY_MONGODB_BACKEND_SETTINGS = json.loads(CHECKMATE_SETTING or
                                                 CELERY_SETTING or
                                                 str(DEFAULT_SETTINGS))
    DEFAULT_BACKEND_URI = BROKER_URL
    CONFIG = copy.copy(CELERY_MONGODB_BACKEND_SETTINGS)
    if 'password' in CONFIG:
        CONFIG['password'] = '*******'
    LOG.debug("CELERY_MONGODB_BACKEND_SETTINGS: %s", CONFIG)

CELERY_ACCEPT_CONTENT = ['json', 'pickle']

# Report out that this file was used for configuration
LOG.info("celery config loaded from %s", __file__)
LOG.info("celery persisting data in %s", CELERY_RESULT_BACKEND)
LOG.info("celery broker is %s", BROKER_URL.replace(
    os.environ.get('CHECKMATE_BROKER_PASSWORD', '*****'), '*****'))
