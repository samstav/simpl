import logging
import os

import pymongo

from checkmate.classes import ExtensibleDict
from checkmate.db.common import *
from checkmate.utils import merge_dictionary

LOG = logging.getLogger(__name__)

CONNECTION_STRING = os.environ.get('CHECKMATE_CONNECTION_STRING',
        'mongodb://localhost')

_CONNECTION = pymongo.Connection(CONNECTION_STRING)

DB_NAME = pymongo.uri_parser.parse_uri(CONNECTION_STRING).get('database',
        'checkmate')
_DB = _CONNECTION[DB_NAME]
LOG.info("Connected to mongodb on %s (database=%s)" % (CONNECTION_STRING,
        DB_NAME))


class Driver(DbBase):
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
        results = _DB[klass].find_one({'_id': id}, {'_id': 0})
        if results:
            if with_secrets == True:
                secrets = _DB['%s_secrets' % klass].find_one({'_id': id},
                        {'_id': 0})
                if secrets:
                    return merge_dictionary(results, secrets)
                else:
                    return results
            else:
                return results

    def get_objects(self, klass, tenant_id=None, with_secrets=None):
        if tenant_id:
            results = _DB[klass].find({'tenantId': tenant_id},
                    {'_id': 0})
        else:
            results = _DB[klass].find(None, {'_id': 0})
        if results:
            response = {}
            if with_secrets == True:
                for e in results:
                    secrets = _DB['%s_secrets' % klass].find_one(
                            {'_id': e['id']}, {'_id': 0})
                    if secrets:
                        response[e['id']] = utils.merge_dictionary(e, secrets)
                    else:
                        response[e['id']] = e
            else:
                for e in results:
                    print e
                    response[e['id']] = e
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
        assert isinstance(body, dict), "dict required by sqlalchemy backend"

        if secrets is not None:
            if not secrets:
                LOG.warning("Clearing secrets for %s:%s" % (klass, id))
                #TODO: to catch bugs. We can remove when we're comfortable
                raise Exception("CLEARING CREDS! Why?!!!!")

        if tenant_id:
            body['tenantId'] = tenant_id
        assert tenant_id or 'tenantId' in body, "tenantId must be specified"
        body['_id'] = id
        _DB[klass].update({'_id': id}, body, True, False)
        body['_id'] = id
        _DB[klass].update({'_id': id}, body, True, False)
        if secrets:
            secrets['_id'] = id
            _DB['%s_secrets' % klass].update({'_id': id}, secrets,
                    True, False)
        del body['_id']
        return body
