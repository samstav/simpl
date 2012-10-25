import logging

from SpiffWorkflow.operators import Attrib
from SpiffWorkflow.specs import Celery

from checkmate.exceptions import CheckmateException, CheckmateNoTokenError
from checkmate.providers import ProviderBase
from checkmate.utils import match_celery_logging

LOG = logging.getLogger(__name__)


class Provider(ProviderBase):
    name = 'dns'
    vendor = 'rackspace'

    def add_resource_tasks(self, resource, key, wfspec, deployment, context,
                           wait_on=None):
        inputs = deployment.get('inputs', {})
        hostname = resource.get('dns-name')

        create_dns_task = Celery(wfspec,
                                 'Create DNS Record',
                                 'checkmate.providers.rackspace.dns.'
                                 'create_record',
                                 call_args=[Attrib('context'),
                                 inputs.get('domain', 'localhost'),
                                 hostname,
                                 'A',
                                 Attrib('vip')],
                                 defines=dict(resource=key, provider=self.key,
                                 task_tags=['final', 'root', 'create']),
                                 properties={'estimated_duration': 30})
        return dict(root=create_dns_task, final=create_dns_task)

    def get_catalog(self, context, type_filter=None):
        #TODO: add more than just regions
        results = {}

        if type_filter is None or type_filter == 'regions':
            regions = {}
            for service in context.catalog:
                if service['type'] == 'dnsextension:dns':
                    endpoints = service['endpoints']
                    for endpoint in endpoints:
                        if 'region' in endpoint:
                            regions[endpoint['region']] = endpoint['publicURL']
            results['regions'] = regions

        return results

    def proxy(self, path, request, tenant_id=None):
        """Proxy request through to provider"""
        if not path:
            raise CheckmateException("Provider expects "
                                     "{version}/{tenant}/{path}")
        parts = path.split("/")
        if len(parts) < 2:
            raise CheckmateException("Provider expects "
                                     "{version}/{tenant}/{path}")
        version = parts[0]
        tenant_id = parts[1]
        resource = parts[2]
        if resource == "domains":
            api = _get_dns_object(request.context)
            domains = api.list_domains_info()
            return domains

        raise CheckmateException("Provider does not support the resource "
                                 "'%s'" % resource)

    @staticmethod
    def _connect(context):
        """Use context info to connect to API and return api object"""
        #FIXME: figure out better serialization/deserialization scheme
        if isinstance(context, dict):
            from checkmate.middleware import RequestContext
            context = RequestContext(**context)
        if not context.auth_token:
            raise CheckmateNoTokenError()

        class CloudDNS_Auth_Proxy():
            """We pass this class to clouddns for it to use instead of its own
            auth mechanism"""
            def __init__(self, url, token):
                self.url = url
                self.token = token

            def authenticate(self):
                """Called by clouddns. Expects back a url and token"""
                return (self.url, self.token)

        def find_url(catalog):
            for service in catalog:
                if service['name'] == 'cloudDNS':
                    endpoints = service['endpoints']
                    for endpoint in endpoints:
                        return endpoint['publicURL']

        url = find_url(context.catalog)
        token = context.auth_token
        proxy = CloudDNS_Auth_Proxy(url=url, token=token)
        api = clouddns.connection.Connection(auth=proxy)
        LOG.debug("Connected to cloud DNS using token of length %s "
                  "and url of %s" % (len(token), url))
        return api


"""
  Celery tasks to manipulate Rackspace Cloud DNS
"""
from celery.task import task
import clouddns
from clouddns.errors import UnknownDomain, ResponseError, InvalidDomainName


def _get_dns_object(context):
    return Provider._connect(context)


def parse_domain(domain_str):
    # return domain.com for web1.domain.com
    # hackish.  Doesn't account for .co.uk, .co.it, etc.
    chunks = domain_str.split('.')
    return chunks[-2] + '.' + chunks[-1]

""" Celery tasks """


@task(default_retry_delay=10, max_retries=10)
def get_domains(deployment, limit=None, offset=None):
    match_celery_logging(LOG)
    api = _get_dns_object(deployment)
    try:
        domains = api.list_domains_info(limit=limit, offset=offset)
        LOG.debug('Successfully retreived domains.')
        return domains
    except Exception, exc:
        LOG.debug('Error retreiving domains. Error: %s. Retrying.' % exc)
        get_domains.retry(exc=exc)


@task(default_retry_delay=10, max_retries=10)
def create_domain(context, domain, email=None,
                  dom_ttl=300):
    match_celery_logging(LOG)
    api = _get_dns_object(context)
    if not email:
        email = "admin@%s" % domain
    try:
        api.create_domain(name=domain, ttl=dom_ttl, emailAddress=email)
        LOG.debug('Domain %s created.' % domain)
    except InvalidDomainName as exc:
        LOG.debug('Domain %s is invalid.  Refusing to retry.' % domain)
        raise exc
    except ResponseError as r:
        LOG.debug('Error creating domain %s.(%s) %s. Retrying.' % (
            domain, r.status, r.reason))
        create_domain.retry(exc=r)
    except Exception as exc:
        LOG.debug('Unknown error creating domain %s. Error: %s. Retrying.' % (
                  domain, str(exc)))
        create_domain.retry(exc=exc)


@task
def delete_domain(context, name):
    match_celery_logging(LOG)
    api = _get_dns_object(context)
    try:
        domain = api.get_domain(name=name)
    except UnknownDomain, exc:
        LOG.debug('Cannot deleted domain %s because it does not exist. '
                  'Refusing to retry.' % name)
        return
    except Exception, exc:
        LOG.debug('Exception getting domain %s. Was hoping to delete it. '
                  'Error %s. Retrying.' % (name, str(exc)))
        delete_domain.retry(exc=exc)

    try:
        api.delete_domain(domain.id)
        LOG.debug('Domain %s deleted.' % name)
    except ResponseError, r:
        LOG.debug('Error deleting domain %s (%s) %s. Retrying.' % (
                  name, r.status, r.reason))
        delete_domain.retry(exc=r)
    except Exception, exc:
        LOG.debug('Error deleting domain %s. Error %s. Retrying.' % (
                  name, str(exc)))
        delete_domain.retry(exc=exc)


@task(default_retry_delay=20, max_retries=10)
def create_record(context, domain, name, dnstype, data,
                  rec_ttl=1800, makedomain=False,
                  email=None):
    match_celery_logging(LOG)
    api = _get_dns_object(context)
    try:
        domain_object = api.get_domain(name=domain)
    except UnknownDomain, exc:
        if makedomain:
            LOG.debug('Cannot create %s record (%s->%s) because %s does not '
                      'exist. Creating %s and retrying.' % (
                      dnstype, name, data, domain, domain))
            if not email:
                email = "admin@%s" % domain
            create_domain.delay(context, domain, email=email)
            create_record.retry(exc=exc)
        else:
            LOG.debug('Cannot create %s record (%s->%s) because %s does not '
                      'exist. Refusing to retry.' % (
                      dnstype, name, data, domain))
            return
    except Exception, exc:
        LOG.debug('Error finding domain %s.  Wanting to create %s record (%s'
                  '->%s TTL: %s). Error %s. Retrying.' % (
                  domain, dnstype, name, data, rec_ttl, str(exc)))
        create_record.retry(exc=exc)

    try:
        domain_object.create_record(name, data, dnstype, ttl=rec_ttl)
        LOG.debug('Created DNS %s record %s -> %s. TTL: %s' % (
                  dnstype, name, data, rec_ttl))
    except ResponseError, r:
        LOG.debug('Error creating DNS %s record %s -> %s. TTL: %s Error: %s '
                  '%s. Retrying.' % (
                  dnstype, name, data, rec_ttl, r.status, r.reason))
        create_record.retry(exc=r)
    except Exception, exc:
        LOG.debug('Error creating DNS %s record %s -> %s. TTL: %s Error: %s.'
                  ' Retrying.' % (dnstype, name, data, rec_ttl, str(exc)))
        create_record.retry(exc=exc)


@task(default_retry_delay=20, max_retries=10)
def delete_record(context, domain, name):
    match_celery_logging(LOG)
    api = _get_dns_object(context)
    try:
        domain = api.get_domain(name=domain)
    except UnknownDomain, exc:
        LOG.debug('Cannot delete record %s because %s does not exist. '
                  'Refusing to retry.' % (name, domain))
        return
    except Exception, exc:
        LOG.debug('Error finding domain %s.  Wanting to delete record %s. '
                  'Error %s. Retrying.' % (domain, name, str(exc)))
        delete_record.retry(exc=exc)

    try:
        record = domain.get_record(name=name)
        domain.delete_record(record.id)
        LOG.debug('Deleted DNS record %s.' % name)
    except ResponseError, r:
        LOG.debug('Error deleting DNS record %s. Error %s %s. Retrying.' % (
                  name, r.status, r.reason))
        delete_record.retry(exc=r)
    except Exception, exc:
        LOG.debug('Error deleting DNS record %s. Error %s. Retrying.' % (
                  name, str(exc)))
        delete_record.retry(exc=exc)
