# Copyright (c) 2011-2015 Rackspace US, Inc.
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

"""Tenants."""

import logging

from checkmate import db
from checkmate import exceptions as cmexc

LOG = logging.getLogger(__name__)


class Manager(object):

    """Tenants Model and Logic for Accessing Tenants."""

    @staticmethod
    def list_tenants(*tags):
        """Get existing tenants."""
        return db.get_driver().list_tenants(*tags)

    @staticmethod
    def save_tenant(tenant_id, body):
        """Save tenant (and overwrite)."""
        body['id'] = tenant_id
        db.get_driver().save_tenant({
            'id': tenant_id,
            'tags': body.get('tags', []),
        })

    @staticmethod
    def get_tenant(tenant_id):
        """Get a single tenant."""
        if tenant_id:
            tenant = db.get_driver().get_tenant(tenant_id)
            if not tenant:
                raise cmexc.CheckmateDoesNotExist('No tenant %s' % tenant_id)
            return tenant

    @staticmethod
    def add_tenant_tags(tenant_id, *tags):
        """Add a set of tags to an individual tenant."""
        if tenant_id:
            if tags is None:
                tags = []
            elif not isinstance(tags, (list, tuple)):
                tags = [tags]
            db.get_driver().add_tenant_tags(tenant_id, *tags)
