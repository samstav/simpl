# Copyright (c) 2011-2013 Rackspace Hosting
# All Rights Reserved.
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

'''Rackspace Cloud DNS provider'''
import logging

from celery import task
import pyrax

from checkmate.common import statsd
from checkmate import exceptions
import checkmate.middleware
import checkmate.providers
import checkmate.providers.base
from checkmate.providers.rackspace.dns import provider
from checkmate import utils

LOG = logging.getLogger(__name__)


### Celery tasks
@task(default_retry_delay=10, max_retries=10)
@statsd.collect
def get_domains(context, limit=None, offset=None):
    '''Returns list of domains for an account.'''
    checkmate.utils.match_celery_logging(LOG)
    api = provider.Provider.connect(context)
    try:
        domains = api.list(limit=limit, offset=offset)
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
    utils.match_celery_logging(LOG)
    api = provider.Provider.connect(context)
    if not email:
        email = "admin@%s" % domain
    try:
        doms = api.create(name=domain, ttl=dom_ttl, emailAddress=email)
        LOG.debug('Domain %s created.', domain)
        if hasattr(doms, "append"):
            doms = doms[0]
        ser_dom = doms.__dict__
        if "connection" in ser_dom:
            del ser_dom["connection"]
        return ser_dom
    except pyrax.exceptions.DomainRecordAdditionFailed as exc:
        LOG.debug('Domain %s is invalid.  Refusing to retry.', domain)
        raise exc
    except pyrax.exceptions.ClientException as resp_error:
        LOG.debug('Error creating domain %s.(%s) %s. Retrying.', domain,
                  resp_error.code, resp_error.message)
        create_domain.retry(exc=resp_error)
    except StandardError as exc:
        LOG.debug('Unknown error creating domain %s. Error: %s. Retrying.',
                  domain, str(exc))
        create_domain.retry(exc=exc)


@task
@statsd.collect
def delete_domain(context, name):
    '''Find and delete the specified domain name.'''
    utils.match_celery_logging(LOG)
    api = provider.Provider.connect(context)
    try:
        domain = api.find(name=name)
    except pyrax.exceptions.NotFound as exc:
        LOG.debug('Cannot deleted domain %s because it does not exist. '
                  'Refusing to retry.', name)
        return
    except StandardError as exc:
        LOG.debug('Exception getting domain %s. Was hoping to delete it. '
                  'Error %s. Retrying.', name, str(exc))
        delete_domain.retry(exc=exc)

    try:
        api.delete(domain)
        LOG.debug('Domain %s deleted.', name)
    except pyrax.exceptions.DomainDeletionFailed as resp_error:
        LOG.debug('Error deleting domain %s (%s) %s. Retrying.', name,
                  resp_error.code, resp_error.message)
        delete_domain.retry(exc=resp_error)
    except StandardError as exc:
        LOG.debug('Error deleting domain %s. Error %s. Retrying.', name,
                  str(exc))
        delete_domain.retry(exc=exc)


@task(default_retry_delay=3, max_retries=20)
@statsd.collect
def create_record(context, domain, name, dnstype, data,
                  rec_ttl=1800, makedomain=False,
                  email=None):
    '''Create a DNS record of the specified type for the specified domain.'''
    utils.match_celery_logging(LOG)
    api = provider.Provider.connect(context)
    try:
        domain_object = api.find(name=domain)
    except pyrax.exceptions.NotFound:
        if makedomain:
            LOG.debug('Cannot create %s record (%s->%s) because domain "%s" '
                      'does not exist. Creating domain "%s".', dnstype, name,
                      data, domain, domain)
            if not email:
                email = "admin@%s" % domain
            domain_object = api.create(name=domain, ttl=300,
                                       emailAddress=email)
        else:
            msg = (
                'Cannot create %s record (%s->%s) because domain "%s" '
                'does not exist.' % (
                dnstype, name, data, domain)
            )
            LOG.error(msg)
            raise exceptions.CheckmateException(msg)
    record = {
        'name': name,
        'type': dnstype,
        'data': data,
        'ttl': rec_ttl
    }
    try:
        rec = domain_object.add_record(record)[0]
        LOG.debug('Created DNS %s record %s -> %s. TTL: %s', dnstype, name,
                  data, rec_ttl)
    except pyrax.exceptions.DomainRecordAdditionFailed as resp_error:
        if "duplicate of" not in resp_error.message:
            create_record.retry(exc=resp_error)
        else:
            LOG.warn('DNS record "%s" already exists for domain "%s"', name,
                     domain)
            rec = domain_object.get_record(name=name)

    ser_rec = rec.__dict__
    if rec.domain_id:
        ser_rec['domain'] = str(rec.domain_id)
    for key, val in ser_rec.iteritems():
        ser_rec[key] = str(val)
    return ser_rec


@task(default_retry_delay=5, max_retries=12)
@statsd.collect
def delete_record_task(context, domain_id, record_id):
    '''Delete the specified record.'''
    utils.match_celery_logging(LOG)
    api = provider.Provider.connect(context)
    try:
        domain = api.get(item=domain_id)
    except pyrax.exceptions.NotFound as exc:
        LOG.debug('Cannot delete record %s because %s does not exist. '
                  'Refusing to retry.', record_id, domain_id)
        return
    except StandardError as exc:
        msg = ('Error finding domain %s. Cannot delete record %s.'
               % (domain_id, record_id))
        LOG.error(msg, exc_info=True)
        raise exceptions.CheckmateException(msg)
    try:
        domain.delete_record(record=record_id)
        LOG.debug('Deleted DNS record %s.', record_id)
        return True
    except pyrax.exceptions.NotFound as exc:
        return
    except pyrax.exceptions.ClientException as resp_error:
        LOG.debug('Error deleting DNS record %s. Error %s %s. Retrying.',
                  record_id, resp_error.status, resp_error.reason)
        delete_record_task.retry(exc=resp_error)
    except StandardError as exc:
        LOG.debug('Error deleting DNS record %s. Retrying.', record_id,
                  exc_info=True)
        delete_record_task.retry(exc=exc)


@task(default_retry_delay=20, max_retries=10)
@statsd.collect
def delete_record_by_name(context, domain, name):
    '''Find the DNS record by name and delete it.'''
    utils.match_celery_logging(LOG)
    api = provider.Provider.connect(context)
    try:
        domain = api.get(name=domain)
    except pyrax.exceptions.NotFound as exc:
        LOG.debug('Cannot delete record %s because %s does not exist. '
                  'Refusing to retry.', name, domain)
        return
    except StandardError as exc:
        LOG.debug('Error finding domain %s.  Wanting to delete record %s. '
                  'Error %s. Retrying.', domain, name, str(exc))
        delete_record_task.retry(exc=exc)

    try:
        record = domain.find_record(name=name, record_type='A')
        domain.delete_record(record.id)
        LOG.debug('Deleted DNS record %s.', name)
    except pyrax.exceptions.ClientException as resp_error:
        LOG.debug('Error deleting DNS record %s. Error %s %s. Retrying.',
                  name, resp_error.status, resp_error.reason)
        delete_record_task.retry(exc=resp_error)
    except StandardError as exc:
        LOG.debug('Error deleting DNS record %s. Error %s. Retrying.', name,
                  str(exc))
        delete_record_task.retry(exc=exc)
