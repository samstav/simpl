'''
Preparing for organizing celery tasks

See:
    http://docs.celeryproject.org/en/latest/getting-started/
    next-steps.html#project-layout

RODO:
- rename to celery.py

'''
#pylint: disable=W0611
from celery import Task
from celery.exceptions import RetryTaskError


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
