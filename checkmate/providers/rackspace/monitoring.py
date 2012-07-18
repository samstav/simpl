
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
	except Exception e:
		LOG.error('Cloud Monitoring authentication failed')
		raise e
	return driver


"""
  Celery tasks to manipulate Monitoring as a Service
"""


@task
def create_entity_and_check(driver=None,ip,data=None,name,context):
	if driver is None:
		driver = Provider._connect(context)
	#TODO: Check for values of ip/data/name/context

	#Create an entity for a given resource (represented by the resource's ip address)
	entity = driver.create_entity(label=name,ip_addresses={'default':ip},metadata=data)
	
	#TODO: Need a way to decide what monitoring zones to poll from
	#Maybe all of them? Maybe whatever zone the device lives in? Defaulting to dfw for now
	#TODO: Need a way to decide what sort of check to put against a device
	#Maybe make sure certain ports open on server? SSH capabilities?
	

	#TODO: Check to make sure entity has been created before created check 

	#Create a basic 'ping' check against resource
	driver.create_check(entity,type='remote.ping',name='ping',target_alias='default',
		monitoring_zones=['mzdfw'])

