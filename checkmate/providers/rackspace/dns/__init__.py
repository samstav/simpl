'''Rackspace Cloud DNS provider'''
import logging

from celery import task
from clouddns.errors import UnknownDomain, ResponseError, InvalidDomainName

from checkmate.common import statsd
from checkmate import utils
from checkmate.exceptions import (
    CheckmateException,
    CheckmateUserException,
    UNEXPECTED_ERROR,
)
import checkmate.middleware
import checkmate.providers
import checkmate.providers.base
from checkmate.providers.rackspace.dns.provider import (
    _get_dns_object,
    Provider,
)

LOG = logging.getLogger(__name__)


### Celery tasks
@task(default_retry_delay=10, max_retries=10)
@statsd.collect
def get_domains(context, limit=None, offset=None):
    '''Returns list of domains for an account.'''
    checkmate.utils.match_celery_logging(LOG)
    api = _get_dns_object(context)
    try:
        domains = api.list_domains_info(limit=limit, offset=offset)
        LOG.debug('Successfully retrieved domains.')
        return domains
    except StandardError as exc:
        LOG.debug('Error retrieving domains. Error: %s. Retrying.', exc)
        get_domains.retry(exc=exc)


@task(default_retry_delay=3, max_retries=20)
@statsd.collect
def create_domain(context, domain, email=None,
                  dom_ttl=300):
    '''Create zone.'''
    checkmate.utils.match_celery_logging(LOG)
    api = _get_dns_object(context)
    if not email:
        email = "admin@%s" % domain
    try:
        doms = api.create_domain(name=domain, ttl=dom_ttl, emailAddress=email)
        LOG.debug('Domain %s created.', domain)
        if hasattr(doms, "append"):
            doms = doms[0]
        ser_dom = doms.__dict__
        if "connection" in ser_dom:
            del ser_dom["connection"]
        return ser_dom
    except InvalidDomainName as exc:
        LOG.debug('Domain %s is invalid.  Refusing to retry.', domain)
        raise exc
    except ResponseError as resp_error:
        LOG.debug('Error creating domain %s.(%s) %s. Retrying.', domain,
                  resp_error.status, resp_error.reason)
        create_domain.retry(exc=resp_error)
    except Exception as exc:
        LOG.debug('Unknown error creating domain %s. Error: %s. Retrying.',
                  domain, str(exc))
        create_domain.retry(exc=exc)


@task
@statsd.collect
def delete_domain(context, name):
    '''Find and delete the specified domain name.'''
    checkmate.utils.match_celery_logging(LOG)
    api = _get_dns_object(context)
    try:
        domain = api.get_domain(name=name)
    except UnknownDomain, exc:
        LOG.debug('Cannot deleted domain %s because it does not exist. '
                  'Refusing to retry.', name)
        return
    except Exception, exc:
        LOG.debug('Exception getting domain %s. Was hoping to delete it. '
                  'Error %s. Retrying.', name, str(exc))
        delete_domain.retry(exc=exc)

    try:
        api.delete_domain(domain.id)
        LOG.debug('Domain %s deleted.', name)
    except ResponseError, resp_error:
        LOG.debug('Error deleting domain %s (%s) %s. Retrying.', name,
                  resp_error.status, resp_error.reason)
        delete_domain.retry(exc=resp_error)
    except Exception, exc:
        LOG.debug('Error deleting domain %s. Error %s. Retrying.', name,
                  str(exc))
        delete_domain.retry(exc=exc)


@task(default_retry_delay=3, max_retries=20)
@statsd.collect
def create_record(context, domain, name, dnstype, data,
                  rec_ttl=1800, makedomain=False,
                  email=None):
    '''Create a DNS record of the specified type for the specified domain.'''
    checkmate.utils.match_celery_logging(LOG)
    api = _get_dns_object(context)
    try:
        domain_object = api.get_domain(name=domain)
    except UnknownDomain:
        if makedomain:
            LOG.debug('Cannot create %s record (%s->%s) because domain "%s" '
                      'does not exist. Creating domain "%s".', dnstype, name,
                      data, domain, domain)
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
            raise CheckmateUserException(msg, utils.get_class_name(
                Exception), UNEXPECTED_ERROR, '')

    try:
        rec = domain_object.create_record(name, data, dnstype, ttl=rec_ttl)
        LOG.debug('Created DNS %s record %s -> %s. TTL: %s', dnstype, name,
                  data, rec_ttl)
    except ResponseError as resp_error:
        if "duplicate of" not in resp_error.reason:
            create_record.retry(exc=resp_error)
        else:
            LOG.warn('DNS record "%s" already exists for domain "%s"', name,
                     domain)
            rec = domain_object.get_record(name=name)

    ser_rec = rec.__dict__
    if rec.domain:
        ser_rec['domain'] = str(rec.domain.id)
    for key, val in ser_rec.iteritems():
        ser_rec[key] = str(val)
    return ser_rec


@task(default_retry_delay=5, max_retries=12)
@statsd.collect
def delete_record_task(context, domain_id, record_id):
    '''Delete the specified record.'''
    checkmate.utils.match_celery_logging(LOG)
    api = _get_dns_object(context)
    try:
        domain = api.get_domain_details(id=domain_id)
    except UnknownDomain, exc:
        LOG.debug('Cannot delete record %s because %s does not exist. '
                  'Refusing to retry.', record_id, domain_id)
        return
    except Exception as exc:
        msg = ('Error finding domain %s. Cannot delete record %s.'
               % (domain_id, record_id))
        LOG.error(msg, exc_info=True)
        raise CheckmateUserException(msg, utils.get_class_name(
            CheckmateException), UNEXPECTED_ERROR, '')
    try:
        record = domain.get_record(id=record_id)
        domain.delete_record(record.id)
        LOG.debug('Deleted DNS record %s.', record_id)
        return True
    except ResponseError as resp_error:
        LOG.debug('Error deleting DNS record %s. Error %s %s. Retrying.',
                  record_id, resp_error.status, resp_error.reason)
        delete_record_task.retry(exc=resp_error)
    except Exception as exc:
        if "Not found" in exc.args[0]:
            return
        LOG.debug('Error deleting DNS record %s. Retrying.', record_id,
                  exc_info=True)
        delete_record_task.retry(exc=exc)


@task(default_retry_delay=20, max_retries=10)
@statsd.collect
def delete_record_by_name(context, domain, name):
    '''Find the DNS record by name and delete it.'''
    checkmate.utils.match_celery_logging(LOG)
    api = _get_dns_object(context)
    try:
        domain = api.get_domain(name=domain)
    except UnknownDomain, exc:
        LOG.debug('Cannot delete record %s because %s does not exist. '
                  'Refusing to retry.', name, domain)
        return
    except Exception, exc:
        LOG.debug('Error finding domain %s.  Wanting to delete record %s. '
                  'Error %s. Retrying.', domain, name, str(exc))
        delete_record_task.retry(exc=exc)

    try:
        record = domain.get_record(name=name)
        domain.delete_record(record.id)
        LOG.debug('Deleted DNS record %s.', name)
    except ResponseError, resp_error:
        LOG.debug('Error deleting DNS record %s. Error %s %s. Retrying.',
                  name, resp_error.status, resp_error.reason)
        delete_record_task.retry(exc=resp_error)
    except Exception, exc:
        LOG.debug('Error deleting DNS record %s. Error %s. Retrying.', name,
                  str(exc))
        delete_record_task.retry(exc=exc)
