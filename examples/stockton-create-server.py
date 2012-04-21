""""Create a server using the Orchestrator.

This demonstrates a simple use case where we use the workflow engine to
orchestrate a number of tasks.

STATUS: It's a proof of concept.
"""
import copy
import os
import random
import sys
import time

# NOTE: these are needed before importing stockton (it uses them on import)
assert 'STOCKTON_APIKEY' in os.environ
assert 'STOCKTON_USERNAME' in os.environ
assert 'BROKER_USERNAME' in os.environ
assert 'CELERY_CONFIG_MODULE' in os.environ


deployment = {
 'id': str(random.randint(1000, 10000)),
 'username': os.environ['STOCKTON_USERNAME'],
 'apikey': os.environ['STOCKTON_APIKEY'],
 'region': os.environ['STOCKTON_REGION'],
 'public_key': os.environ['STOCKTON_PUBLIC_KEY'],
 'private_key': os.environ['STOCKTON_PRIVATE_KEY'],
 'files': {},
}
print "Deployment ID: %s" % deployment['id']

# Read in the public key, this can be passed to newly created servers.
if (os.environ.has_key('STOCKTON_PUBLIC_KEY') and  
        os.path.exists(os.path.expanduser(os.environ['STOCKTON_PUBLIC_KEY']))):
    try:
        f = open(os.path.expanduser(os.environ['STOCKTON_PUBLIC_KEY']))
        deployment['public_key'] = f.read()
        deployment['files']['/root/.ssh/authorized_keys'] = \
                deployment['public_key']
        f.close()
    except IOError as (errno, strerror):
        sys.exit("I/O error reading public key (%s): %s" % (errno,
                                                              strerror))
    except:
        sys.exit('Cannot read public key.')


def wait_on_task(task, timeout=60, output=None):
    """Routine to wait on an async call and emit and status data that is
    returned (by default to STDOUT)
    NB: This function might be moved to a stockton utilities module"""
    if output is None:
        output = sys.stdout
    output.write("Waiting on asynchronous call '%s'\n" % task)
    last_state, last_info = None, None
    elapsed = 0
    msg = ""
    while not task.ready() and elapsed < timeout:
        if last_state != task.state:
            msg +=  "\nStatus is now: %s" % task.state
            last_state = task.state
        if isinstance(task.info, BaseException):
            msg += "\nTask Error received: %s" % task.info
        elif task.info and len(task.info) and last_info != task.info:
            msg += "\nData received: %s" % task.info.__str__()
            last_info = copy.deepcopy(task.info)

        if len(msg) > 1:
            output.write(msg[1:])
        else:
            output.write(".")
        output.flush()
        time.sleep(1)
        elapsed += 1
        msg = " "
    output.write("\n")


import stockton  # init and make sure we end up using the same celery instance
import checkmate.orchestrator

# Let's make sure we are talking to the stockton celery
#TODO: fix this when we have better celery/stockton configuration
from celery import current_app
assert current_app.backend.__class__.__name__ == 'DatabaseBackend'
assert 'python-stockton' in current_app.backend.dburi.split('/')

# Make the async call!
hostname = 'orchestrator-test-%s.%s' % (deployment['id'],
                         os.environ.get('STOCKTON_TEST_DOMAIN',
                                        'mydomain.com'))
async_call = checkmate.orchestrator.distribute_create_simple_server.delay(
        deployment, hostname, files=deployment['files'])

# Wait for task to complete and output to STDOUT
wait_on_task(async_call, timeout=90)
if not async_call.ready():
    sys.exit("Timed out waiting on task")
if isinstance(async_call.info, Exception):
    sys.exit(async_call.info)

results = async_call.info

server_id = results['stockton.server.distribute_create']['id']
server_ip = results['stockton.server.distribute_create']['ip']

print "Server Created: ID=%s, IP=%s" % (server_id, server_ip)
if (os.environ.has_key('STOCKTON_PUBLIC_KEY') and  
        os.path.exists(os.path.expanduser(os.environ['STOCKTON_PUBLIC_KEY']))):
    print "When the server is ready, connect using:"
    print "  ssh -i %s root@%s" % (os.environ['STOCKTON_PRIVATE_KEY'],
                                   server_ip)
