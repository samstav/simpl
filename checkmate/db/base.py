'''
Signature for Database Driver Modules

The API defines IDs as 32 character strings. The API ID is passed in to the
driver calls. It is up to the driver to map that to a native ID and abstract
the native ID away from the API.

The API ID is not necessarily a UUID. Allowed charatcers are:

    abcdefghijklmnopqrstuvwxyz
    ABCDEFGHIJKLMNOPQRSTUVWXYZ
    0123456789
    -_.+~@

The ID must start with an alphanumeric character.

TODO:
- implement partial saves (formalize what we do in save_deployment)

'''
import logging

LOG = logging.getLogger()


class DbBase(object):  # pylint: disable=R0921
    '''Interface for all database drivers'''

    def __init__(self, connection_string, driver=None, *args, **kwargs):
        '''Initialize database driver

        Drivers can also be serialized/deserialized from strings which are
        effectively the connection strings.

        :param connection_string: required and determines the key for this
                                  driver which will be used to share it between
                                  modules
        :param driver: used to inject a driver for testing or connection
                       sharing
        '''
        LOG.debug("Initializing driver %s with connection_string='%s', "
                  "args=%s, driver=%s, and kwargs=%s", self.__class__.__name__,
                  connection_string, args, driver, kwargs)
        self.connection_string = connection_string
        self.driver = driver

    def __getstate__(self):
        '''Support serializing to connection string'''
        return {'connection_string': self.connection_string}

    def __setstate__(self, dict):  # pylint: disable=W0622
        '''Support deserializing from connection string'''
        self.connection_string = dict['connection_string']

    def __str__(self):
        '''Support serializing to connection string'''
        return self.connection_string

    def __repr__(self):
        '''Support displaying connection string'''
        return ("<%s.%s connection_string='%s'>" % (self.__class__.__module__,
                self.__class__.__name__, self.connection_string))

    def dump(self):
        '''Dump all data n the database'''
        raise NotImplementedError()

    # ENVIRONMENTS
    def get_environment(self, api_id, with_secrets=None):
        '''Get the environment that matches the API ID supplied

        :param api_id: the API ID of the environment to get
        :param with_secrets: set to true to also return passwords and keys
        :returns: dict -- the environment
        '''
        raise NotImplementedError()

    def get_environments(self, tenant_id=None, with_secrets=None):
        '''Get a list of environments that matches the tenant ID supplied

        :param tenant_id: the tenant ID for which to return environments
        :param with_secrets: set to true to also return passwords and keys
        :returns: dict -- a dict of all environments where the key is the
                  environment ID
        '''
        raise NotImplementedError()

    def save_environment(self, api_id, body, secrets=None, tenant_id=None):
        '''Save (Update or Create) an environment

        :param api_id: the API ID of the environment to store
        :param body: the dict of the environment to store
        :param secrets: the dict of any secrets in the environment
        :param tenant_id: the tenant ID for which to save the environment
        :returns: dict -- the saved environment (some changes such as a
                  _modified by_ date may have taken place)

        Note:: Use utils.extract_sensitive_keys to split secrets from the body
        '''
        raise NotImplementedError()

    # TENANTS
    def save_tenant(self, tenant):
        raise NotImplementedError()

    def list_tenants(self, *args):
        raise NotImplementedError()

    def get_tenant(self, tenant_id):
        raise NotImplementedError()

    def add_tenant_tags(self, tenant_id, *args):
        raise NotImplementedError()

    def remove_tenant_tags(self, tenant_id, *args):
        raise NotImplementedError()

    # DEPLOYMENTS
    def get_deployment(self, api_id, with_secrets=None):
        raise NotImplementedError()

    def get_deployments(self, tenant_id=None, with_secrets=None,
                        limit=None, offset=None, with_deleted=False):
        raise NotImplementedError()

    def save_deployment(self, api_id, body, secrets=None, tenant_id=None,
                        partial=False):
        raise NotImplementedError()

    # BLUEPRINTS
    def get_blueprint(self, api_id, with_secrets=None):
        raise NotImplementedError()

    def get_blueprints(self, tenant_id=None, with_secrets=None,
                       limit=None, offset=None):
        raise NotImplementedError()

    def save_blueprint(self, api_id, body, secrets=None, tenant_id=None):
        raise NotImplementedError()

    # WORKFLOWS
    def get_workflow(self, api_id, with_secrets=None):
        raise NotImplementedError()

    def get_workflows(self, tenant_id=None, with_secrets=None,
                      limit=None, offset=None):
        raise NotImplementedError()

    def save_workflow(self, api_id, body, secrets=None, tenant_id=None):
        raise NotImplementedError()

    def unlock_workflow(self, api_id, key):
        raise NotImplementedError()

    def lock_workflow(self, api_id, with_secrets=None, key=None):
        raise NotImplementedError()

    def lock_object(self, klass, api_id, with_secrets=None, key=None):
        raise NotImplementedError()

    def unlock_object(self, klass, api_id, key):
        raise NotImplementedError()

    #
    # Data conversion helper
    # TODO(zns): remove this when we're done
    #
    legacy_statuses = {  # TODO: remove these when old data is clean
        "BUILD": 'UP',
        "CONFIGURE": 'UP',
        "ACTIVE": 'UP',
        'ERROR': 'FAILED',
        'DELETING': 'UP',
        'LAUNCHED': 'UP',
    }

    def convert_data(self, klass, data):
        if klass == 'deployments':
            if 'errmessage' in data:
                data['error-message'] = data.pop('errmessage')
            if 'error_messages' in data:
                data['error-message'] = data.pop('error_messages')
            if 'status' in data:
                if data['status'] in self.legacy_statuses:
                    data['status'] = self.legacy_statuses[data['status']]
            if 'resources' in data and isinstance(data['resources'], dict):
                self.convert_data('resources', data['resources'])  # legacy
            if 'display-outputs' in data and data['display-outputs'] is None:
                data['display-outputs'] = {}
        elif klass == 'resources':
            for _, resource in data.items():
                if 'statusmsg' in resource:
                    resource['status-message'] = resource.pop('statusmsg')
                if 'instance' in resource and isinstance(resource['instance'],
                                                         dict):
                    instance = resource['instance']
                    if 'statusmsg' in instance:
                        instance['status-message'] = instance.pop('statusmsg')
                    if 'status_msg' in instance:
                        instance['status-message'] = instance.pop('status_msg')
                    if ('errmessage' in instance and
                          'error-message' not in instance):
                        instance['error-message'] = instance.pop('errmessage')
                    elif ('errmessage' in resource and
                          'error-message' not in instance):
                        instance['error-message'] = resource.pop('errmessage')
                    if ('trace' in instance and
                          'error-traceback' not in instance):
                        instance['error-traceback'] = instance.pop('trace')
                    elif ('trace' in resource and
                          'error-traceback' not in instance):
                        instance['error-traceback'] = resource.pop('trace')
                    if 'errmessage' in instance:
                        del instance['errmessage']
                    if 'errmessage' in resource:
                        del resource['errmessage']
                    if 'trace' in instance:
                        del instance['trace']
                    if 'trace' in resource:
                        del resource['trace']

    def lock(self, key, timeout):
        raise NotImplementedError()

    def unlock(self, key):
        raise NotImplementedError()

    def acquire_lock(self, key, timeout):
        raise NotImplementedError()

    def release_lock(self, key):
        raise NotImplementedError()
