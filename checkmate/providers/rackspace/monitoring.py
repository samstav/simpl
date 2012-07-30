import logging

from checkmate.providers import ProviderBase


LOG = logging.getLogger(__name__)

"""
class Provider(ProviderBase):
	name = 'monitoring'
	vendor = 'rackspace'
"""	

from rackspace_monitoring.providers import get_driver
from rackspace_monitoring.types import Provider
from libcloud.common.types import InvalidCredsError

def _connect(deployment):
	try:
		Cls = get_driver(Provider.RACKSPACE)
		driver = Cls(deployment['username'],deployment['apikey'])
	except InvalidCredsError, e:
		LOG.error('Cloud Monitoring authentication failed')
		raise e
	return driver


"""
  Celery tasks to manipulate Monitoring as a Service
"""

from celery.task import task

@task(default_retry_delay=5, max_retries=5)
def initialize_monitoring(driver=None,ip=None,name=None,context=None,resource=None):
	if driver is None:
		driver = _connect(context)

	try:
		LOG.debug("Creating entity for %s" % ip)
		entity = driver.create_entity(label=name,ip_addresses={'default':ip})
	except Exception, exc:
		LOG.debug("Failed to create entity for %s" % ip)
		initialize_monitoring.retry(exc=exc)
	LOG.debug("Successfully created entity %s for %s" % (name,ip))

	
	if resource == "lb":	
		check_type='remote.ping'
	elif resource == "node":
		check_type='remote.ping'
	else:
		check_type='remote.ping'

	try:
		#TODO: Decide what monitoring zone to poll from.
		LOG.debug("Creating %s check for entity %s" % (check_type, entity.id))
		driver.create_check(entity,type=check_type,label=check_type,target_alias='default',
			monitoring_zones=['mzdfw'])
	except Exception, exc:
		LOG.debug("Failed to create %s check for entity %s" % (check_type, entity.id))
		raise exc
	LOG.debug("Successfully created %s check for entity %s" % (check_type, entity.id))
	return True



