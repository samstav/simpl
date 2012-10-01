"""
    Celery tasks to handle SSH connections
"""
import logging
import os
import StringIO

from celery.task import task
from celery.task.sets import subtask
import paramiko

from checkmate.utils import match_celery_logging

LOG = logging.getLogger(__name__)


class AcceptMissingHostKey(paramiko.client.MissingHostKeyPolicy):
    """ add missing host keys to the client, but do not save in the known_hosts file 
     since we can easily spin up servers that have recycled ip addresses """
    
    def missing_host_key(self, client, hostname, key):
        client._host_keys.add(hostname, key.get_name(), key)

@task(default_retry_delay=10, max_retries=36)
def test_connection(context, ip, username, timeout=10, password=None,
           identity_file=None, port=22, callback=None, private_key=None):
    """Connect to an ssh server and verify that it responds

    ip:             the ip address or host name of the server
    username:       the username to use
    timeout:        timeout in seconds
    password:       password to use for username/password auth
    identity_file:  a private key file to use
    port:           TCP IP port to use (ssh default is 22)
    callback:       a callback task to call on success
    private_key:    an RSA string for the private key to use (instead of using
                    a file)

    The order for authentication attempts is:
    - private_key
    - identity_file
    - any key discoverable in ~/.ssh/
    - username/password
    """
    match_celery_logging(LOG)
    LOG.debug("Checking for a response from ssh://%s@%s:%d." % (
        username, ip, port))
    try:
        client = _connect(ip, port=port, username=username, timeout=timeout,
                      private_key=private_key, identity_file=identity_file,
                      password=password)
        client.close()
        LOG.debug("ssh://%s@%s:%d is up." % (username, ip, port))
        if callback:
            subtask(callback).delay()
        return True
    except Exception, exc:
        LOG.debug('ssh://%s@%s:%d failed.  %s' % (username, ip, port, exc))
        if test_connection.request.id:
            test_connection.retry(exc=exc)
    return False


@task(default_retry_delay=10, max_retries=10)
def execute(ip, command, username, timeout=10, password=None,
           identity_file=None, port=22, callback=None, private_key=None):
    """Executes an ssh command on a remote host and returns a dict with stdin
    and stdout of the call. Tries cert auth first and falls back to password
    auth if password provided

    ip:             the ip address or host name of the server
    command:        shell command to execute
    username:       the username to use
    timeout:        timeout in seconds
    password:       password to use for username/password auth
    identity_file:  a private key file to use
    port:           TCP IP port to use (ssh default is 22)
    callback:       a callback task to call on success
    private_key:    an RSA string for the private key to use (instead of using
                    a file)
    """
    match_celery_logging(LOG)
    LOG.debug("Executing '%s' on ssh://%s@%s:%d." % (command, username,
        ip, port))
    try:
        client = _connect(ip, port=port, username=username, timeout=timeout,
                      private_key=private_key, identity_file=identity_file,
                      password=password)
        stdin, stdout, stderr = client.exec_command(command)
        results = {'stdout': stdout.read(), 'stderr': stderr.read()}
        LOG.debug('ssh://%s@%s:%d responded.' % (username, ip, port))
        if callback is not None:
            subtask(callback).delay()
        return results
    except Exception, exc:
        LOG.debug("ssh://%s@%s:%d failed.  %s" % (username, ip, port, exc))
        execute.retry(exc=exc)
    finally:
        if client:
            client.close()
    return False


def _connect(ip, port=22, username="root", timeout=10, identity_file=None,
             private_key=None, password=None):
    """Attempts SSH connection and returns SSHClient object
    ip:             the ip address or host name of the server
    username:       the username to use
    timeout:        timeout in seconds
    password:       password to use for username/password auth
    identity_file:  a private key file to use
    port:           TCP IP port to use (ssh default is 22)
    private_key:    an RSA string for the private key to use (instead of using
                    a file)
    """
    client = paramiko.SSHClient()
    client.load_system_host_keys()
    client.set_missing_host_key_policy(AcceptMissingHostKey())
    try:
        if private_key is not None:
            file_obj = StringIO.StringIO(private_key)
            pkey = paramiko.RSAKey.from_private_key(file_obj)
            LOG.debug("Trying supplied private key string")
            client.connect(ip, timeout=timeout, port=port, username=username,
                           pkey=pkey)
        elif identity_file is not None:
            LOG.debug("Trying key file: %s" % os.path.expanduser(
                    identity_file))
            client.connect(ip, timeout=timeout, port=port, username=username,
                           key_filename=os.path.expanduser(identity_file))
        else:
            client.connect(ip, port=port, username=username, password=password)
            LOG.debug("Authentication for ssh://%s@%s:%d using "
                    "password succeeded" % (username, ip, port))
        LOG.debug("Connected to ssh://%s@%s:%d." % (username, ip, port))
        return client
    except paramiko.PasswordRequiredException, exc:
        #Looks like we have cert issues, so try password auth if we can
        if password:
            LOG.debug("Retrying with password credentials")
            return _connect(ip, username=username, timeout=timeout,
                            password=password, port=port)
        else:
            raise exc
    except paramiko.BadHostKeyException, exc:
        msg = ("ssh://%s@%s:%d failed:  %s. You might have a bad key "
                "entry on your server, but this is a security issue and won't "
                "be handled automatically. To fix this you can remove the "
                "host entry for this host from the /.ssh/known_hosts file" % (
                    username, ip, port, exc))
        LOG.debug(msg)
        raise exc
    except Exception, exc:
        LOG.debug('ssh://%s@%s:%d failed.  %s' % (username, ip, port, exc))
        raise exc
