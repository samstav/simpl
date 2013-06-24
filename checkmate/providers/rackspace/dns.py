import logging

import tldextract
from SpiffWorkflow.operators import Attrib
from SpiffWorkflow.specs import Celery

from checkmate.exceptions import CheckmateException, CheckmateNoTokenError
from checkmate.providers import ProviderBase
from checkmate.utils import match_celery_logging
import os
from checkmate.providers.base import user_has_access
from checkmate.common import caching
import sys
from eventlet.greenpool import GreenPile
from clouddns.domain import Domain

LOG = logging.getLogger(__name__)
DNS_API_CACHE = {}


class Provider(ProviderBase):
    name = 'dns'
    vendor = 'rackspace'

    @caching.CacheMethod(timeout=3600, sensitive_args=[1], store=DNS_API_CACHE)
    def _get_limits(self, url, token):
        api = self.connect(token=token, url=url)
        return api.get_limits()

    def _is_new_domain(self, domain, context):
        if domain and context:
            api = self.connect(context)
            dom = self._my_list_domains_info(api, domain)
            return not dom
        return False

    @staticmethod
    def _my_list_domains_info(api, dom_name):
        try:
            return api.list_domains_info(filter_by_name=dom_name)
        except ResponseError as respe:
            if respe.status != 404:
                LOG.warn("Error checking record limits for %s", dom_name,
                         exc_info=True)

    def _check_record_limits(self, context, dom_name, max_records,
                             num_new_recs):
        if num_new_recs > 0:
            api = self.connect(context)
            if dom_name:
                num_recs = 0
                doms = self._my_list_domains_info(api, dom_name)
                if doms:
                    dom = Domain(api, doms[0])
                    try:
                        num_recs = len(dom.list_records_info())
                    except ResponseError as respe:
                        num_recs = 0
                        if 404 != respe.status:
                            LOG.warn("Error getting records for %s", dom_name,
                                     exc_info=True)
                if num_recs + num_new_recs > max_records:
                    return {
                        'type': "INSUFFICIENT-CAPACITY",
                        'message': "Domain %s would have %s records after "
                                   "this operation. You may only have "
                                   "up to %s records for a domain."
                                   % (dom_name, num_recs + num_new_recs,
                                   max_records),
                        'provider': self.name,
                        'severity': "CRITICAL",
                    }

    def verify_limits(self, context, resources):
        messages = []
        api = self.connect(context)
        limits = self._get_limits(self._find_url(context.catalog),
                                  context.auth_token)
        max_doms = limits.get('absolute', {}).get('domains', sys.maxint)
        max_recs = limits.get('absolute', {}).get('records per domain',
                                                  sys.maxint)
        cur_doms = api.get_total_domain_count()
        # get a list of the possible domains
        domain_names = set(map(lambda x: parse_domain(x.get('dns-name')),
                               resources))
        # find the ones that are new
        pile = GreenPile()
        for dom in domain_names:
            pile.spawn(self._is_new_domain, dom, context)
        num_new = len([val for val in pile if val])
        # if they are going to create more domains than they
        # should, respond
        if (num_new + cur_doms) > max_doms:
            messages.append({
                'type': "INSUFFICIENT-CAPACITY",
                'message': ("This deployment would create %s domains. "
                            "You have %s domains available."
                            % (num_new, max_doms - cur_doms)),
                'provider': self.name,
                'severity': "CRITICAL"
            })

        # make sure we're not exceeding the record count
        def _count_filter_records(resources):
            handled = {}
            for resource in resources:
                dom = parse_domain(resource.get('dns-name'))
                if dom not in handled:
                    handled[dom] = True
                    yield (dom, len([d for d in resources
                           if parse_domain(d.get('dns-name')) == dom]))

        for dom_name, num_recs in _count_filter_records(resources):
            pile.spawn(self._check_record_limits, context, dom_name, max_recs,
                       num_recs)
        messages.extend([msg for msg in pile if msg])
        return messages

    def verify_access(self, context):
        roles = ['identity:user-admin', 'dnsaas:admin', 'dnsaas:creator']
        if user_has_access(context, roles):
            return {
                'type': "ACCESS-OK",
                'message': "You have access to create Cloud DNS records",
                'provider': self.name,
                'severity': "INFORMATIONAL"
            }
        else:
            return {
                'type': "NO-ACCESS",
                'message': ("You do not have access to create Cloud DNS"
                            " records"),
                'provider': self.name,
                'severity': "CRITICAL"
            }

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

    @staticmethod
    def proxy(path, request, tenant_id=None):
        """Proxy request through to provider"""
        if not path:
            raise CheckmateException("Provider expects "
                                     "{version}/{tenant}/{path}")
        parts = path.split("/")
        if len(parts) < 2:
            raise CheckmateException("Provider expects "
                                     "{version}/{tenant}/{path}")
        resource = parts[2]
        if resource == "domains":
            api = _get_dns_object(request.context)
            return Provider._my_list_domains_info(api, None) or []

        raise CheckmateException("Provider does not support the resource "
                                 "'%s'" % resource)

    @staticmethod
    def _find_url(catalog):
        for service in catalog:
            if service['name'] == 'cloudDNS':
                endpoints = service['endpoints']
                for endpoint in endpoints:
                    return endpoint['publicURL']

    @staticmethod
    def connect(context=None, token=None, url=None):
        """Use context info to connect to API and return api object"""

        if (not context) and not (token and url):
            raise ValueError("Must pass either a context or a token and url")

        if context:
            #FIXME: figure out better serialization/deserialization scheme
            if isinstance(context, dict):
                from checkmate.middleware import RequestContext
                context = RequestContext(**context)
            if not context.auth_token:
                raise CheckmateNoTokenError()
            token = context.auth_token
            url = Provider._find_url(context.catalog)

        class CloudDNS_Auth_Proxy(object):
            """We pass this class to clouddns for it to use instead of its own
            auth mechanism"""
            def __init__(self, url, token):
                self.url = url
                self.token = token

            def authenticate(self):
                """Called by clouddns. Expects back a url and token"""
                return (self.url, self.token)

        proxy = CloudDNS_Auth_Proxy(url=url, token=token)
        api = clouddns.connection.Connection(auth=proxy)
        LOG.debug("Connected to cloud DNS using token of length %s "
                  "and url of %s", len(token), url)
        return api


"""
  Celery tasks to manipulate Rackspace Cloud DNS
"""
from celery.task import task
import clouddns
from clouddns.errors import UnknownDomain, ResponseError, InvalidDomainName


def _get_dns_object(context):
    return Provider.connect(context)


def parse_domain(domain_str):
    """Return 'domain.com' for 'sub2.sub1.domain.com' """
    if not domain_str:
        return ""
    extractor = tldextract.TLDExtract(
        cache_file=os.environ.get('CHECKMATE_TLD_CACHE_FILE', None))
    domain_data = extractor(domain_str)
    return '%s.%s' % (domain_data.domain, domain_data.tld)

""" Celery tasks """


@task(default_retry_delay=10, max_retries=10)
def get_domains(context, limit=None, offset=None):
    match_celery_logging(LOG)
    api = _get_dns_object(context)
    try:
        domains = api.list_domains_info(limit=limit, offset=offset)
        LOG.debug('Successfully retrieved domains.')
        return domains
    except Exception as exc:
        LOG.debug('Error retrieving domains. Error: %s. Retrying.', exc)
        get_domains.retry(exc=exc)


@task(default_retry_delay=3, max_retries=20)
def create_domain(context, domain, email=None,
                  dom_ttl=300):
    match_celery_logging(LOG)
    api = _get_dns_object(context)
    if not email:
        email = "admin@%s" % domain
    try:
        doms = api.create_domain(name=domain, ttl=dom_ttl, emailAddress=email)
        LOG.debug('Domain %s created.' % domain)
        if hasattr(doms, "append"):
            doms = doms[0]
        ser_dom = doms.__dict__
        if "connection" in ser_dom:
            del ser_dom["connection"]
        return ser_dom
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


@task(default_retry_delay=3, max_retries=20)
def create_record(context, domain, name, dnstype, data,
                  rec_ttl=1800, makedomain=False,
                  email=None):
    """ Create a DNS record of the specified type for the specified domain """

    match_celery_logging(LOG)
    api = _get_dns_object(context)
    try:
        domain_object = api.get_domain(name=domain)
    except UnknownDomain:
        if makedomain:
            LOG.debug('Cannot create %s record (%s->%s) because domain "%s" '
                      'does not exist. Creating domain "%s".' % (
                      dnstype, name, data, domain, domain))
            if not email:
                email = "admin@%s" % domain
            domain_object = api.create_domain(domain, 300, emailAddress=email)
        else:
            msg = (
                'Cannot create %s record (%s->%s) because domain "%s" '
                'does not exist.' % (
                dnstype, name, data, domain)
            )
            LOG.error(msg)
            raise CheckmateException(msg)

    try:
        rec = domain_object.create_record(name, data, dnstype, ttl=rec_ttl)
        LOG.debug('Created DNS %s record %s -> %s. TTL: %s' % (
            dnstype, name, data, rec_ttl))
    except ResponseError as res_err:
        if "duplicate of" not in res_err.reason:
            create_record.retry(exc=res_err)
        else:
            LOG.warn('DNS record "%s" already exists for domain "%s"'
                     % (name, domain))
            rec = domain_object.get_record(name=name)

    ser_rec = rec.__dict__
    if rec.domain:
        ser_rec['domain'] = str(rec.domain.id)
    for key, val in ser_rec.iteritems():
        ser_rec[key] = str(val)
    return ser_rec


@task(default_retry_delay=5, max_retries=12)
def delete_record(context, domain_id, record_id):
    """ Delete the specified record """
    match_celery_logging(LOG)
    api = _get_dns_object(context)
    try:
        domain = api.get_domain_details(id=domain_id)
    except UnknownDomain, exc:
        LOG.debug('Cannot delete record %s because %s does not exist. '
                  'Refusing to retry.' % (record_id, domain_id))
        return
    except Exception as exc:
        msg = ('Error finding domain %s. Cannot delete record %s.'
               % (domain_id, record_id))
        LOG.error(msg, exc_info=True)
        raise CheckmateException(msg)
    try:
        record = domain.get_record(id=record_id)
        domain.delete_record(record.id)
        LOG.debug('Deleted DNS record %s.' % record_id)
        return True
    except ResponseError as res_err:
        LOG.debug('Error deleting DNS record %s. Error %s %s. Retrying.' % (
                  record_id, res_err.status, res_err.reason))
        delete_record.retry(exc=res_err)
    except Exception as exc:
        if "Not found" in exc.args[0]:
            return
        LOG.debug('Error deleting DNS record %s. Retrying.' % record_id,
                  exc_info=True)
        delete_record.retry(exc=exc)


@task(default_retry_delay=20, max_retries=10)
def delete_record_by_name(context, domain, name):
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
