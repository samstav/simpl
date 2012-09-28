"""This is where celery picks up its settings"""
import json
import logging
import os
import sys


LOG = logging.getLogger(__name__)

# For debugging, thise makes all calls synchronous
if '--eager' in sys.argv:
    CELERY_ALWAYS_EAGER = True
else:
    CELERY_ALWAYS_EAGER = os.environ.get("CELERY_ALWAYS_EAGER",
                                         "false").lower() in ["true", "1"]
if CELERY_ALWAYS_EAGER:
    LOG.warning("Celery is running synchronously because the "
                "CELERY_ALWAYS_EAGER setting is true")

if 'CHECKMATE_BROKER_URL' in os.environ:
    BROKER_URL = os.environ['CHECKMATE_BROKER_URL']
elif 'CHECKMATE_BROKER_HOST' in os.environ:
    broker = {'username': os.environ.get('CHECKMATE_BROKER_USERNAME'),
              'password': os.environ.get('CHECKMATE_BROKER_PASSWORD'),
              'host': os.environ.get('CHECKMATE_BROKER_HOST', 'localhost'),
              'port': os.environ.get('CHECKMATE_BROKER_PORT', '5672'),
              }
    BROKER_URL = "amqp://%s:%s@%s:%s/checkmate" % (broker['username'],
                                                   broker['password'],
                                                   broker['host'],
                                                   broker['port'])
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
    default_backend_path = os.path.expanduser(os.path.normpath(
        os.path.join(os.path.dirname(__file__), os.pardir, 'data',
                     'celerydb.sqlite')))
    default_backend_uri = "sqlite:///%s" % default_backend_path
elif CELERY_RESULT_BACKEND == "mongodb":
    # Get CHECKMATE settings, fall back to CELERY, and then default
    default_settings = dict(host="localhost",
                            database="checkmate",
                            taskmeta_collection="celery_task_meta")
    celery_setting = os.environ.get('CELERY_MONGODB_BACKEND_SETTINGS')
    checkmate_setting = os.environ.get('CHECKMATE_MONGODB_BACKEND_SETTINGS')
    CELERY_MONGODB_BACKEND_SETTINGS = json.loads(checkmate_setting or
                                                 celery_setting or
                                                 str(default_settings))
    default_backend_uri = BROKER_URL
    LOG.debug("CELERY_MONGODB_BACKEND_SETTINGS: %s" %
              CELERY_MONGODB_BACKEND_SETTINGS)

CELERY_RESULT_DBURI = os.environ.get('CHECKMATE_RESULT_DBURI',
                                     default_backend_uri)

# Report out that this file was used for configuration
LOG.info("celery config loaded from %s" % __file__)
LOG.info("celery persisting data in %s" % CELERY_RESULT_DBURI)
LOG.info("celery broker is %s" % BROKER_URL.replace(
         os.environ.get('CHECKMATE_BROKER_PASSWORD', '*****'), '*****'))
