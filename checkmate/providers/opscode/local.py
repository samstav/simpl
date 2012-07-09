"""Chef Local/Solo configuration management provider

How do settings flow through:
- values that are only available at run time (ex. ip of a server) can be picked
  up directly using the Attrib() object (Attrib('ip') gets resolved into the
  'ip' key's value before the call)
- settings available at compile time get set in the context object. The context
  object is made available during the run and any task can pick up a value from
  it using the Attrib() object (Attrib('ip') gets resolved into the 'ip' key's
  before the call)
- setting that are generated?

"""
import logging
import os
import uuid

from Crypto.PublicKey import RSA  # pip install pycrypto
from Crypto.Random import atfork
from SpiffWorkflow.operators import Attrib
from SpiffWorkflow.specs import Celery, Transform

from checkmate.common import crypto
from checkmate.components import Component
from checkmate.exceptions import CheckmateException, \
        CheckmateCalledProcessError, CheckmateNoMapping
from checkmate.providers import ProviderBase
from checkmate.utils import get_source_body, merge_dictionary
from checkmate.workflows import wait_for

LOG = logging.getLogger(__name__)


class Provider(ProviderBase):
    """Implements a Chef Local/Solo configuration management provider"""
    name = 'chef-local'
    vendor = 'opscode'

    def __init__(self, provider, key=None):
        ProviderBase.__init__(self, provider, key=key)
        self.prep_task = None

    def prep_environment(self, wfspec, deployment, context):
        if self.prep_task:
            return  # already prepped
        create_environment = Celery(wfspec, 'Create Chef Environment',
                'checkmate.providers.opscode.local.create_environment',
                call_args=[deployment['id']],
                public_key_ssh=Attrib('public_key_ssh'),
                private_key=Attrib('private_key'),
                secret_key=Attrib('secret_key'),
                defines=dict(provider=self.key,
                            task_tags=['root']),
                properties={'estimated_duration': 10})
        self.prep_task = create_environment

        return dict(root=create_environment, final=create_environment)

    def add_resource_tasks(self, resource, key, wfspec, deployment, context,
                wait_on=None):
        if wait_on is None:
            wait_on = []
        self.add_wait_on_host_tasks(resource, wfspec, deployment, wait_on)

        # Add tasks
        register_node_task = Celery(wfspec, 'Register Server:%s' % key,
                'checkmate.providers.opscode.local.register_node',
                call_args=[Attrib('ip'), deployment['id']],
                password=Attrib('password'),
                omnibus_version="0.10.10-1",
                identity_file=Attrib('private_key_path'),
                attributes={'deployment': {'id': deployment['id']}},
                defines=dict(resource=key,
                            provider=self.key,
                            task_tags=['root']),
                description="Install Chef client on the target machine and "
                       "register it in the environment",
                properties={'estimated_duration': 120})

        bootstrap_task = Celery(wfspec, 'Pre-Configure Server:%s' % key,
               'checkmate.providers.opscode.local.cook',
                call_args=[Attrib('ip'), deployment['id']],
                recipes=['build-essential'],
                password=Attrib('password'),
                identity_file=Attrib('private_key_path'),
                description="Run build-essential on server",
                defines=dict(resource=key,
                            provider=self.key,
                            task_tags=None),
                properties={'estimated_duration': 100})
        register_node_task.connect(bootstrap_task)

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

        # Call manage_databag(environment, bagname, itemname, contents)
        write_bag = Celery(wfspec, 'Write Data Bag',
               'checkmate.providers.opscode.local.manage_databag',
                call_args=[deployment['id'], deployment['id'],
                        "webapp_wordpress_A", Attrib('bag')],
                secret_file='certificates/chef.pem',
                defines=dict(resource=key,
                            provider=self.key,
                            task_tags=None),
                properties={'estimated_duration': 5})
        build_bag.connect(write_bag)

        configure_task = Celery(wfspec, 'Configure Application:%s' % key,
               'checkmate.providers.opscode.local.cook',
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
        wait_for(wfspec, configure_task, [bootstrap_task, write_bag],
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
                    'checkmate.providers.opscode.local.manage_role',
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
        """Return stored/override catalog if it exists, else connect, build,
        and return one"""

        # TODO: maybe implement this an on_get_catalog so we don't have to do
        #        this for every provider
        results = ProviderBase.get_catalog(self, context,
            type_filter=type_filter)
        if results:
            # We have a prexisting or overridecatalog stored
            return results

        # build a live catalog ()this would be the on_get_catalog called if no
        # stored/override existed
        if type_filter is None or type_filter == 'application':
            # Get cookbooks
            cookbooks = self._get_cookbooks(site_cookbooks=False)
            site_cookbooks = self._get_cookbooks(site_cookbooks=True)
            roles = self._get_roles(context)

            cookbooks.update(roles)
            cookbooks.update(site_cookbooks)

            results = {'application': cookbooks}

        return results

    def get_component(self, context, id):
        # Get cookbook
        assert id, 'Blank component ID requested from get_component'
        if '::' in id:
            id = id.split('::')[0]

        cookbook = self._get_cookbook(id, site_cookbook=True)
        if cookbook:
            Component.validate(cookbook)
            return cookbook

        cookbook = self._get_cookbook(id, site_cookbook=False)
        if cookbook:
            Component.validate(cookbook)
            return cookbook

        role = self._get_role(id, context)
        if role:
            Component.validate(role)
            return role

        LOG.debug("Component '%s' not found" % id)

    def _get_cookbooks(self, site_cookbooks=False):
        """Get all cookbooks as CheckMate components"""
        results = {}
        repo_path = _get_repo_path()
        if site_cookbooks:
            path = os.path.join(repo_path, 'site-cookbooks')
        else:
            path = os.path.join(repo_path, 'cookbooks')

        names = []
        for top, dirs, files in os.walk(path):
            names = [name for name in dirs if name[0] != '.']
            break

        for name in names:
            data = self._get_cookbook(name, site_cookbook=site_cookbooks)
            if data:
                results[data['id']] = data
        return results

    def _get_cookbook(self, id, site_cookbook=False):
        """Get a cookbook as a CheckMate component"""
        assert id, 'Blank cookbook ID requested from _get_cookbook'
        cookbook = {}
        repo_path = _get_repo_path()
        if site_cookbook:
            meta_path = os.path.join(repo_path, 'site-cookbooks', id,
                    'metadata.json')
        else:
            meta_path = os.path.join(repo_path, 'cookbooks', id,
                    'metadata.json')
        if os.path.exists(meta_path):
            cookbook = self._parse_cookbook_metadata(meta_path)
        return cookbook

    def _parse_cookbook_metadata(self, metadata_json_path):
        """Get a cookbook's data and format it as a checkmate component

        :param metadata_json_path: path to metadata.json file
        """
        component = {'is': 'application'}
        with file(metadata_json_path, 'r') as f:
            data = json.load(f)
        component['id'] = data['name']
        component['summary'] = data.get('description')
        component['version'] = data.get('version')
        if 'attributes' in data:
            component['options'] = data['attributes']
        if 'dependencies' in data:
            dependencies = []
            for key, value in data['dependencies'].iteritems():
                dependencies.append(dict(id=key, version=value))
            component['dependencies'] = dependencies
        if 'platforms' in data:
            #TODO: support multiple options
            if 'ubuntu' in data['platforms'] or 'centos' in data['platforms']:
                requires = [dict(host='linux')]
                component['requires'] = requires

        # Tweaks we apply for each cookbook
        mapping = {
                'apache2': {
                        'provides': [{'application': 'http'}],
                    },
                'wordpress': {
                        'provides': [{'application': 'http'}],
                    },
            }
        if component['id'] in mapping:
            component.update(mapping[component['id']])
        # Add hosting relationship
        if 'requires' in component:
            found = False
            for entry in component['requires']:
                key, value = entry.items()[0]
                if key == 'host':
                    found = True
                    break
                if isinstance(value, dict):
                    if value.get('relation') == 'host':
                        found = True
                        break
            if not found:
                component['requires'].append(dict(host='linux'))
        else:
            component['requires'] = [dict(host='linux')]

        return component

    def _get_roles(self, context):
        """Get all roles as CheckMate components"""
        results = {}
        repo_path = _get_repo_path()
        path = os.path.join(repo_path, 'roles')

        names = []
        for top, dirs, files in os.walk(path):
            names = [name for name in files if name.endswith('.json')]
            break

        for name in names:
            data = self._get_role(name[:-5], context)
            if data:
                results[data['id']] = data
        return results

    def _get_role(self, id, context):
        """Get a role as a CheckMate component"""
        assert id, 'Blank role ID requested from _get_role'
        role = {}
        repo_path = _get_repo_path()
        if id.endswith("-role"):
            id = id[:-5]
        role_path = os.path.join(repo_path, 'roles', "%s.json" % id)
        if os.path.exists(role_path):
            role = self._parse_role_metadata(role_path, context)
        return role

    def _parse_role_metadata(self, role_json_path, context):
        """Get a roles's data and format it as a checkmate component

        :param role_json_path: path to role json file

        Note: role names get '-role' appended to their ID to identify them as
              roles.
        """
        component = {'is': 'application'}
        provides = []
        requires = []
        options = {}
        with file(role_json_path, 'r') as f:
            data = json.load(f)
        component['id'] = "%s-role" % data['name']
        if data.get('description'):
            component['summary'] = data['description']
        if 'run_list' in data:
            dependencies = []
            for value in data['run_list']:
                if value.startswith('recipe'):
                    name = value[value.index('[') + 1:-1]
                    dependencies.append(name)
                elif value.startswith('role'):
                    name = value[value.index('[') + 1:-1]
                    dependencies.append("%s-role" % name)
                else:
                    continue

                dependency = self.get_component(context, name)
                if dependency:
                    if 'provides' in dependency:
                        provides.extend(dependency['provides'])
                    if 'requires' in dependency:
                        requires.extend(dependency['requires'])
                    if 'options' in dependency:
                        options.update(dependency['options'])
            if dependencies:
                component['dependencies'] = dependencies
            if provides:
                component['provides'] = provides
            if requires:
                component['requires'] = requires
            if options:
                component['options'] = options

        return component

    def find_components(self, context, **kwargs):
        name = kwargs.pop('name', None)
        role = kwargs.pop('role', None)
        if role:
            id = "%s-%s-role" % (name, role)
        else:
            id = name
        if id:
            return [self.get_component(context, id)]

        return ProviderBase.find_components(self, context, **kwargs)

    def status(self):
        # Files to be changed:
        #   git diff --stat --color remotes/origin/master..master
        # Full diff: remove --stat
        pass

#
# Celery Tasks (moved from python-stockton)
#
from collections import deque
import git
import json
import shutil
from subprocess import check_output, CalledProcessError, Popen, PIPE
import sys
import threading

from celery.task import task

from checkmate.ssh import execute as ssh_execute


@task
def create_environment(name, path=None, private_key=None,
        public_key_ssh=None, secrets_key=None):
    """Create a knife-solo environment

    The environment is a directory structure that is self-contained and
    seperate from other environments. It is used by this provider to run knife
    solo commands.

    :param name: the name of the environment. This will be the directory name.
    :param path: an override to the root path where to create this environment
    :param private_key: PEM-formatted private key
    :param public_key_ssh: SSH-formatted public key
    :param secrets_key: PEM-formatted private key for use by knife/chef for
        data bag encryption
    """
    # Get path
    root = _get_root_environments_path(path)
    fullpath = os.path.join(root, name)
    if os.path.exists(fullpath):
        raise CheckmateException("Environment already exists: %s" % fullpath)

    # Create environment
    os.mkdir(fullpath, 0770)
    LOG.debug("Created environment directory: %s" % fullpath)
    results = {"environment": fullpath}

    key_data = _create_environment_keys(fullpath, private_key=private_key,
            public_key_ssh=public_key_ssh)

    # Kitchen is created in a /kitchen subfolder since it gets completely
    # rsynced to hosts. We don't want the whole environment rsynced
    kitchen_data = _create_kitchen('kitchen', fullpath,
            secrets_key=secrets_key)
    kitchen_path = os.path.join(fullpath, 'kitchen')

    # Copy environment public key to kitchen certs folder
    public_key_path = os.path.join(fullpath, 'checkmate.pub')
    kitchen_key_path = os.path.join(kitchen_path, 'certificates',
            'checkmate-environment.pub')
    shutil.copy(public_key_path, kitchen_key_path)
    LOG.debug("Wrote environment public key to kitchen: %s" % kitchen_key_path)

    _init_cookbook_repo(os.path.join(kitchen_path, 'cookbooks'))
    # Temporary Hack: load all cookbooks and roles from chef-stockton
    # TODO: Undo this and use more git
    download_cookbooks(name, path=root)
    download_cookbooks(name, path=root, use_site=True)
    download_roles(name, path=root)

    results.update(kitchen_data)
    results.update(key_data)
    LOG.debug("distribute_create_environment returning: %s" % results)
    return results


def _get_root_environments_path(path=None):
    """Build the path using provided inputs and using any environment variables
    or configuration settings"""
    root = path or os.environ.get("CHECKMATE_CHEF_LOCAL_PATH",
            os.path.dirname(__file__))
    if not os.path.exists(root):
        raise CheckmateException("Invalid root path: %s" % root)
    return root


def _create_kitchen(name, path, secrets_key=None):
    """Creates a new knife-solo kitchen in path

    :param name: the name of the kitchen
    :param path: where to create the kitchen
    :param secrets_key: PEM-formatted private key for data bag encryption
    """
    if not os.path.exists(path):
        raise CheckmateException("Invalid path: %s" % path)

    kitchen_path = os.path.join(path, name)
    if not os.path.exists(kitchen_path):
        os.mkdir(kitchen_path, 0770)
        LOG.debug("Created kitchen directory: %s" % kitchen_path)

    params = ['knife', 'kitchen', '.']
    _run_kitchen_command(kitchen_path, params)

    secrets_key_path = os.path.join(kitchen_path, 'certificates', 'chef.pem')
    config = """# knife -c knife.rb
file_cache_path  "%s"
cookbook_path    ["%s", "%s"]
role_path  "%s"
data_bag_path  "%s"
log_level        :info
log_location     STDOUT
ssl_verify_mode  :verify_none
encrypted_data_bag_secret "%s"
""" % (kitchen_path,
            os.path.join(kitchen_path, 'cookbooks'),
            os.path.join(kitchen_path, 'site-cookbooks'),
            os.path.join(kitchen_path, 'roles'),
            os.path.join(kitchen_path, 'data_bags'),
            secrets_key_path)
    solo_file = os.path.join(kitchen_path, 'solo.rb')
    with file(solo_file, 'w') as f:
        f.write(config)
    LOG.debug("Created solo file: %s" % solo_file)

    # Create certificates folder
    certs_path = os.path.join(kitchen_path, 'certificates')
    os.mkdir(certs_path, 0770)
    LOG.debug("Created certs directory: %s" % certs_path)

    # Store (generate if necessary) the secrets file
    if not secrets_key:
        # celery runs os.fork(). We need to reset the random number generator
        # before generating a key. See atfork.__doc__
        atfork()
        key = RSA.generate(2048)
        secrets_key = key.exportKey('PEM')
        LOG.debug("Generated secrets private key")
    with file(secrets_key_path, 'w') as f:
        f.write(secrets_key)
    LOG.debug("Stored secrets file: %s" % secrets_key_path)

    # Knife defaults to knife.rb, but knife-solo looks for solo.rb, so we link
    # both files so that knife and knife-solo commands will work and anyone
    # editing one will also change the other
    knife_file = os.path.join(path, name, 'knife.rb')
    os.link(solo_file, knife_file)
    LOG.debug("Linked knife.rb: %s" % knife_file)

    LOG.debug("Finished creating kitchen: %s" % kitchen_path)
    return {"kitchen": kitchen_path}


def _create_environment_keys(environment_path, private_key=None,
        public_key_ssh=None):
    """Put keys in an existing environment

    If none are provided, a new set of public/private keys are created
    """
    # Create private key
    private_key_path = os.path.join(environment_path, 'private.pem')
    if private_key:
        with file(private_key_path, 'w') as f:
            f.write(private_key)
        LOG.debug("Wrote environment private key: %s" % private_key_path)
    else:
        params = ['openssl', 'genrsa', '-out', private_key_path, '2048']
        result = check_output(params)
        LOG.debug(result)

    # Secure private key
    os.chmod(private_key_path, 0600)
    LOG.debug("Private cert permissions set: chmod 0600 %s" %
            private_key_path)

    # Generate public key
    if not public_key_ssh:
        params = ['ssh-keygen', '-y', '-f', private_key_path]
        public_key_ssh = check_output(params)

    # Write it to environment
    public_key_path = os.path.join(environment_path, 'checkmate.pub')
    with file(public_key_path, 'w') as f:
        f.write(public_key_ssh)
    LOG.debug("Wrote environment public key: %s" % public_key_path)
    return dict(public_key_ssh=public_key_ssh, public_key_path=public_key_path,
            private_key_path=private_key_path)


def _init_cookbook_repo(cookbooks_path):
    """Make cookbook folder a git repo"""
    if not os.path.exists(cookbooks_path):
        raise CheckmateException("Invalid cookbook path: %s" % cookbooks_path)

    # Init git repo
    repo = git.Repo.init(cookbooks_path)

    file_path = os.path.join(cookbooks_path, '.gitignore')
    with file(file_path, 'w') as f:
        f.write("#Checkmate Created Repo")
    index = repo.index
    index.add(['.gitignore'])
    index.commit("Initial commit")
    LOG.debug("Initialized cookbook repo: %s" % cookbooks_path)


@task
def download_cookbooks(environment, path=None, cookbooks=None,
        source=None, use_site=False):
    """Download cookbooks from a remote repo
    :param environment: the name of the kitchen/environment environment.
        It should have cookbooks and site-cookbooks subfolders
    :param path: points to the root of environments.
        It should have cookbooks and site-cookbooks subfolders
    :param cookbooks: the names of the cookbooks to download (blank=all)
    :param source: the source repos (a github URL)
    :param use_site: use site-cookbooks instead of cookbooks
    :returns: count of cookbooks copied"""
    # Until we figure out a better solution, I'm assuming the chef-stockton
    # repo is cloned as a subfolder under the provider (and cloning it if
    # not) and we copy the cookbooks from there

    # Get path
    root = _get_root_environments_path(path)
    fullpath = os.path.join(root, environment)
    if not os.path.exists(fullpath):
        raise CheckmateException("Environment does not exist: %s" % fullpath)
    kitchen_path = os.path.join(fullpath, 'kitchen')
    if not os.path.exists(kitchen_path):
        raise CheckmateException("Kitchen does not exist: %s" % kitchen_path)

    # Find/get cookbook source
    repo_path = _get_repo_path()

    if not os.path.exists(repo_path):
        git.Repo.clone_from('git://github.rackspace.com/checkmate/'
                'chef-stockton.git', repo_path)
        LOG.info("Cloned chef-stockton to %s" % repo_path)
    else:
        LOG.debug("Getting cookbooks from %s" % repo_path)

    if use_site:
        cookbook_subdir = 'site-cookbooks'
    else:
        cookbook_subdir = 'cookbooks'

    # Check that cookbooks requested exist
    if cookbooks:
        for cookbook in cookbooks:
            if not os.path.exists(os.path.join(repo_path, cookbook_subdir,
                    cookbook)):
                raise CheckmateException("Cookbook '%s' not available in repo:"
                        " %s" % (cookbook, repo_path))
    else:
        # If none specificed, assume all
        cookbooks = [p for p in os.listdir(os.path.join(repo_path,
                cookbook_subdir)) if os.path.isdir(os.path.join(repo_path,
                cookbook_subdir, p))]

    # Copy the cookbooks over
    count = 0
    for cookbook in cookbooks:
        target = os.path.join(kitchen_path, cookbook_subdir, cookbook)
        if not os.path.exists(target):
            LOG.debug("Copying cookbook '%s' to %s" % (cookbook, repo_path))
            shutil.copytree(os.path.join(repo_path, cookbook_subdir, cookbook),
                    target)
            count += 1
    return count


@task
def download_roles(environment, path=None, roles=None, source=None):
    """Download roles from a remote repo
    :param environment: the name of the kitchen/environment environment.
        It should have a roles subfolder.
    :param path: points to the root of environments.
        It should have a roles subfolders
    :param roles: the names of the roles to download (blank=all)
    :param source: the source repos (a github URL)
    :returns: count of roles copied"""
    # Until we figure out a better solution, I'm assuming the chef-stockton
    # repo is cloned as a subfolder under python-stockton (and cloning it if
    # not) and we copy the roles from there

    # Get path
    root = _get_root_environments_path(path)
    fullpath = os.path.join(root, environment)
    if not os.path.exists(fullpath):
        raise CheckmateException("Environment does not exist: %s" % fullpath)
    kitchen_path = os.path.join(fullpath, 'kitchen')
    if not os.path.exists(kitchen_path):
        raise CheckmateException("Kitchen does not exist: %s" % kitchen_path)

    # Find/get cookbook source
    repo_path = _get_repo_path()

    if not os.path.exists(repo_path):
        git.Repo.clone_from('git://github.rackspace.com/ManagedCloud/'
                'chef-stockton.git', repo_path)
        LOG.info("Cloned chef-stockton to %s" % repo_path)
    else:
        LOG.debug("Getting roles from %s" % repo_path)

    # Check that roles requested exist
    if roles:
        for role in roles:
            if not os.path.exists(os.path.join(repo_path, 'roles',
                    role)):
                raise CheckmateException("Role '%s' not available in repo: "
                        "%s" % (role, repo_path))
    else:
        # If none specificed, assume all
        roles = [p for p in os.listdir(os.path.join(repo_path, 'roles'))]

    # Copy the roles over
    count = 0
    for role in roles:
        target = os.path.join(kitchen_path, 'roles', role)
        if not os.path.exists(target):
            LOG.debug("Copying role '%s' to %s" % (role, repo_path))
            shutil.copy(os.path.join(repo_path, 'roles', role), target)
            count += 1
    return count


@task
def register_node(host, environment, path=None, password=None,
        omnibus_version=None, attributes=None, identity_file=None):
    """Register a node in Chef.

    Using 'knife prepare' we will:
    - update apt caches on Ubuntu by default (which bootstrap does not do)
    - install chef on the client
    - register the node by creating as .json file for it in /nodes/

    Note: Maintaining same 'register_node' name as chefserver.py

    :param host: the public IP of the host (that's how knife solo tracks the
        nodes)
    :param environment: the ID of the environment
    :param path: an optional override for path to the environment root
    :param password: the node's password
    :param omnibus_version: override for knife bootstrap (default=latest)
    :param attributes: attributes to set on node (dict)
    :param identity_file: private key file to use to connect to the node
    """
    # Get path
    root = _get_root_environments_path(path)
    kitchen_path = os.path.join(root, environment, 'kitchen')
    if not os.path.exists(kitchen_path):
        raise CheckmateException("Environment kitchen does not exist: %s" %
                kitchen_path)

    # Rsync problem with creating path (missing -p so adding it ourselves) and
    # doing this before the complex prepare work
    ssh_execute(host, "mkdir -p %s" % kitchen_path, 'root', password=password)

    # Calculate node path and check for prexistance
    node_path = os.path.join(kitchen_path, 'nodes', '%s.json' % host)
    if os.path.exists(node_path):
        raise CheckmateException("Node seems to already be registered: %s" %
                node_path)

    # Build and execute command 'knife prepare' command
    params = ['knife', 'prepare', 'root@%s' % host]
    if password:
        params.extend(['-P', password])
    if omnibus_version:
        params.extend(['--omnibus-version', omnibus_version])
    if identity_file:
        params.extend(['-i', identity_file])
    _run_kitchen_command(kitchen_path, params)
    LOG.info("Knife prepare succeeded for %s" % host)

    if attributes:
        with file(node_path, 'rw') as f:
            node = json.load(f)
            node.update(attributes)
            json.dump(node, f)
        LOG.info("Node attributes written in %s" % node_path)


def _run_kitchen_command(kitchen_path, params, lock=True):
    """Runs the 'knife xxx' command.

    This also needs to handle knife command errors, which are returned to
    stderr.

    That needs to be run in a kitchen, so we move curdir and need to make sure
    we stay there, so I added some synchronization code while that takes place
    However, if code calls in that already has a lock, the optional lock param
    can be set to false so thise code does not lock
    """
    LOG.debug("Running: %s" % ' '.join(params))
    if lock:
        path_lock = threading.Lock()
        path_lock.acquire()
        try:
            os.chdir(kitchen_path)
            result = check_all_output(params)  # check_output(params)
        except CalledProcessError, exc:
            # Reraise pickleable exception
            raise CheckmateCalledProcessError(exc.returncode, exc.cmd,
                    output=exc.output)
        finally:
            path_lock.release()
    else:
        os.chdir(kitchen_path)
        result = check_all_output(params)  # check_output(params)
    LOG.debug(result)
    # Knife succeeds even if there is an error. This code tries to parse the
    # output to return a useful error
    fatal = []
    last_fatal = ''
    last_error = ''
    for line in result.split('\n'):
        if 'ERROR:' in line:
            LOG.error(line)
            last_error = line
        if 'FATAL:' in line:
            fatal.append(line)
            last_fatal = line
    if fatal:
        command = ' '.join(params)
        if 'Chef::Exceptions::' in last_fatal:
            # Get the string after Chef::Exceptions::
            error = last_fatal.split('::')[-1]
            if error:
                raise CheckmateCalledProcessError(1, command,
                        output="Chef/Knife error encountered: %s" % error)
        output = '\n'.join(fatal)
        raise CheckmateCalledProcessError(1, command, output=output)
    elif last_error:
        if 'KnifeSolo::::' in last_fatal:
            # Get the string after a Knife-Solo error::
            error = last_error.split('Error:')[-1]
            if error:
                raise CheckmateCalledProcessError(1, ' '.join(params),
                        output="Knife error encountered: %s" % error)
            # Don't raise on all errors. They don't all mean failure!
    return result


@task
def cook(host, environment, recipes=None, roles=None, path=None,
            username='root', password=None, identity_file=None, port=22):
    """Apply recipes/roles to a server"""
    root = _get_root_environments_path(path)
    kitchen_path = os.path.join(root, environment, 'kitchen')
    if not os.path.exists(kitchen_path):
        raise CheckmateException("Environment kitchen does not exist: %s" %
                kitchen_path)
    node_path = os.path.join(kitchen_path, 'nodes', '%s.json' % host)
    if not os.path.exists(node_path):
        raise CheckmateException("Node '%s' is not registered in %s" % (host,
                kitchen_path))

    # Add any missing recipes to node settings
    run_list = []
    if roles:
        run_list.extend(["role[%s]" % role for role in roles])
    if recipes:
        run_list.extend(["recipe[%s]" % recipe for recipe in recipes])
    if run_list:
        add_list = []
        # Open file, read/parse/calculate changes, then write
        lock = threading.Lock()
        lock.acquire()
        try:
            with file(node_path, 'r') as f:
                node = json.load(f)
            for entry in run_list:
                if entry not in node['run_list']:
                    node['run_list'].append(entry)
                    add_list.append(entry)
            if add_list:
                with file(node_path, 'w') as f:
                    json.dump(node, f)
        finally:
            lock.release()
        if add_list:
            LOG.debug("Added to %s: %s" % (node_path, add_list))
        else:
            LOG.debug("All run_list already exists in %s: %s" % (node_path,
                    run_list))
    else:
        LOG.debug("No recipes or roles to add. Will just run 'knife cook' for "
                "%s" % node_path)

    # Build and run command
    if not username:
        username = 'root'
    params = ['knife', 'cook', '%s@%s' % (username, host)]
    if identity_file:
        params.extend(['-i', identity_file])
    if password:
        params.extend(['-P', password])
    if port:
        params.extend(['-p', str(port)])
    _run_kitchen_command(kitchen_path, params)


@task
def manage_role(name, environment, path=None, desc=None,
        run_list=None, default_attributes=None, override_attributes=None,
        env_run_lists=None):
    """Write/Update role"""
    root = _get_root_environments_path(path)
    kitchen_path = os.path.join(root, environment, 'kitchen')
    if not os.path.exists(kitchen_path):
        raise CheckmateException("Environment does not exist: %s" %
                kitchen_path)
    the_ruby = os.path.join(kitchen_path, 'roles', '%s.rb' % name)
    if os.path.exists(the_ruby):
        raise CheckmateException("Encountered a chef role in Ruby. Only JSON "
                "roles can be manipulated by CheckMate: %s" % the_ruby)

    role_path = os.path.join(kitchen_path, 'roles', '%s.json' % name)

    if os.path.exists(role_path):
        with file(role_path, 'r') as f:
            role = json.load(f)
        if run_list is not None:
            role['run_list'] = run_list
        if default_attributes is not None:
            role['default_attributes'] = default_attributes
        if override_attributes is not None:
            role['override_attributes'] = override_attributes
        if env_run_lists is not None:
            role['env_run_lists'] = env_run_lists
    else:
        role = {
            "name": name,
            "chef_type": "role",
            "json_class": "Chef::Role",
            "default_attributes": default_attributes or {},
            "description": desc,
            "run_list": run_list or [],
            "override_attributes": override_attributes or {},
            "env_run_lists": env_run_lists or {}
            }

    LOG.debug("Writing role '%s' to %s" % (name, role_path))
    with file(role_path, 'w') as f:
        json.dump(role, f)


@task
def manage_databag(environment, bagname, itemname, contents,
        path=None, secret_file=None, merge=True):
    """Updates a data_bag or encrypted_data_bag

    :param environment: the ID of the environment
    :param bagname: the name of the databag (in solo, this end up being a
            directory)
    :param item: the name of the item (in solo this ends up being a .json file)
    :param contents: this is a dict of attributes to write in to the databag
    :param path: optional override to the default path where environments live
    :param secret_file: the path to a certificate used to encrypt a data_bag
    :param merge: if True, the data will be merged in. If not, it will be
            completely overwritten
    """
    root = _get_root_environments_path(path)
    kitchen_path = os.path.join(root, environment, 'kitchen')
    databags_root = os.path.join(kitchen_path, 'data_bags')
    if not os.path.exists(databags_root):
        raise CheckmateException("Data bags path does not exist: %s" %
                databags_root)

    databag_path = os.path.join(databags_root, bagname)
    if not os.path.exists(databag_path):
        merge = False  # Nothing to merge if it is new!
        _run_kitchen_command(kitchen_path, ['knife', 'solo', 'data', 'bag',
                'create', bagname])
        LOG.debug("Created data bag: %s" % databag_path)

    if merge:
        params = ['knife', 'solo', 'data', 'bag', 'show', bagname, itemname,
            '-F', 'json']
        if secret_file:
            params.extend('--secret_file', secret_file)

        lock = threading.Lock()
        lock.acquire()
        try:
            data = _run_kitchen_command(kitchen_path, params)
            existing = json.loads(data)
            contents = merge_dictionary(existing, contents)
            if isinstance(contents, dict):
                contents = json.dumps(contents)
            params = ['knife', 'solo', 'data',
                    'bag', 'create', bagname, itemname, '-d', '--json',
                    contents]
            if secret_file:
                params.extend(['--secret-file', secret_file])
            result = _run_kitchen_command(kitchen_path, params)
        except CalledProcessError, exc:
            # Reraise pickleable exception
            raise CheckmateCalledProcessError(exc.returncode, exc.cmd,
                    output=exc.output)
        finally:
            lock.release()
    else:
        if 'id' not in contents:
            contents['id'] = itemname
        elif contents['id'] != itemname:
            raise CheckmateException("The value of the 'id' field in a databag"
                    " item is reserved by Chef and must be set to the name of "
                    "the databag item. Checkmate will set this for you if it "
                    "is missing, but the data you supplied included an ID "
                    "that did not match the databag item name. The ID was "
                    "'%s' and the databg item name was '%s'")
        if isinstance(contents, dict):
            contents = json.dumps(contents)
        params = ['knife', 'solo', 'data',
                'bag', 'create', bagname, itemname, '-d', '--json', contents]
        if secret_file:
            params.extend(['--secret-file', secret_file])
        result = _run_kitchen_command(kitchen_path, params)
    LOG.debug(result)


def check_all_output(params):
    """Similar to subprocess check_output, but returns all output in error if
    an error is raised.

    We use this for processing Knife output where the details of the error are
    piped to stdout and the actual error does not have everything we need"""
    ON_POSIX = 'posix' in sys.builtin_module_names

    def start_thread(func, *args):
        t = threading.Thread(target=func, args=args)
        t.daemon = True
        t.start()
        return t

    def consume(infile, output):
        for line in iter(infile.readline, ''):
            output(line)
        infile.close()

    p = Popen(params, stdout=PIPE, stderr=PIPE, bufsize=1, close_fds=ON_POSIX)

    # preserve last N lines of stdout and stderr
    N = 100
    queue = deque(maxlen=N)
    threads = [start_thread(consume, *args)
                for args in (p.stdout, queue.append), (p.stderr, queue.append)]
    for t in threads:
        t.join()  # wait for IO completion

    retcode = p.wait()

    if retcode == 0:
        return ''.join(queue)
    else:
        raise CheckmateCalledProcessError(retcode, ' '.join(params),
                output='\n'.join(queue))


def _get_repo_path():
    """Find the master repo path for chef cookbooks"""
    path = os.environ.get('CHECKMATE_CHEF_REPO')
    if not path:
        path = os.path.join(os.path.dirname(__file__), 'chef-stockton')
        LOG.warning("No CHECKMATE_CHEF_REPO variable set. Defaulting to %s" %
                path)
    return path
