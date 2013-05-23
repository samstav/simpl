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

from celery import Task
from celery.exceptions import RetryTaskError

from checkmate.db.common import InvalidKeyError, ObjectLockedError

LOG = logging.getLogger(__name__)


class AlwaysRetryTask(Task):  # pylint: disable=R0904
    '''Base of retrying tasks

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
            self.retry(exc=exc)


class SingleTask(Task):  # pylint: disable=R0904
    '''Base of non concurrent tasks'''
    abstract = True

    def __call__(self, *args, **kwargs):
        try:
            with(self.lock_db.lock(self.lock_key.format(**locals()),
                                   self.lock_timeout)):
                return self.run(*args, **kwargs)
        except ObjectLockedError as exc:
            LOG.warn("Object lock collision in Single Task on "
                     "Deployment %s", args[0])
            self.retry()
        except InvalidKeyError:
            raise
        except RetryTaskError:
            raise
        except Exception as exc:
            self.retry(exc=exc)
