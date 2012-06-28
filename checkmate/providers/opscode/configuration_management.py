import logging

from SpiffWorkflow.operators import Attrib
from SpiffWorkflow.specs import Celery, Merge, Transform

from checkmate.exceptions import CheckmateException
from checkmate.providers import ProviderBase, register_providers
from checkmate.utils import get_source_body
from checkmate.workflows import wait_for

LOG = logging.getLogger(__name__)


class LocalProvider(ProviderBase):
    name = 'chef-local'
    vendor = 'opscode'

    """Implements a Chef Local/Solo configuration management provider"""
    def __init__(self, provider, key=None):
        ProviderBase.__init__(self, provider, key=key)
        self.prep_task = None

    def prep_environment(self, wfspec, deployment):
        if self.prep_task is not None:
            return  # already prepped
        create_environment = Celery(wfspec, 'Create Chef Environment',
                'stockton.cheflocal.distribute_create_environment',
                call_args=[deployment['id']],
                defines=dict(provider=self.key,
                            task_tags=['root']),
                properties={'estimated_duration': 10})

        def write_keys_code(my_task):
            if 'environment' not in my_task.attributes['context']['keys']:
                my_task.attributes['context']['keys']['environment'] = {}
            data = my_task.attributes['context']['keys']['environment']
            if 'public_key' not in data:
                data['public_key'] = my_task.attributes['public_key']
            if 'public_key_path' not in data:
                data['public_key_path'] = my_task.attributes.get(
                        'public_key_path')
            if 'private_key_path' not in data:
                data['private_key_path'] = my_task.attributes.get(
                        'private_key_path')

        write_keys = Transform(wfspec, "Get Environment Key",
                transforms=[get_source_body(write_keys_code)],
                description="Add environment public key data to context so "
                        "providers have access to them",
                defines=dict(provider=self.key,
                            task_tags=['final', 'prep', 'environment keys']))
        create_environment.connect(write_keys)
        self.prep_task = write_keys

        return dict(root=create_environment, final=write_keys)

    def add_resource_tasks(self, resource, key, wfspec, deployment, context,
                wait_on=None):
        if wait_on is None:
            wait_on = []
        self.add_wait_on_host_tasks(resource, wfspec, deployment, wait_on)

        # Add tasks
        register_node_task = Celery(wfspec, 'Register Server:%s' % key,
                'stockton.cheflocal.distribute_register_node',
                call_args=[Attrib('ip'), deployment['id']],
                password=Attrib('password'),
                omnibus_version="0.10.10-1",
                defines=dict(resource=key,
                            provider=self.key,
                            task_tags=['root']),
                description="Install Chef client on the target machine and "
                       "register it in the environment",
                properties={'estimated_duration': 120})

        # Register only when server is up and environment is ready
        if wait_on:
            tasks = wait_on[:]
            tasks.append(self.prep_task)
            root = wait_for(wfspec, register_node_task, tasks, name="Check "
                    "that Environment is Ready and Server is Up:%s" % key)
        else:
            self.prep_task.connect(register_node_task)
            root = register_node_task

        def build_bag_code(my_task):
            bag = {
                "mysql": {
                  "db_user": my_task.attributes['context']['db_username'],
                  "db_password": my_task.attributes['context']['db_password'],
                  "db_name": my_task.attributes['context']['db_name'],
                  #"db_root_pw": "super_secret_pw",
                  "db_host": my_task.attributes['hostname']
                },
                "wordpress": {
                  "prefix": "wp_",
                  "wp_logged_in": "59de5a96acf7709097ba7a9ba2ca421b2fff73ee",
                  "path": "/",
                  "wp_nonce": "d52ed52f6664f6006ba22150542728157ce83cdb",
                  "wp_auth": "3ed26d885e9e90d3ec6e43cd15f406092b85c134",
                  "wp_secure_auth": "63d4f698784c128ecd938493075bdb12bd5922b2"
                },
                "apache": {
                  "domain_name": "example.com",
                  "ssl_key": "-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEAyql1QiZCxzSc5aikNRk4dJ8ham2YpBubjM82rgWtQbcArKc4\nlKi9V/zzaBlzp0shKqfs8LQK3IvNqOD2CfXPK2AMx2UbTJoPmSkf/MP2jvwBbi36\nBoqlS2lnHsQEUdH8N1vagfOCowUP2zQFm2Cw5XvrS3YXqYJoIG4030pfGM6h4u3w\nai8MPjkqfT2BSbNNr+kyMzVWV8OUxU2nnSLjmosc+XbGo7lmoPWF9i2+2LJeVdO2\n6dDL7+GBslV7Z4IoCtlrisKTBWzmSUW2GE/SwCvl7ySlMvOV3JsV0400RJkuk0tZ\n7yYBQLt7j9XaX5B/Sc1raV7bGdHAoRUC9flNTQIDAQABAoIBAE3RhgoRgQDXDgwN\nloghGBGH7R/d14fkZfVKt/dYjK+4IpUpXMuQg6weoCRv6X3qlmC3vH6s06LeN+lK\nAI/QiG1iY2XJSBNA8Q5hwTugz7MVx0LUerY6VMBBR+yDXhlA5XUoWx4dMCOC1RTZ\nw/FmzmZAEBiYzvsy7OLPDpRTDXMLbV3ULlC+TsKOHAGeSnJbLFrS7MMI4rs8d366\nlyz9pYy9VG2/NRFk+yLvO5vd2YKiPgWWCFWmxkULvRYC7pRU8Uye6iUh0Zn/LWQd\n0Rt38ZrMfVUoIm8ep8TjfwvZDO4MURy7mqAtqLRNyUJk1Rau23crbq5F6jCF0ukq\nMzLlguECgYEA+mzdUD4dic92V5+sP9LYM79DMVlRFLQ9nDJOK4hKukG9+KXSyk8T\nWEtLlJA/2LoDOBAPqq+3eg6l54YTq1RPgVOQxFAwIQHq1K2aBJEt1tyMA1eK3Kp/\nbsS8/jbr3V3C82q3E/Llsm0JCO/5cTCc59DC6xHZvWZ4YJRT7Fc+LHUCgYEAzyxl\nz81fgoaOglcEpVMcv+48EUANEoG06+WXLu9Juc7G9xuKe/QGvl3cAhx0zB+PwnKw\nSF9CXj3d5hCgnioNC8HZ6fO9IiYBqbrjmenrvdPBAbG4SSVZTChYSg44Kh6puSOB\nfZpDaW3poTl4YFFOSpijkukL/kWs5m7zpM4b4nkCgYBkL6d+0crpdllnBtdXlVev\npCYSmSQJ/23ijnGdkuIqj+CbmGOzUl1v5nevUOJqJ0jgZfSOmcvyheezr30w/wLr\nv23cTCRlICo9udIzX42SNxvAvoYsb/2ZaBYgMgK8xiUXUys5TOS+NEb4D2Gg+gzb\n5TYF61dMIbGpGc5VcDXMfQKBgDId/WsttYMv5d2mC1urJXNQwHsz0XW+pvPCELar\n8Fvgp8UzhmbB+7eloQlptN+EaxSRBhAb60Q9FycGsrRQW+OSO5MbAY/3PcO/kDu1\nmO/NAA3W3kvjmxyPTfxsQC4ASPKeoj6uSMyCaFg2POagBJ6LGlb5xYr3dAIyqQIf\nUiORAoGBAN79cXdQBL6XJIFuy43QzcT37IDihxJ3sGOBPf4nOCealOHxA/iRgYim\nN7YE6SrkAPPZdG3L9U7LOCfchUiIbSvQFXReukewn6714N4QMYY0Dz+1NBwXD/w1\n8j3jDF3oufViQELOIrmjxtZbBazVffOTpgYiepnP8Ns7U5WGijhF\n-----END RSA PRIVATE KEY-----\n",
                  "path": "/",
                  "ssl_cert": "-----BEGIN CERTIFICATE-----\nMIIDxjCCAq6gAwIBAgIJAMPPVAWqOFGIMA0GCSqGSIb3DQEBBQUAMIGWMQswCQYD\nVQQGEwJVUzELMAkGA1UECBMCVHgxFDASBgNVBAcTC1NhbiBBbnRvbmlvMRowGAYD\nVQQKExFBd2Vzb21lbmVzcywgSW5jLjEdMBsGA1UEAxMUbXlhd2Vzb21ld2Vic2l0\nZS5jb20xKTAnBgkqhkiG9w0BCQEWGnN0dWZmQG15YXdlc29tZXdlYnNpdGUuY29t\nMB4XDTEyMDYxNTE0MDE0NloXDTIyMDYxMzE0MDE0NlowgZYxCzAJBgNVBAYTAlVT\nMQswCQYDVQQIEwJUeDEUMBIGA1UEBxMLU2FuIEFudG9uaW8xGjAYBgNVBAoTEUF3\nZXNvbWVuZXNzLCBJbmMuMR0wGwYDVQQDExRteWF3ZXNvbWV3ZWJzaXRlLmNvbTEp\nMCcGCSqGSIb3DQEJARYac3R1ZmZAbXlhd2Vzb21ld2Vic2l0ZS5jb20wggEiMA0G\nCSqGSIb3DQEBAQUAA4IBDwAwggEKAoIBAQDKqXVCJkLHNJzlqKQ1GTh0nyFqbZik\nG5uMzzauBa1BtwCspziUqL1X/PNoGXOnSyEqp+zwtArci82o4PYJ9c8rYAzHZRtM\nmg+ZKR/8w/aO/AFuLfoGiqVLaWcexARR0fw3W9qB84KjBQ/bNAWbYLDle+tLdhep\ngmggbjTfSl8YzqHi7fBqLww+OSp9PYFJs02v6TIzNVZXw5TFTaedIuOaixz5dsaj\nuWag9YX2Lb7Ysl5V07bp0Mvv4YGyVXtngigK2WuKwpMFbOZJRbYYT9LAK+XvJKUy\n85XcmxXTjTREmS6TS1nvJgFAu3uP1dpfkH9JzWtpXtsZ0cChFQL1+U1NAgMBAAGj\nFTATMBEGCWCGSAGG+EIBAQQEAwIGQDANBgkqhkiG9w0BAQUFAAOCAQEAqXZuiTPy\n+YRWkkE9DOWJmmnSsjLBrnh1YY0ZmNDMFM9xP6uRd/StAbwgIYxMS2Wo8ZtMkrNv\nnaCBB6ghgQHaNJmx1j92SpS1U/WELcSKV01j9DnklFXbSH6n5fS/VsckTcmVOXoW\nwLgHXXd0aueqBTPpiKEjNfI7dUl+uUpbklb+RyN565hxjzrSDSuhSjZ/0GL61RVz\n4pY+rjEPNp3itHbR6weyWwNvi0xA8FYipwJYEiErN2zuhH1ikACrlBw9Fo/7hSmh\nZ3rujqhToCEbXsejLKjSKSzdVGEhgRHla+9+cEvnAYfWnIkAl1pVK3BH+5Bg4634\nFQOjVTygmZVlVw==\n-----END CERTIFICATE-----\n"
                },
                "user": {
                  "hash": "1c1c17efcbae072dcfaa85e133ced2d8f0484ce2c9edb5b073cdb82bd19286f4",
                  "password": "secret_password",
                  "ssh_pub_key": "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQC4yHdB478LU+1xdlSHfOzu1oNBixez9iEHM5O4cdsg8O4J88kXvR8Ks9fFNcuLFRPLdiX4m/H97HVt3iFaBUBKq1nORrbrkJxik5Eb/8s1VBDumey8gPDN4GDD7WfJS5BeCgWY9LEbtV7Eqlqn3Q2et8nywDYpBUOYcOhDK9sZHI8hk2gk8M4ZDI3rSf/sZVZU0/oVwUrRIa8Gh5rL5cRB7gXrhjrFqosXj9Xrq/ACIBvuTMlpFV+w1y3OztqIObUhmfc1XRWMOt+m54r4bfeULIBhLzQ5+aT0wWeSA0oY9BLCzBG751zMzDmcvcAdLk3K1Ux2qsKzUZE+vd4XmLd9",
                  "name": "example_user",
                  "ssh_priv_key": "-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEAuMh3QeO/C1PtcXZUh3zs7taDQYsXs/YhBzOTuHHbIPDuCfPJ\nF70fCrPXxTXLixUTy3Yl+Jvx/ex1bd4hWgVASqtZzka265CcYpORG//LNVQQ7pns\nvIDwzeBgw+1nyUuQXgoFmPSxG7VexKpap90NnrfJ8sA2KQVDmHDoQyvbGRyPIZNo\nJPDOGQyN60n/7GVWVNP6FcFK0SGvBoeay+XEQe4F64Y6xaqLF4/V66vwAiAb7kzJ\naRVfsNctzs7aiDm1IZn3NV0VjDrfpueK+G33lCyAYS80Ofmk9MFnkgNKGPQSwswR\nu+dczMw5nL3AHS5NytVMdqrCs1GRPr3eF5i3fQIDAQABAoIBAB7rPDlEOHVWx8ZS\nfHZnSuXz8uaGtaKhLomb8b3NH1N1vP7hUeas+IK78QDIrZRKJJPI4zWkMmvAoy2N\nG5uKgWV9InvHjVgBTImaE4/Rz1jPBj5Gdzxbfu+T+d0O3mzqPe/eUW10lCYExSS3\nNJAeBudl7V63FtjqTpM1YUfMEM80lPE8UXIZEk1YQuoyzxt46jhFPY3pNtACJjEI\nycbX04UPQAf8W1bHIJZir8FOD0NwFkAXewTth9JA6jrstHmUAi55asrskzI1LvBR\nkb7S2VkG2HSw2MRbmvfbxfCb8vbsbOzQjS8G4d9u5H1M8JzLWWkraWDgh+Tiew0a\nPK0p3ykCgYEA8jbub7UMmjUdR+c4/mYZ5JdJFSyPaNoU40eNSx86vGDjO2jZgZGQ\nbNL+E/byDLR44cZNYTKixgUpb6SFoR/hzJ3sQq3/PUcWmu6CvnFj/9Z3nBecHTbq\nCyeN4uATW/DF/aujyTLvQ+brZ6eaOzxSWbDVhIVX6aXOWMv51I60nQ8CgYEAw0zB\nwxuOwEbbbJ4aOFTxbwE1aMhaoD52fzGf/olJWOltp47CH4VgxlDRrDLf4U6yEQS0\n3UEgdJqeppcxAZtRPLs/rK1LHpEM5ZQCs8XSouicKIMQ4oEpS7+wyqySDBCRuM1y\nSWKiokxwEPAEJUOP8BL5+owyGa9glAREiFuuurMCgYATnhdZvNQ0eTDR7gxTrnlS\nZl5o9J744xDmB5mOCA19zGsbGLblI6EK71vcyhd4p/VSc/k4ch105F4iyLR6BFcJ\nd5D3JZiSoftWuRKl0hFDW198qPzf8N6r4JxBT9zBiZK/pPMzDIkMett+HbkEKzKQ\nSR5CCXrBVciMsJifep9uSQKBgQC6Y8AtCFj2MunpwP5/Mrp1Wa7ygPzVIKgQ/niX\nAclpvOZ1Wu70DGRvAOULNkarDmMtkNNYsnZaMtMlZPhVczlV/9NmZsFhu8eWN+tY\nTX2ZEu0uUOBFfEXAUINW+tor/4hD2neviB51TQRLdfZO5isyUboYH8MU9mby/Ru3\nE+EvtwKBgCAVdXWErd+xHLdcU1UqZEPO/s/Dok5vJqgDZLWdzrEv2O4jQ5RBA7r6\nlgXjwuvjgcWtLJKolxPSIcd/ZP2yxIuGAXuRGloKmEz13XOZvzqYZ6t3CRGl++Pj\nojYMBG29dekW0ceDPEIaIA817OdZKXfmOkNmPi3IDpbnav9ubq8a\n-----END RSA PRIVATE KEY-----\n"
                },
                "id": "webapp_wordpress_app1",
                "lsyncd": {
                  "slaves": []
                }
              }
            #FIXME: this is a test. It doesn't account for master
            for key, value in my_task.attributes.iteritems():
                if key.endswith(".private_ip"):
                    bag['lsyncd']['slaves'].append(value)

            my_task.set_attribute(bag=bag)

        build_bag = Transform(wfspec, "Build Data Bag",
                transforms=[get_source_body(build_bag_code)],
                description="Get all data needed for our cookbooks and place "
                        "it in a structure ready for storage in a databag",
                defines=dict(provider=self.key, task_tags=None))

        # Build Bag needs to wait on all required resources
        # we need the keys from the environment
        predecessors = [self.prep_task]
        for relation in resource.get('relations', {}).values():
            if 'target' in relation:
                # We are the source, so we need data from the target
                target = deployment['resources'][relation['target']]
                tasks = self.find_tasks(wfspec,
                        resource=relation['target'],
                        provider=target['provider'],
                        tag='final')
                if not tasks:
                    raise Exception()
                predecessors.extend(tasks)

        wait_for(wfspec, build_bag, predecessors)

        # Call distribute_manage_databag(environment, bagname, itemname, contents)
        write_bag = Celery(wfspec, 'Write Data Bag',
               'stockton.cheflocal.distribute_manage_databag',
                call_args=[deployment['id'], 'deployments',
                        "webapp_wordpress_app1", Attrib('bag')],
                defines=dict(resource=key,
                            provider=self.key,
                            task_tags=None),
                properties={'estimated_duration': 5})
        build_bag.connect(write_bag)

        bootstrap_task = Celery(wfspec, 'Configure Server:%s' % key,
               'stockton.cheflocal.distribute_cook',
                call_args=[Attrib('ip'), deployment['id']],
                roles=['build-ks', 'wordpress-web'],
                password=Attrib('password'),
                identity_file=Attrib('private_key_path'),
                description="Push and apply Chef recipes on the server",
                defines=dict(resource=key,
                            provider=self.key,
                            task_tags=['final']),
                properties={'estimated_duration': 100})
        # Note: This join is assumed to exist by create_workflow
        wait_for(wfspec, bootstrap_task, [register_node_task, write_bag],
                name="Check on Registration and Overrides:%s" % key,
                description="Before applying chef recipes, we need to know "
                "that the server has chef on it and that the overrides "
                "(database settings) have been applied")

        # The connection to overrides will be done later (using the join)
        return dict(root=root, final=bootstrap_task)

    def add_connection_tasks(self, resource, key, relation, relation_key,
            wfspec, deployment):
        target = deployment['resources'][relation['target']]
        interface = relation['interface']

        if interface == 'mysql':
            #Take output from Create DB task and write it into
            # the 'override' dict to be available to future tasks

            db_final = self.find_tasks(wfspec, provider=target['provider'],
                    tag='final')
            if not db_final:
                raise CheckmateException("Database creation task not found")
            if len(db_final) > 1:
                raise CheckmateException("Multiple database creation tasks "
                        "found")
            db_final = db_final[0]

            def compile_override_code(my_task):
                my_task.attributes['overrides'] = {'wordpress': {'db':
                    {'host': my_task.attributes['hostname'],
                    'database': my_task.attributes['context']['db_name'],
                    'user': my_task.attributes['context']['db_username'],
                    'password': my_task.attributes['context']
                    ['db_password']}}}

            compile_override = Transform(wfspec, "Prepare Overrides",
                    transforms=[get_source_body(compile_override_code)],
                    description="Get all the variables "
                            "we need (like database name and password) and "
                            "compile them into JSON that we can set on the "
                            "role or environment",
                    defines=dict(relation=relation_key,
                                provider=self.key,
                                task_tags=None))
            db_final.connect(compile_override)

            set_overrides = Celery(wfspec, 'Write Database Settings',
                    'stockton.cheflocal.distribute_manage_role',
                    call_args=['wordpress-web', deployment['id']],
                    override_attributes=Attrib('overrides'),
                    description="Take the JSON prepared earlier and write "
                            "it into the wordpress role. It will be used "
                            "by the Chef recipe to connect to the DB",
                    defines=dict(relation=relation_key,
                                resource=key,
                                provider=self.key,
                                task_tags=None),
                    properties={'estimated_duration': 10})
            wait_on = [compile_override, self.prep_task]
            wait_for(wfspec, set_overrides, wait_on,
                    name="Wait on Environment and Settings:%s" % key)

            config_final = self.find_tasks(wfspec, resource=key,
                    provider=self.key, tag='final')[0]
            # Assuming input is join
            assert isinstance(config_final.inputs[0], Merge)
            set_overrides.connect(config_final.inputs[0])
        elif relation.get('relation') == 'host':
            pass
        else:
            LOG.warning("Provider '%s' does not recognized connection "
                    "interface '%s'" % (self.key, interface))

    def get_catalog(self, context, type_filter=None):
        #TODO: remove hard-coding
        results = {}
        if type_filter is None or type_filter == 'application':
            results = {'application': {
                    'apache2': {
                        'name': 'apache',
                        },
                    'mysql': {
                        'name': 'mysql',
                        },
                    'php5': {
                        'name': 'php5',
                        },
                    'lsyncd': {
                        'name': 'lsyncd',
                        },
                    }}

        return results


class ServerProvider(ProviderBase):
    name = 'chef-server'
    vendor = 'opscode'

    """Implements a Chef Server configuration management provider"""
    def __init__(self, provider, key=None):
        super(ServerProvider, self).__init__(provider, key=key)
        self.prep_task = None

    def prep_environment(self, wfspec, deployment):
        create_environment = Celery(wfspec, 'Create Chef Environment',
                'stockton.chefserver.distribute_manage_env',
                call_args=[Attrib('context'), deployment['id'],
                        'CheckMate Environment'],
                properties={'estimated_duration': 10})
        self.prep_task = create_environment
        return {'root': self.prep_task, 'final': self.prep_task}

    def add_resource_tasks(self, resource, key, wfspec, deployment, context,
                wait_on=None):
        register_node_task = Celery(wfspec, 'Register Server:%s' % key,
                        'stockton.chefserver.distribute_register_node',
                        call_args=[Attrib('context'),
                               resource.get('dns-name'), ['wordpress-web']],
                        environment=deployment['id'],
                        defines=dict(resource=key, provider=self.key),
                        description="Register the "
                                "node in the Chef Server. Nothing is done "
                                "the node itself",
                        properties={'estimated_duration': 20})
        self.prep_task.connect(register_node_task)

        ssh_apt_get_task = Celery(wfspec, 'Apt-get Fix:%s' % key,
                           'stockton.ssh.ssh_execute',
                            call_args=[Attrib('ip'),
                                    "sudo apt-get update",
                                    'root'],
                            password=Attrib('password'),
                            identity_file=Attrib('private_key_path'),
                            properties={'estimated_duration': 100})
        # TODO: stop assuming only one wait_on=create_server_task
        wait_on[0].connect(ssh_apt_get_task)

        bootstrap_task = Celery(wfspec, 'Bootstrap Server:%s' % key,
                           'stockton.chefserver.distribute_bootstrap',
                            call_args=[Attrib('context'),
                                    resource.get('dns-name'), Attrib('ip')],
                            password=Attrib('password'),
                            identity_file=Attrib('private_key_path'),
                            run_roles=['build', 'wordpress-web'],
                            environment=deployment['id'],
                            properties={'estimated_duration': 90})
        wait_for(wfspec, bootstrap_task,
                [ssh_apt_get_task, register_node_task],
                name="Wait for Server Build:%s" % key)
        return {'root': register_node_task, 'final': bootstrap_task}

    def add_connection_tasks(self, resource, key, relation, relation_key,
            wfspec, deployment):
        target = deployment['resources'][relation['target']]
        interface = relation['interface']

        if interface == 'mysql':
            #Take output from Create DB task and write it into
            # the 'override' dict to be available to future tasks

            db_final = self.find_resource_task(wfspec, relation['target'],
                    target['provider'], 'final')

            compile_override = Transform(wfspec, "Prepare Overrides",
                    transforms=[
                    "my_task.attributes['overrides']={'wordpress': {'db': "
                    "{'host': my_task.attributes['hostname'], "
                    "'database': my_task.attributes['context']['db_name'], "
                    "'user': my_task.attributes['context']['db_username'], "
                    "'password': my_task.attributes['context']"
                    "['db_password']}}}"],
                    description="Get all the variables "
                            "we need (like database name and password) and "
                            "compile them into JSON that we can set on the "
                            "role or environment",
                    defines=dict(relation=relation_key,
                                provider=self.key,
                                task_tags=None))
            db_final.connect(compile_override)

            set_overrides = Celery(wfspec,
                "Write Database Settings",
                'stockton.chefserver.distribute_manage_env',
                call_args=[Attrib('context'), deployment['id']],
                    desc='CheckMate Environment',
                    override_attributes=Attrib('overrides'),
                description="Take the JSON prepared earlier and write "
                        "it into the environment overrides. It will "
                        "be used by the Chef recipe to connect to "
                        "the database",
                defines=dict(relation=relation_key,
                            resource=key,
                            provider=self.key,
                            task_tags=None),
                properties={'estimated_duration': 15})

            wait_on = [compile_override, self.prep_task]
            wait_for(wfspec, set_overrides, wait_on,
                    name="Wait on Environment and Settings:%s" % key)

            config_final = self.find_resource_task(wfspec, key, self.key,
                    'final')
            # Assuming input is join
            assert isinstance(config_final.inputs[0], Merge)
            set_overrides.connect(config_final.inputs[0])

        else:
            LOG.warning("Provider '%s' does not recognized connection "
                    "interface '%s'" % (self.key, interface),
                    defines=dict(relation=relation_key,
                                provider=self.key,
                                task_tags=None))


register_providers([ServerProvider, LocalProvider])
