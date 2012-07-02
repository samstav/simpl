"""
  Celery tasks to handle SSH tasks
"""
import logging
import os

from celery.task import task
from celery.task.sets import subtask
import paramiko

LOG = logging.getLogger(__name__)


@task(default_retry_delay=10, max_retries=100)
def test_connection(deployment, ip, username, timeout=10, password=None,
           identity_file=None, port=22, callback=None):
    LOG.debug('Checking for a response from ssh://%s@%s:%d.' % (
        username, ip, port))
    try:
        client = paramiko.SSHClient()
        client.load_system_host_keys()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        auth_type = 'Password'
        if identity_file is not None:
            auth_type = 'Key'
            LOG.debug('Trying key file: %s' % os.path.expanduser(
                    identity_file))
            client.connect(ip, timeout=timeout, port=port,
                           username=username,
                           key_filename=os.path.expanduser(identity_file))
        else:
            client.connect(ip, port=port, username=username,
                           password=password)
        client.close()
        LOG.debug('ssh://%s@%s:%d is up.' % (
            username, ip, port))

        if callback:
            subtask(callback).delay()
        return True
    except (paramiko.AuthenticationException,
            paramiko.PasswordRequiredException), exc:
        if isinstance(exc, paramiko.PasswordRequiredException):
            #Looks like we have cert issues, so try password auth if we can
            if password:
                if test_connection(deployment, ip, username, timeout=timeout,
                    password=password, identity_file=None, port=port,
                    callback=callback):
                    LOG.debug("Authentication for ssh://%s@%s:%d using "
                            "password succeeded" % (username, ip, port))
                    return True

        LOG.debug('Authentication for ssh://%s@%s:%d failed. Type: %s' %
                (username, ip, port, auth_type))
        if test_connection.request.id:
            test_connection.retry(exc=exc)
    except paramiko.BadHostKeyException, exc:
        msg = ("ssh://%s@%s:%d failed:  %s. You might have a bad key "
                "entry on your server, but this is a security issue and won't "
                "be handled automatically. To fix this you can remove the "
                "host entry for this host from the /.ssh/known_hosts file" % (
                    username, ip, port, exc))
        print msg
        LOG.debug(msg)
        if test_connection.request.id:
            test_connection.update_state(state='FAILURE', meta={'Message':
                    msg})
        raise exc
    except Exception, exc:
        print exc
        LOG.debug('ssh://%s@%s:%d failed.  %s' % (
            username, ip, port, exc))
        if test_connection.request.id:
            test_connection.retry(exc=exc)
    return False


@task(default_retry_delay=10, max_retries=10)
def execute(ip, command, username, timeout=10, password=None,
           identity_file=None, port=22, callback=None):
    """Executes an ssh command on a remote host and returns a dict with stdin
    and stdout of the call. Tries cert auth first and falls back to password
    auth if password provided"""
    LOG.debug("Executing '%s' on ssh://%s@%s:%d." % (command, username,
        ip, port))
    client = paramiko.SSHClient()
    client.load_system_host_keys()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        if identity_file is not None:
            LOG.debug('Trying key file: %s' % os.path.expanduser(
                    identity_file))
            client.connect(ip, timeout=timeout, port=port,
                           username=username,
                           key_filename=os.path.expanduser(identity_file))
        else:
            client.connect(ip, port=port, username=username,
                           password=password)
    except (paramiko.AuthenticationException,
            paramiko.PasswordRequiredException), exc:
        if isinstance(exc, paramiko.PasswordRequiredException):
            #Looks like we have cert issues, so try password auth if we can
            if password:
                LOG.debug("Authentication for ssh://%s@%s:%d using "
                        "password succeeded" % (username, ip, port))
                return execute(ip, command, username,
                    timeout=timeout, password=password, identity_file=None,
                    port=port, callback=callback)
        raise exc

    try:
        stdin, stdout, stderr = client.exec_command(command)
        results = {'stdout': stdout.read(), 'stderr': stderr.read()}
        client.close()
        LOG.debug('ssh://%s@%s:%d responded.' % (username, ip, port))

        if callback is not None:
            subtask(callback).delay()
        return results
    except Exception, exc:
        print exc
        LOG.debug('ssh://%s@%s:%d failed.  %s' % (
            username, ip, port, exc))
        execute.retry(exc=exc)
    return False
