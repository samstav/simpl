
class DbBase(object):
    def dump(self):
        raise NotImplementedError()

    # ENVIRONMENTS
    def get_environment(self, id):
        raise NotImplementedError()

    def get_environments(self):
        raise NotImplementedError()

    def save_environment(self, id, body):
        raise NotImplementedError()

    # DEPLOYMENTS
    def get_deployment(self, id):
        raise NotImplementedError()

    def get_deployments(self):
        raise NotImplementedError()

    def save_deployment(self, id, body):
        raise NotImplementedError()

    # BLUEPRINTS
    def get_blueprint(self, id):
        raise NotImplementedError()

    def get_blueprints(self):
        raise NotImplementedError()

    def save_blueprint(self, id, body):
        raise NotImplementedError()

    # COMPONENTS
    def get_component(self, id):
        raise NotImplementedError()

    def get_components(self):
        raise NotImplementedError()

    def save_component(self, id, body):
        raise NotImplementedError()
