# Copyright (c) 2011-2015 Rackspace US, Inc.
# All Rights Reserved.
#
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

"""Celery tasks to handle RDP connections."""

import logging

from celery.task import task
from eventlet.green import socket

from checkmate.common import statsd
from checkmate.utils import match_celery_logging

LOG = logging.getLogger(__name__)


@task(default_retry_delay=10, max_retries=36)
@statsd.collect
def test_connection(context, host, port=3389, timeout=10):
    """Connect to a RDP server and verify that it responds.

    :param host:             the ip address or host name of the server
    :param port:           TCP IP port to use (RDP default is 3389)
    """
    match_celery_logging(LOG)
    LOG.debug("Checking for a response from rdp://%s:%d.", host, port)

    # pylint: disable=E1101
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        sock.connect((host, port))
    except StandardError as exc:
        LOG.debug('rdp://%s:%d failed.  %s', host, port, exc)
        if test_connection.request.id:
            test_connection.retry(exc=exc)

    sock.close()
    LOG.debug("rdp://%s:%d is up.", host, port)
    return True
