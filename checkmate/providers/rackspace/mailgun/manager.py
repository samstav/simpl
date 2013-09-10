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
"""
Mailgun manager module.
"""
import logging

import pyrax

from checkmate import exceptions as cex
from checkmate import utils

LOG = logging.getLogger(__name__)


class Manager(object):
    '''Contains mailgun provider model and logic for interaction.'''

    @staticmethod
    def create_domain(domain_name, password, context, api, simulate=False):
        '''Creates specified domain in Mailgun for relaying.'''
        exists = False
        if simulate:
            domain = utils.Simulation(id=domain_name, name=domain_name,
                                      smtp_login='postmaster@%s' % domain_name,
                                      smtp_password=password)
        else:
            if not domain_name:
                uid = context.get('deployment').split('-')[0]
                domain_name = 'rsd%s.mailgun.org' % uid
            try:
                domain = api.create(domain_name, smtp_pass=password)
            except pyrax.exceptions.DomainRecordNotUnique:
                exists = True
                domain = api.get(domain_name)
            except pyrax.exceptions.ClientException as exc:
                LOG.exception(exc)
                if exc.code == '400':
                    raise
                else:
                    raise cex.CheckmateResumableException(str(exc),
                                                          str(exc.details),
                                                          cex.UNEXPECTED_ERROR,
                                                          '')
            except StandardError as exc:
                raise cex.CheckmateUserException(str(exc),
                                                 utils.get_class_name(exc),
                                                 cex.UNEXPECTED_ERROR, '')
        
        results = {
            'id': domain.id,
            'name': domain.name,
            'status': 'ACTIVE',
            'exists': exists,
            'interfaces': {
                'smtp': {
                    'host': 'smtp.mailgun.org',
                    'port': 587,
                    'smtp_login': domain.smtp_login,
                    'smtp_password': domain.smtp_password
                }
            },
        }
        return results

    @staticmethod
    def delete_domain(domain_name, api, simulate=False):
        '''Deletes a domain from Mailgun.'''
        if simulate:
            status = 'DELETED'
        else:
            try:
                api.delete(domain_name)
                status = 'DELETED'
            except pyrax.exceptions.DomainRecordNotFound as exc:
                status = 'DELETED'
            except (pyrax.exceptions.DomainDeletionFailed,
                    pyrax.exceptions.ClientException) as exc:
                if exc.code == '400':
                    raise
                else:
                    raise cex.CheckmateResumableException(str(exc),
                                                          str(exc.details),
                                                          cex.UNEXPECTED_ERROR,
                                                          '')
            except StandardError as exc:
                raise cex.CheckmateUserException(str(exc),
                                                 utils.get_class_name(exc),
                                                 cex.UNEXPECTED_ERROR, '')
        results = {
            'id': domain_name,
            'name': domain_name,
            'status': status,
            'interfaces': {}
        }
        return results
