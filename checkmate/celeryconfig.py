import logging
import os

LOG = logging.getLogger(__name__)

if 'CHECKMATE_BROKER_URL' in os.environ:
    # Example for debugging that does not need AMQP:
    # BROKER_URL="sqla+sqlite:////Users/projects/checkmate/data/db.sqlite"
    BROKER_URL = os.environ['CHECKMATE_BROKER_URL']
else:
    broker = {
     'username': 'checkmate',
     'password': 'password',
     'host': 'localhost',
     'port': 5672
    }

    BROKER_URL = "amqp://%s:%s@%s:%s/checkmate" % (broker['username'],
                                              broker['password'],
                                              broker['host'],
                                              broker['port'])

# This would be a message queue only config, but won't work with Checkmate
# since checkmate needs to query task results and status
#CELERY_RESULT_BACKEND = "amqp"
#
# Use this if we want to track status and let clients query it
CELERY_RESULT_BACKEND = os.environ.get('CHECKMATE_RESULT_BACKEND', "database")

sql_default = "sqlite:///%s" % os.path.expanduser(os.path.normpath(
        os.path.join(os.path.dirname(__file__), os.pardir, 'data',
        'celerydb.sqlite')))
CELERY_RESULT_DBURI = os.environ.get('CHECKMATE_RESULT_DBURI', sql_default)

# Report out that this file was used for configuration
LOG.info("celery config loaded from %s" % __file__)
LOG.info("celery persisting data in %s" % CELERY_RESULT_DBURI)
LOG.info("celery broker is %s" % BROKER_URL.replace(
            os.environ.get('CHECKMATE_BROKER_PASSWORD', '*****'), '*****'))
