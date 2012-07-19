
import logging

from checkmate.providers import ProviderBase


LOG = logging.getLogger(__name__)

class Provider(ProviderBase):
	name = 'monitoring'
	vendor = 'rackspace'
	

from rackspace_monitoring.providers import get_driver
from rackspace_monitoring.types import Provider

def _connect(deployment):
	try:
		Cls = get_driver(Provider.RACKSPACE)
		driver = Cls(deployment['username'],deployment['apikey'])
	#TODO: Check for specific Monitoring Auth failures
	except Exception, e:
		LOG.error('Cloud Monitoring authentication failed')
		raise e
	return driver


"""
  Celery tasks to manipulate Monitoring as a Service
"""

from celery.task import task

@task(default_retry_delay=5, max_retries=5)
def create_entity(driver=None,ip,data=None,name,context):
	"""
	:returns: the created entity
	"""
	if driver is None:
		driver = Provider._connect(context)

	try:
		LOG.debug("Creating entity for %s") % ip
		entity = driver.create_entity(label=name,ip_addresses={'default':ip},metadata=data)
	except Exception, exc:
		LOG.debug("Failed to create entity for %s") % ip
		create_entity.retry(exc=exc)
	LOG.debug("Successfully created entity %s for %s") % (name,ip)
	create_check.delay(driver,context,entity)
	

def create_check(driver=None,context,entity):
	"""
	TODO: Decide what sort of checks to create based on resource
	"""
	if driver is None:
		driver = Provider_connect(context)	
	try:
		check_type = 'remote.ping'	
		#TODO: Decide what monitoring zone to poll from.
		#Should we poll based on the location of the device? Let the customer decide?
		LOG.debug("Creating %s check for entity %s") % (check_type, entity.id)
		driver.create_check(entity,type=check_type,name='ping',target_alias='default',
			monitoring_zones=['mzdfw'])
	except Exception, exc:
		LOG.debug("Failed to create %s check for entity %s") % (check_type, entity.id)
		create_check.retry(exc=exc) 
	LOG.debug("Successfully created % check for entity %s") % (check_type, entity.id)

