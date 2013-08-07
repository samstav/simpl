'''
Preparing for organizing celery app & tasks

See:
    http://docs.celeryproject.org/en/latest/getting-started/
    next-steps.html#project-layout

TODO:
- rename to celery.py

'''
#pylint: disable=W0611
import logging
import os

from celery import Task
from celery.exceptions import RetryTaskError
from celery import signals

from checkmate.celeryconfig import CHECKMATE_CELERY_LOGCONFIG
from checkmate.common import config
from checkmate.db.common import InvalidKeyError, ObjectLockedError


LOG = logging.getLogger(__name__)
CONFIG = config.current()


def after_setup_logger_handler(sender=None, logger=None, loglevel=None,
                               logfile=None, format=None, colorize=None,
                               **kwds):
    if (not CHECKMATE_CELERY_LOGCONFIG or
            not os.path.exists(CHECKMATE_CELERY_LOGCONFIG)):
        LOG.debug("'CHECKMATE_CELERY_LOGCONFIG' env is not configured, or is "
                  "configured to a non-existent path.")
        return

    LOG.debug("Logging-Configuration file: %s" % CHECKMATE_CELERY_LOGCONFIG)
    logging.config.fileConfig(CHECKMATE_CELERY_LOGCONFIG,
                                  disable_existing_loggers=False)

signals.after_setup_logger.connect(after_setup_logger_handler)
signals.after_setup_task_logger.connect(after_setup_logger_handler)


@signals.worker_process_init.connect  # pylint: disable=W0613
def init_checkmate_worker(**kwargs):
    '''Initialize Configuration.'''
    LOG.info("Initializing Checkmate worker")
    CONFIG.update(config.parse_environment(env=os.environ))
    LOG.debug("Initialized config: %s", CONFIG.__dict__)


class AlwaysRetryTask(Task):  # pylint: disable=R0904,W0223
    '''Base of retrying tasks.

    See: https://groups.google.com/forum/?fromgroups=#!topic/celery-users/
         DACXXud_8eI
    '''
    abstract = True

    def __call__(self, *args, **kwargs):
        try:
            return self.run(*args, **kwargs)
        except RetryTaskError:
            raise   # task is already being retried.
        except Exception, exc:
            return self.retry(exc=exc)


class SingleTask(Task):  # pylint: disable=R0904,W0223
    '''Base of non concurrent tasks.'''
    abstract = True

    def __call__(self, *args, **kwargs):
        try:
            with(self.lock_db.lock(self.lock_key.format(**locals()),
                                   self.lock_timeout)):
                return self.run(*args, **kwargs)
        except ObjectLockedError as exc:
            LOG.warn("Object lock collision in Single Task '%s': %s",
                     self.name, exc)
            self.retry()
        except InvalidKeyError:
            raise
        except RetryTaskError:
            raise
        except Exception as exc:
            return self.retry(exc=exc)
