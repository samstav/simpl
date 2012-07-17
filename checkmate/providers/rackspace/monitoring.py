
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
def create_entity_and_check(driver=None,ip,data=None,name):
	if driver is None:
		driver = Provider._connect(context)

	#TODO: Check that ip/meta/label all have values

	#Create an entity for a given resource (represented by the resource's ip address)
	entity_location = driver.create_entity(who='',why='',label=name,ip_addresses={'default':ip},metadata=data)

	#location is in form of endpoint/entities/entity_id
	entity_id = entity_location.split('/')[-1]
	entity = driver.get_entity(entity_id)
	
	driver.create_check(entity,disabled=None,type='remote.ping',details=None,
		label='ping',target_alias=None,target_resolver=None,target_hostname=None,
		who='',why='')

