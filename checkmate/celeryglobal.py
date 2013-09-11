# pylint: disable=E1101,W0613

# Copyright (c) 2011-2013 Rackspace Hosting
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

"""
Preparing for organizing celery app & tasks

See:
    http://docs.celeryproject.org/en/latest/getting-started/
    next-steps.html#project-layout

TODO:
- rename to celery.py

"""
import logging
import os

import celery
from celery import exceptions as celexc
from celery import signals

from checkmate import celeryconfig as celconf
from checkmate.common import config
from checkmate.db import common as dbcomm


LOG = logging.getLogger(__name__)
CONFIG = config.current()


def after_setup_logger_handler(sender=None, logger=None, loglevel=None,
                               logfile=None, format=None, colorize=None,
                               **kwds):
    """Once setup is complete, configure logging."""
    if (not celconf.CHECKMATE_CELERY_LOGCONFIG or
            not os.path.exists(celconf.CHECKMATE_CELERY_LOGCONFIG)):
        LOG.debug("'CHECKMATE_CELERY_LOGCONFIG' env is not configured, or is "
                  "configured to a non-existent path.")
        return

    LOG.debug(
        "Logging-Configuration file: %s", celconf.CHECKMATE_CELERY_LOGCONFIG)
    logging.config.fileConfig(celconf.CHECKMATE_CELERY_LOGCONFIG,
                              disable_existing_loggers=False)

signals.after_setup_logger.connect(after_setup_logger_handler)
signals.after_setup_task_logger.connect(after_setup_logger_handler)


@signals.celeryd_init.connect
def init_checkmate_worker(sender=None, conf=None, **kwargs):
    """Initialize Configuration."""
    LOG.info("Initializing Checkmate worker")
    CONFIG.update(config.parse_environment(env=os.environ))
    LOG.debug("Initialized config: %s", CONFIG.__dict__)


class AlwaysRetryTask(celery.Task):
    """Base of retrying tasks.

    See: https://groups.google.com/forum/?fromgroups=#!topic/celery-users/
         DACXXud_8eI
    """
    abstract = True

    def __call__(self, *args, **kwargs):
        try:
            return self.run(*args, **kwargs)
        except celexc.RetryTaskError:
            raise   # task is already being retried.
        except Exception as exc:
            return self.retry(exc=exc)


class SingleTask(celery.Task):
    """Base of non concurrent tasks."""
    abstract = True

    def __call__(self, *args, **kwargs):
        try:
            with(self.lock_db.lock(self.lock_key.format(**locals()),
                                   self.lock_timeout)):
                return self.run(*args, **kwargs)
        except dbcomm.ObjectLockedError as exc:
            LOG.warn("Object lock collision in Single Task '%s': %s",
                     self.name, exc)
            self.retry()
        except dbcomm.InvalidKeyError:
            raise
        except celexc.RetryTaskError:
            raise
        except Exception as exc:
            return self.retry(exc=exc)
