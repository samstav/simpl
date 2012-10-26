import logging
import os

import pymongo

from checkmate.classes import ExtensibleDict
from checkmate.db.common import *
from checkmate.exceptions import CheckmateDatabaseConnectionError
from checkmate.utils import merge_dictionary

LOG = logging.getLogger(__name__)


class Driver(DbBase):
    """MongoDB Database Driver"""
    _connection = None

    def __init__(self, *args, **kwargs):
        """Initializes globals for this driver"""
        DbBase.__init__(self, *args, **kwargs)
        self.connection_string = os.environ.get('CHECKMATE_CONNECTION_STRING',
                                                'mongodb://localhost')
        print "connection: %s" % self.connection_string

        self.db_name = pymongo.uri_parser.parse_uri(self.connection_string
                                                    ).get('database',
                                                          'checkmate')
        self._database = None

    def database(self):
        """Connects to and returns mongodb database object"""
        if self._database is None:
            if self._connection is None:
                try:
                    self._connection = pymongo.Connection(
                            self.connection_string)
                except pymongo.errors.AutoReconnect as exc:
                    raise CheckmateDatabaseConnectionError(exc.__str__())

            self._database = self._connection[self.db_name]
            LOG.info("Connected to mongodb on %s (database=%s)" %
                     (self.connection_string, self.db_name))
        return self._database

    def dump(self):
        response = {}
        response['environments'] = self.get_environments()
        response['deployments'] = self.get_deployments()
        response['blueprints'] = self.get_blueprints()
        response['workflows'] = self.get_workflows()
        response['components'] = self.get_components()
        return response

    # ENVIRONMENTS
    def get_environment(self, id, with_secrets=None):
        return self.get_object('environments', id, with_secrets)

    def get_environments(self, tenant_id=None, with_secrets=None):
        return self.get_objects('environments', tenant_id, with_secrets)

    def save_environment(self, id, body, secrets=None, tenant_id=None):
        return self.save_object('environments', id, body, secrets, tenant_id)

    # DEPLOYMENTS
    def get_deployment(self, id, with_secrets=None):
        return self.get_object('deployments', id, with_secrets)

    def get_deployments(self, tenant_id=None, with_secrets=None):
        return self.get_objects('deployments', tenant_id, with_secrets)

    def save_deployment(self, id, body, secrets=None, tenant_id=None):
        return self.save_object('deployments', id, body, secrets, tenant_id)

    #BLUEPRINTS
    def get_blueprint(self, id, with_secrets=None):
        return self.get_object('blueprints', id, with_secrets)

    def get_blueprints(self, tenant_id=None, with_secrets=None):
        return self.get_objects('blueprints', tenant_id, with_secrets)

    def save_blueprint(self, id, body, secrets=None, tenant_id=None):
        return self.save_object('blueprints', id, body, secrets, tenant_id)

    # COMPONENTS
    def get_component(self, id, with_secrets=None):
        return self.get_object('components', id, with_secrets)

    def get_components(self, tenant_id=None, with_secrets=None):
        return self.get_objects('components', tenant_id, with_secrets)

    def save_component(self, id, body, secrets=None, tenant_id=None):
        return self.save_object('components', id, body, secrets, tenant_id)

    # WORKFLOWS
    def get_workflow(self, id, with_secrets=None):
        return self.get_object('workflows', id, with_secrets)

    def get_workflows(self, tenant_id=None, with_secrets=None):
        return self.get_objects('workflows', tenant_id, with_secrets)

    def save_workflow(self, id, body, secrets=None, tenant_id=None):
        return self.save_object('workflows', id, body, secrets, tenant_id)

    # GENERIC
    def get_object(self, klass, id, with_secrets=None):
        results = self.database()[klass].find_one({'_id': id}, {'_id': 0})
        if results:
            if with_secrets is True:
                secrets = self.database()['%s_secrets' % klass].find_one(
                        {'_id': id}, {'_id': 0})
                if secrets:
                    return merge_dictionary(results, secrets)
                else:
                    return results
            else:
                return results

    def get_objects(self, klass, tenant_id=None, with_secrets=None):
        if tenant_id:
            results = self.database()[klass].find({'tenantId': tenant_id},
                    {'_id': 0})
        else:
            results = self.database()[klass].find(None, {'_id': 0})
        if results:
            response = {}
            if with_secrets is True:
                for entry in results:
                    secrets = self.database()['%s_secrets' % klass].find_one(
                            {'_id': entry['id']}, {'_id': 0})
                    if secrets:
                        response[entry['id']] = utils.merge_dictionary(entry,
                                                                       secrets)
                    else:
                        response[entry['id']] = entry
            else:
                for entry in results:
                    response[entry['id']] = entry
             #If only one entry returned, change to 1-entry format
            if len(response) is 1:
                key = response.keys()[0]
                response = response[key]
            return response
        else:
            return {}

    def save_object(self, klass, id, body, secrets=None, tenant_id=None):
        """Clients that wish to save the body but do/did not have access to
        secrets will by default send in None for secrets. We must not have that
        overwrite the secrets. To clear the secrets for an object, a non-None
        dict needs to be passed in: ex. {}
        """
        if isinstance(body, ExtensibleDict):
            body = body.__dict__()
        assert isinstance(body, dict), "dict required by backend"
        assert 'id' in body, "id required to be in body by backend"

        if secrets is not None:
            if not secrets:
                LOG.warning("Clearing secrets for %s:%s" % (klass, id))
                #TODO: to catch bugs. We can remove when we're comfortable
                assert False, "CLEARING CREDS! Is that intended?!!!!"

        if tenant_id:
            body['tenantId'] = tenant_id
        assert tenant_id or 'tenantId' in body, "tenantId must be specified"
        body['_id'] = id
        self.database()[klass].update({'_id': id}, body, True, False)
        if secrets:
            secrets['_id'] = id
            self.database()['%s_secrets' % klass].update({'_id': id}, secrets,
                    True, False)
        del body['_id']
        return body

    def delete_object(self, klass, id, body):
        result = self.database()[klass].remove(body)
