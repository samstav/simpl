import logging
import os

LOG = logging.getLogger(__name__)

if 'CHECKMATE_BROKER_URL' in os.environ:
    # Example for debugging that does not need AMQP:
    # BROKER_URL="sqla+sqlite:////Users/projects/checkmate/data/db.sqlite"
    BROKER_URL = os.environ['CHECKMATE_BROKER_URL']
else:
    broker = {
     'username': os.environ['CHECKMATE_BROKER_USERNAME'],
     'password': os.environ['CHECKMATE_BROKER_PASSWORD'],
     'host': os.environ['CHECKMATE_BROKER_HOST'],
     'port': os.environ['CHECKMATE_BROKER_PORT']
    }

    BROKER_URL = "amqp://%s:%s@%s:%s/checkmate" % (broker['username'],
                                              broker['password'],
                                              broker['host'],
                                              broker['port'])

# This would be a message queue only config, but won't work with Checkmate
# since checkmate needs to query task results and status
#CELERY_RESULT_BACKEND = os.environ.get('CHECKMATE_RESULT_BACKEND', "database")
#
# Use this if we want to track status and let clients query it
CELERY_RESULT_BACKEND = os.environ.get('CHECKMATE_RESULT_BACKEND', "database")

sql_default = "sqlite:////%s" % os.path.join('var', 'checkmate', 'data',
        'celerydb.sqlite')
CELERY_RESULT_DBURI = os.environ.get('CHECKMATE_RESULT_DBURI', sql_default)

# Report out that this file was used for configuration
print "celery config loaded from %s" % __file__
print "celery persisting data in %s" % CELERY_RESULT_DBURI
print "celery broker is %s" % BROKER_URL.replace(
            os.environ.get('CHECKMATE_BROKER_PASSWORD', '*****'), '*****')
