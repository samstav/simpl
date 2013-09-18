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

"""Shim (Helper) for MongoDB."""
import logging

from checkmate import db

LOG = logging.getLogger(__name__)
COLLECTIONS_TO_CLEAN = ['tenants',
                        'deployments',
                        'blueprints',
                        'resource_secrets',
                        'resources']

try:
    import mongobox as mbox
except ImportError as exc:
    LOG.warn("Unable to import MongoBox. MongoDB tests will not run: %s", exc)
    raise


class Shim(object):
    """Abstraction layer for MongoDB testing using MongoBox."""
    def __init__(self):
        """Fire up a sandboxed mongodb instance."""
        try:
            self.box = mbox.MongoBox(scripting=True)
            self.box.start()
            self.connection_string = ("mongodb://localhost:%s/test" %
                                      self.box.port)
            self.driver = None
        except StandardError as exc:
            LOG.exception(exc)
            if hasattr(self, 'box'):
                del self.box

    def stop(self):
        """Stop the sanboxed mongodb instance."""
        if self.box.running() is True:
            self.box.stop()
        self.box = None

    def start(self):
        """Get the DB driver, passing in connection_string to set it up."""
        if self.connection_string:
            self.driver = db.get_driver(
                connection_string=self.connection_string, reset=True)

    def clean(self):
        """Drop all collections listed in CLEECTIONS_TO_CLEAN."""
        for collection_name in COLLECTIONS_TO_CLEAN:
            self.driver.database()[collection_name].drop()
