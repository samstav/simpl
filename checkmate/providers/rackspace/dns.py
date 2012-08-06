import logging

from SpiffWorkflow.operators import Attrib
from SpiffWorkflow.specs import Celery

from checkmate.providers import ProviderBase

LOG = logging.getLogger(__name__)


class Provider(ProviderBase):
    name = 'dns'
    vendor = 'rackspace'

    def add_resource_tasks(self, resource, key, wfspec, deployment, context,
                wait_on=None):
        inputs = deployment.get('inputs', {})
        hostname = resource.get('dns-name')

        create_dns_task = Celery(wfspec, 'Create DNS Record',
                           'checkmate.providers.rackspace.dns.create_record',
                           call_args=[Attrib('context'),
                           inputs.get('domain', 'localhost'), hostname,
                           'A', Attrib('vip')],
                           defines=dict(resource=key,
                                        provider=self.key,
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


"""
  Celery tasks to manipulate Rackspace Cloud DNS
"""
from celery.task import task
import clouddns
from clouddns.errors import UnknownDomain, ResponseError, InvalidDomainName


def _get_dns_object(context):
    # Until python-clouddns is patched to accept pre-existing API
    # tokens, we'll have to re-auth.
    return clouddns.connection.Connection(context['username'],
                                          context['apikey'])


def parse_domain(domain_str):
    # return domain.com for web1.domain.com
    # hackish.  Doesn't account for .co.uk, .co.it, etc.
    chunks = domain_str.split('.')
    return chunks[-2] + '.' + chunks[-1]

""" Celery tasks """


@task(default_retry_delay=10, max_retries=10)
def create_domain(context, domain, email='soa_placeholder@example.com',
        ttl=300):
    api = _get_dns_object(context)
    try:
        api.create_domain(name=domain, ttl=ttl, emailAddress=email)
        LOG.debug('Domain %s created.' % domain)
    except InvalidDomainName, exc:
        LOG.debug('Domain %s is invalid.  Refusing to retry.' % domain)
        return
    except ResponseError, r:
        LOG.debug('Error creating domain %s.(%s) %s. Retrying.' % (
            domain, r.status, r.reason))
        create_domain.retry(exc=r)
    except Exception, exc:
        LOG.debug('Unknown error creating domain %s. Error: %s. Retrying.' % (
                domain, str(exc)))
        create_domain.retry(exc=exc)


@task
def delete_domain(context, name):
    api = _get_dns_object(context)
    try:
        domain = api.get_domain(name=name)
    except UnknownDomain, exc:
        LOG.debug('Cannot deleted domain %s because it does not exist. ' \
                'Refusing to retry.' % name)
        return
    except Exception, exc:
        LOG.debug('Exception getting domain %s. Was hoping to delete it. ' \
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
                             ttl=1800, makedomain=False,
                             email='soa_placeholder@example.com'):
    api = _get_dns_object(context)
    try:
        domain_object = api.get_domain(name=domain)
    except UnknownDomain, exc:
        if makedomain:
            LOG.debug('Cannot create %s record (%s->%s) because %s does not ' \
                    'exist. Creating %s and retrying.' % (
                    dnstype, name, data, domain, domain))
            create_domain.delay(context, domain, email=email)
            create_record.retry(exc=exc)
        else:
            LOG.debug('Cannot create %s record (%s->%s) because %s does not ' \
                'exist. Refusing to retry.' % (dnstype, name, data, domain))
            return
    except Exception, exc:
        LOG.debug('Error finding domain %s.  Wanting to create %s record (%s' \
            '->%s TTL: %s). Error %s. Retrying.' % (
              domain, dnstype, name, data, ttl, str(exc)))
        create_record.retry(exc=exc)

    try:
        domain_object.create_record(name, data, dnstype, ttl=ttl)
        LOG.debug('Created DNS %s record %s -> %s. TTL: %s' % (
            dnstype, name, data, ttl))
    except ResponseError, r:
        LOG.debug('Error creating DNS %s record %s -> %s. TTL: %s Error: %s ' \
            '%s. Retrying.' % (
              dnstype, name, data, ttl, r.status, r.reason))
        create_record.retry(exc=r)
    except Exception, exc:
        LOG.debug('Error creating DNS %s record %s -> %s. TTL: %s Error: %s.' \
            ' Retrying.' % (dnstype, name, data, ttl, str(exc)))
        create_record.retry(exc=exc)


@task(default_retry_delay=20, max_retries=10)
def delete_record(context, domain, name):
    api = _get_dns_object(context)
    try:
        domain = api.get_domain(name=domain)
    except UnknownDomain, exc:
        LOG.debug('Cannot delete record %s because %s does not exist. ' \
            'Refusing to retry.' % (name, domain))
        return
    except Exception, exc:
        LOG.debug('Error finding domain %s.  Wanting to delete record %s. ' \
            'Error %s. Retrying.' % (domain, name, str(exc)))
        delete_record.retry(exc=exc)

    try:
        record = domain.get_record(name=name)
        domain.delete_record(record.id)
        LOG.debug('Deleted DNS record %s.' % name)
    except ResponseError, r:
        LOG.debug('Error deleting DNS record %. Error %s %s. Retrying.' % (
            name, r.status, r.reason))
        delete_record.retry(exc=r)
    except Exception, exc:
        LOG.debug('Error deleting DNS record %s. Error %s. Retrying.' % (
            name, str(exc)))
        delete_record.retry(exc=exc)
