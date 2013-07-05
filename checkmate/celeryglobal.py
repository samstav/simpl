'''
Preparing for organizing celery app & tasks

See:
    http://docs.celeryproject.org/en/latest/getting-started/
    next-steps.html#project-layout

TODO:
- rename to celery.py

'''
#pylint: disable=W0611
from functools import partial
import logging
import os

from celery import Task
from celery.exceptions import RetryTaskError
from celery.signals import worker_process_init

from checkmate.common import config
from checkmate.db.common import InvalidKeyError, ObjectLockedError
from checkmate.exceptions import (
    CheckmateValidationException,
    CheckmateResumableException
)
import checkmate.utils as utils

LOG = logging.getLogger(__name__)
CONFIG = config.current()


@worker_process_init.connect  # pylint: disable=W0613
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


class ProviderTask(Task):
    '''Celery Task for providers.'''
    abstract = True

    def __init__(self, *args, **kwargs):
        self.__provider = self.provider
        self.provider = None

    def __call__(self, context, *args, **kwargs):
        try:
            utils.match_celery_logging(LOG)
            try:
                self.api = kwargs.get('api') or self.__provider.connect(
                    context, context['region'])
            # TODO(Nate): Generalize exception raised in providers connect
            except CheckmateValidationException:
                raise
            except StandardError as exc:
                return self.retry(exc=exc)
            self.partial = partial(self.callback, context)
            data = self.run(context, *args, **kwargs)
            self.callback(context, data)
            return data
        except RetryTaskError:
            raise  # task is already being retried.
        except CheckmateResumableException as exc:
            return self.retry(exc=exc)

    def callback(self, context, data):
        '''Calls postback with instance.id to ensure posted to resource.'''
        from checkmate.deployments import tasks
        results = {
            'resources': {
                context['resource']: {
                    'instance': data
                }
            }
        }
        if 'status' in data:
            results['resources'][context['resource']]['status'] = \
                self.__provider.translate_status(data['status'])

        tasks.postback(context['deployment'], results)
