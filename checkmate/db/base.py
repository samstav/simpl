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

'''


class DbBase(object):
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

    # DEPLOYMENTS
    def get_deployment(self, api_id, with_secrets=None):
        raise NotImplementedError()

    def get_deployments(self, tenant_id=None, with_secrets=None):
        raise NotImplementedError()

    def save_deployment(self, api_id, body, secrets=None, tenant_id=None):
        raise NotImplementedError()

    # BLUEPRINTS
    def get_blueprint(self, api_id):
        raise NotImplementedError()

    def get_blueprints(self):
        raise NotImplementedError()

    def save_blueprint(self, api_id, body):
        raise NotImplementedError()

    # COMPONENTS
    def get_component(self, api_id):
        raise NotImplementedError()

    def get_components(self):
        raise NotImplementedError()

    def save_component(self, api_id, body):
        raise NotImplementedError()

    # WORKFLOWS
    def get_workflow(self, api_id):
        raise NotImplementedError()

    def get_workflows(self):
        raise NotImplementedError()

    def save_workflow(self, api_id, body):
        raise NotImplementedError()

    def unlock_workflow(self, api_id, key):
        raise NotImplementedError()

    def lock_workflow(self, api_id):
        raise NotImplementedError()
