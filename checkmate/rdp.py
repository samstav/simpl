"""
    Celery tasks to handle RDP connections
"""
import logging

from celery.task import task
from celery.task.sets import subtask
from eventlet.green import socket

from checkmate.common import statsd
from checkmate.utils import match_celery_logging

LOG = logging.getLogger(__name__)


@task(default_retry_delay=10, max_retries=36)
@statsd.collect
def test_connection(context, host, port=3389, timeout=10, callback=None):
    '''Connect to a RDP server and verify that it responds.

    :param host:             the ip address or host name of the server
    :param port:           TCP IP port to use (RDP default is 3389)
    :param callback:       a callback task to call on success
    '''
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
    if callback:
        subtask(callback).delay()
    return True
