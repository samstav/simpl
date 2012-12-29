"""Chef Solo configuration management provider"""
import httplib
import json
import logging
import os
import urlparse
import yaml

from jinja2 import Environment, DictLoader
from SpiffWorkflow.operators import Attrib, PathAttrib
from SpiffWorkflow.specs import Celery, TransMerge

from checkmate import utils
from checkmate.common import schema
from checkmate.exceptions import CheckmateException
from checkmate.keys import hash_SHA512
from checkmate.providers import ProviderBase
from checkmate.workflows import wait_for
from checkmate.utils import merge_dictionary  # used by transform

LOG = logging.getLogger(__name__)


def register_scheme(scheme):
    '''
    Use this to register a new scheme with urlparse and have it be parsed
    in the same way as http is parsed
    '''
    for method in filter(lambda s: s.startswith('uses_'), dir(urlparse)):
        getattr(urlparse, method).append(scheme)

register_scheme('git')  # without this, urlparse won't handle git:// correctly


class CheckmateNotReady(CheckmateException):
    pass


class Provider(ProviderBase):
    """Implements a Chef Solo configuration management provider"""
    name = 'chef-solo'
    vendor = 'opscode'

    def __init__(self, provider, key=None):
        ProviderBase.__init__(self, provider, key=key)
        self.prep_task = None

        # Map File
        self.source = self.get_setting('source')
        if self.source:
            self.map_file = ChefMap(url=self.source)
        else:
            # Create noop map file
            self.map_file = ChefMap(raw="")

    def prep_environment(self, wfspec, deployment, context):
        if self.prep_task:
            return  # already prepped
        self._hash_all_user_resource_passwords(deployment)

        # Create Celery Task
        settings = deployment.settings()
        keys = settings.get('keys', {})
        deployment_keys = keys.get('deployment', {})
        public_key_ssh = deployment_keys.get('public_key_ssh')
        private_key = deployment_keys.get('private_key')
        secret_key = deployment.get_setting('secret_key')
        source_repo = deployment.get_setting('source', provider_key=self.key)
        defines = {'provider': self.key}
        properties = {'estimated_duration': 10, 'task_tags': ['root']}
        task_name = 'checkmate.providers.opscode.local.create_environment'
        self.prep_task = Celery(wfspec,
                                'Create Chef Environment',
                                task_name,
                                call_args=[deployment['id'], 'kitchen'],
                                public_key_ssh=public_key_ssh,
                                private_key=private_key,
                                secret_key=secret_key,
                                source_repo=source_repo,
                                defines=defines,
                                properties=properties)

        return {'root': self.prep_task, 'final': self.prep_task}

    def add_resource_tasks(self, resource, key, wfspec, deployment, context,
                           wait_on=None):
        """Create and write settings, generate run_list, and call cook"""
        wait_on, service_name, component = self._add_resource_tasks_helper(
                resource, key, wfspec, deployment, context, wait_on)
        #chef_map = self.get_map(component)
        self._add_component_tasks(wfspec, component, deployment, key,
                                  context, service_name)

    def _add_component_tasks(self, wfspec, component, deployment, key,
                             context, service_name):
        # Get component/role or recipe name
        kwargs = {}
        LOG.debug("Determining component from dict: %s" % component.get('id'),
                  extra=component)
        if 'role' in component:
            name = '%s::%s' % (component['id'], component['role'])
        else:
            name = component['id']
            if name == 'mysql':
                name += "::server"  # install server by default, not client

        if component['id'].endswith('-role'):
            kwargs['roles'] = [name[0:-5]]  # trim the '-role'
        else:
            kwargs['recipes'] = [name]
        LOG.debug("Component determined to be %s" % kwargs)

        # Create the cook task
        resource = deployment['resources'][key]
        anchor_task = configure_task = Celery(wfspec,
                'Configure %s: %s (%s)' % (component['id'],
                key, service_name),
               'checkmate.providers.opscode.solo.cook',
                call_args=[
                        PathAttrib('instance:%s/ip' %
                                resource.get('hosted_on', key)),
                        deployment['id']],
                password=PathAttrib('instance:%s/password' %
                        resource.get('hosted_on', key)),
                kitchen_name='kitchen',
                identity_file=Attrib('private_key_path'),
                description="Push and apply Chef recipes on the server",
                defines=dict(resource=key,
                            provider=self.key,
                            task_tags=['final']),
                properties={'estimated_duration': 100},
                **kwargs)

        if self.map_file.has_runtime_options(resource['component']):
            collect_data = self.get_collect_task(wfspec, deployment, key)
            configure_task.follow(collect_data)
            anchor_task = collect_data
        elif self.map_file.has_mappings(resource['component']):
            collect_data = self.get_collect_task(wfspec, deployment, key)
            configure_task.follow(collect_data)
            anchor_task = collect_data

        # Collect dependencies
        dependencies = [self.prep_task]

        # Wait for relations tasks to complete
        for relation_key in resource.get('relations', {}).keys():
            tasks = self.find_tasks(wfspec,
                    resource=key,
                    relation=relation_key,
                    tag='final')
            if tasks:
                dependencies.extend(tasks)

        server_id = resource.get('hosted_on', key)

        wait_for(wfspec, anchor_task, dependencies,
                name="After server %s (%s) is registered and options are ready"
                        % (server_id, service_name),
                description="Before applying chef recipes, we need to know "
                "that the server has chef on it and that the overrides "
                "(ex. database settings) have been applied")

        # if we have a host task marked 'complete', make that wait on configure
        host_complete = self.get_host_complete_task(wfspec, resource)
        if host_complete:
            wait_for(wfspec, host_complete, [configure_task],
                     name='Wait for %s to be configured before completing '
                     'host %s' %
                     (service_name, resource.get('hosted_on', key)))

    def get_collect_task(self, wfspec, deployment, resource_key):
        """

        Get (or create) a task that collects map options

        The task will run its code whenever an input task completes. The code
        to pick up the actual values based on the map comes from the Transforms
        class.

        One collect task is created for each resource and marked with a
        'collect' tag.

        :returns: a TransMerge task for the resource specified in resource_key

        """
        # Does it exist already?
        tasks = self.find_tasks(wfspec,
                                provider=self.key,
                                resource=resource_key,
                                tag='collect')
        if tasks:
            return tasks[0]

        # Create the task
        resource = deployment['resources'][resource_key]
        parsed = self.map_file.parse(self.map_file.raw, deployment=deployment,
                                     resource=resource)
        map_with_context = ChefMap(parsed=parsed)

        maps = self.get_resource_prepared_maps(resource, deployment,
                                               map_file=map_with_context)
        output = map_with_context.get_component_output_template(
                                                         resource['component'])
        source = utils.get_source_body(Transforms.collect_options)
        collect_data = TransMerge(wfspec,
                "Collect Chef Data for %s" % resource_key,
                transforms=[source],
                description="Get data needed for our cookbooks and "
                        "place it in a structure ready for storage in "
                        "a databag or role",
                properties={
                            'task_tags': ['collect'],
                            'chef_maps': maps,
                            'chef_output': output,
                           },
                defines={
                         'provider': self.key,
                         'resource': resource_key,
                        }
                )
        LOG.debug("Created data collection task for '%s'" % resource_key)
        return collect_data

    def get_resource_prepared_maps(self, resource, deployment, map_file=None):
        """Parse maps for a resource and identify paths for finding the map
        data"""
        if map_file is None:
            map_file = self.map_file

        maps = map_file.get_component_maps(resource['component'])
        for mapping in maps or []:

            # find paths for sources

            if 'source' in mapping:
                url = ChefMap.parse_map_URI(mapping['source'])
                if url['scheme'] == 'requirements':
                    key = url['netloc']
                    relations = [r for r in resource['relations'].values()
                                if r.get('source-key') == key]
                    if relations:
                        target = relations[0]['target']
                        mapping['path'] = 'instance:%s/instance/interfaces/%s' % (target, relations[0]['interface'])

        return maps

    def _hash_all_user_resource_passwords(self, deployment):
        """Chef needs all passwords to be a hash"""
        if 'resources' in deployment:
            for resource in deployment['resources'].values():
                if resource.get('type') == 'user':
                    instance = resource.get('instance', {})
                    if 'password' in instance:
                        instance['hash'] = hash_SHA512(instance['password'])

    def add_connection_tasks(self, resource, key, relation, relation_key,
                             wfspec, deployment, context):
        """Write out or Transform data. Provide final task for relation sources
        to hook into"""
        LOG.debug("Adding connection task for resource '%s' for relation '%s'"
                  % (key, relation_key), extra={'data': {'resource': resource,
                  'relation': relation}})

        # Is this relation in one of our maps? If so, let's handle that
        tasks = []
        if self.map_file.has_requirement_mapping(resource['component'],
                                                 relation['source-key']):
            LOG.debug("Relation '%s' for resource '%s' has a mapping"
                      % (relation_key, key))
            # Set up a wait for the relation target to be ready
            tasks = self.find_tasks(wfspec, resource=relation['target'],
                                    tag='final')
        if tasks:
            # The collect task will have received a copy of the map and
            # will pick up the values that it needs when these precursor
            # tasks signal they are complete.
            collect_task = self.get_collect_task(wfspec, deployment, key)
            wait_for(wfspec, collect_task, tasks)

        if relation.get('relation') == 'host':
            # Wait on host to be ready
            wait_on = self.get_host_ready_tasks(resource, wfspec, deployment)
            if not wait_on:
                raise CheckmateException("No host resource found for relation "
                                         "'%s'" % relation_key)

            attributes = self.map_file.get_attributes(resource['component'],
                                                      deployment)
            # Create chef setup tasks
            register_node_task = Celery(wfspec,
                    'Register Server %s (%s)' % (relation['target'],
                                                 resource['service']),
                    'checkmate.providers.opscode.local.register_node',
                    call_args=[
                            PathAttrib('instance:%s/ip' % relation['target']),
                            deployment['id']],
                    password=PathAttrib('instance:%s/password' %
                            relation['target']),
                    kitchen_name='kitchen',
                    attributes=attributes,
                    omnibus_version="10.12.0-1",
                    identity_file=Attrib('private_key_path'),
                    defines=dict(resource=key,
                                relation=relation_key,
                                provider=self.key),
                    description=("Install Chef client on the target machine "
                                 "and register it in the environment"),
                    properties=dict(estimated_duration=120))

            bootstrap_task = Celery(wfspec,
                    'Pre-Configure Server %s (%s)' % (relation['target'],
                                                      resource['service']),
                    'checkmate.providers.opscode.solo.cook',
                    call_args=[
                            PathAttrib('instance:%s/ip' % relation['target']),
                            deployment['id']],
                    password=PathAttrib('instance:%s/password' %
                                        relation['target']),
                    identity_file=Attrib('private_key_path'),
                    description="Install basic pre-requisites on %s"
                                % relation['target'],
                    defines=dict(resource=key,
                                 relation=relation_key,
                                 provider=self.key),
                    properties=dict(estimated_duration=100,
                                    task_tags=['final']))
            bootstrap_task.follow(register_node_task)

            # Register only when server is up and environment is ready
            wait_on.append(self.prep_task)
            root = wait_for(wfspec, register_node_task, wait_on,
                    name="After Environment is Ready and Server %s (%s) is Up"
                            % (relation['target'], resource['service']),
                    resource=key, relation=relation_key, provider=self.key)
            if 'task_tags' in root.properties:
                root.properties['task_tags'].append('root')
            else:
                root.properties['task_tags'] = ['root']
            return dict(root=root, final=bootstrap_task)

    def get_catalog(self, context, type_filter=None):
        """Return stored/override catalog if it exists, else connect, build,
        and return one"""

        # TODO: maybe implement this an on_get_catalog so we don't have to do
        #        this for every provider
        results = ProviderBase.get_catalog(self, context,
                                           type_filter=type_filter)
        if results:
            # We have a prexisting or injected catalog stored. Use it.
            return results

        if self.source:
            # Get remote catalog
            catalog = self.get_remote_catalog()
            # parse out provides

            return catalog

    def get_remote_catalog(self, source=None):
        """Gets the remote catalog from a repo by obtaining a Chefmap file, if
        it exists, and parsing it"""
        if source:
            map_file = ChefMap(url=source)
        else:
            map_file = self.map_file
        catalog = {}
        try:
            for doc in yaml.safe_load_all(map_file.parsed):
                if 'id' in doc:
                    for key in doc.keys():
                        if key not in schema.COMPONENT_SCHEMA:
                            del doc[key]
                    resource_type = doc.get('is', 'application')
                    if resource_type not in catalog:
                        catalog[resource_type] = {}
                    catalog[resource_type][doc['id']] = doc
            LOG.debug('Obtained remote catalog from %s' % map_file.url)
        except ValueError:
            msg = 'Catalog source did not return parsable content'
            raise CheckmateException(msg)
        return catalog


class Transforms():
    """Class to hold transform functions.

    We put them in a separate class to:
    - access them from tests
    - possible, in the future, use them as a library instead of passing the
      actual code in to Spiff for better security

    """
    @staticmethod  # self will actually be a SpiffWorkflow.TaskSpec
    def collect_options(self, my_task):
        """Collect and write run-time options"""
        from checkmate.providers.opscode.solo import ChefMap, CheckmateNotReady
        maps = self.get_property('chef_maps')
        data = my_task.attributes
        queue = []
        for mapping in maps:
            try:
                result = ChefMap.evaluate_mapping_source(mapping, data)
                if result:
                    queue.append((mapping, result))
            except CheckmateNotReady:
                return False  # false means not done
        results = {}
        for mapping, result in queue:
            ChefMap.apply_mapping(mapping, result, results)

        output_template = self.get_property('chef_output', {})
        if output_template:
            merge_dictionary(my_task.attributes, output_template)

        if results:

            # Write chef options and task outputs

            outputs = results.pop('outputs', {})
            if results:
                if 'chef_options' not in my_task.attributes:
                    my_task.attributes['chef_options'] = {}
                merge_dictionary(my_task.attributes['chef_options'], results)

            if outputs:
                merge_dictionary(my_task.attributes, outputs)
                LOG.debug("Writing task outputs: %s" % outputs)
        return True


class ChefMap():
    """Retrieves and parses Chefmap files"""

    @staticmethod
    def resolve_map(mapping, data, output):
        """Resolve mapping and write output"""
        result = ChefMap.evaluate_mapping_source(mapping, data)
        if result:
            ChefMap.apply_mapping(mapping, result, output)

    @staticmethod
    def apply_mapping(mapping, value, output):
        """Applies the mapping value to all the targets

        :param mapping: dict of the mapping
        :param value: the value of the mapping. This is evaluated elsewhere.
        :param output: a dict to apply the mapping to

        """
        for target in mapping.get('targets', []):
            url = ChefMap.parse_map_URI(target)
            if url['scheme'] in ['attributes', 'outputs']:
                if url['scheme'] not in output:
                    output[url['scheme']] = {}
                utils.write_path(output[url['scheme']], url['path'].strip('/'),
                                 value)
                LOG.debug("Wrote to output '%s': %s" % (target, value))
            else:
                raise NotImplemented("Unsupported url scheme '%s'" %
                                     url['scheme'])

    @staticmethod
    def evaluate_mapping_source(mapping, data):
        """
        Returns the mapping source value

        Raises a CheckmateNotReady exception if the source is not yet available

        :param mapping: the mapping to resolved
        :param data: the data to read from
        :returns: the value

        """
        value = None
        if 'source' in mapping:
            url = ChefMap.parse_map_URI(mapping['source'])
            if url['scheme'] == 'requirements':
                path = mapping.get('path', url['netloc'])
                try:
                    value = utils.read_path(data, os.path.join(path,
                                            url['path']))
                except (KeyError, TypeError):
                    LOG.debug("'%s' not yet available at '%s': %s" % (
                              mapping['source'], path, exc), extra={'data': data})
                    raise CheckmateNotReady("Not ready")
                LOG.debug("Resolved mapping '%s' to '%s'" % (mapping['source'],
                          value))
            else:
                raise NotImplemented("Unsupported url scheme '%s'" %
                                     url['scheme'])
        elif 'value' in mapping:
            value = mapping['value']
        else:
            raise CheckmateException("Mapping has neither 'source' nor "
                                     "'value'")
        return value

    def __init__(self, url=None, raw=None, parsed=None):
        """Create a new Chefmap instance

        :param url: is the path to the root git repo. Supported protocols
                       are http, https, and git. The .git extension is
                       optional. Appending a branch name as a #fragment works::

                map_file = ChefMap("http://github.com/user/repo")
                map_file = ChefMap("https://github.com/org/repo.git")
                map_file = ChefMap("git://github.com/user/repo#master")
        :param raw: provide the raw content of the map file
        :param parsed: provide parsed content of the map file

        :return: solo.ChefMap

        """
        self.url = url
        self._raw = raw
        self._parsed = parsed

    @property
    def raw(self):
        """Returns the raw file contents"""
        if self._raw is None:
            self._raw = self.get_remote_map_file()
        return self._raw

    @property
    def parsed(self):
        """Returns the parsed file contents"""
        if self._parsed is None:
            self._parsed = self.parse(self.raw)
        return self._parsed

    @staticmethod
    def get_remote_raw_url(source, path="Chefmap"):
        """Calculates the raw URL for a file based off a source repo"""
        source_repo, ref = urlparse.urldefrag(source)
        url = urlparse.urlparse(source_repo)
        if url.path.endswith('.git'):
            repo_path = url.path[:-4]
        else:
            repo_path = url.path
        scheme = url.scheme if url.scheme != 'git' else 'https'
        full_path = os.path.join(repo_path, 'raw', ref or 'master', path)
        result = urlparse.urlunparse((scheme, url.netloc, full_path,
                                      url.params, url.query, url.fragment))
        return result

    def get_remote_map_file(self):
        """Gets the remote map file from a repo"""
        target_url = self.get_remote_raw_url(self.url)
        url = urlparse.urlparse(target_url)
        if url.scheme == 'https':
            http_class = httplib.HTTPSConnection
            port = url.port or 443
        else:
            http_class = httplib.HTTPConnection
            port = url.port or 80
        host = url.hostname

        http = http_class(host, port)
        headers = {
            'Accept': 'text/plain',
        }

        # TODO: implement some caching to not overload the server
        try:
            LOG.debug('Connecting to %s' % self.url)
            http.request('GET', url.path, headers=headers)
            resp = http.getresponse()
            body = resp.read()
        except StandardError as exc:
            LOG.exception(exc)
            raise exc
        finally:
            http.close()

        if resp.status != 200:
            raise CheckmateException("Map file could not be retrieved from "
                                     "'%s'. The error returned was '%s'" %
                                     (target_url, resp.reason))

        return body

    @property
    def components(self):
        """The components in the map file"""
        return (c for c in yaml.safe_load_all(self.parsed)
                if 'id' in c)

    def has_mappings(self):
        """Does the map file have any mappings?"""
        for component in self.components:
            if component.get('maps'):  # ignore empty maps too
                return True
        return False

    def has_databag_mappings(self):
        """Does the map file have any databag mappings?"""
        for component in self.components:
            databag_maps = (m for m in component.get('maps', [])
                            if (self.parse_map_URI(m.get('source'))['scheme']
                                in ['databags', 'encrypted-databags']))
            if any(databag_maps):
                return True
        return False

    def has_requirement_mapping(self, component_id, requirement_key):
        for component in self.components:
            if component_id == component['id']:
                for m in component.get('maps', []):
                    url = self.parse_map_URI(m.get('source'))
                    if (url['scheme'] == 'requirements' and
                        url['netloc'] == requirement_key):
                        return True
        return False

    def get_attributes(self, component_id, deployment):
        """Get attribute maps for a specific component"""
        for component in self.components:
            if component_id == component['id']:
                maps = (m for m in component.get('maps', [])
                        if any(target for target in m.get('targets', [])
                               if (self.parse_map_URI(target)['scheme'] ==
                                   'attributes')))
                if maps:
                    result = {}
                    for m in maps:
                        value = None
                        try:
                            value = self.evaluate_mapping_source(m, deployment)
                        except CheckmateNotReady:
                            LOG.debug("Map not ready yet: " % m)
                            continue
                        if value:
                            for target in m.get('targets', []):
                                url = self.parse_map_URI(target)
                                if url['scheme'] == 'attributes':
                                    utils.write_path(result, url['path'],
                                                     value)
                    return result

    def has_runtime_options(self, component_id):
        """
        Check if a component has maps that can only be resolved at run-time

        Those would be items like:
        - requirement sources where the required resource does not exist yet

        :returns: boolean

        """
        for component in self.components:
            if component_id == component['id']:
                maps = (m for m in component.get('maps', [])
                                if (self.parse_map_URI(m.get('source'))['scheme']
                                    in ['requirements']))
                if any(maps):
                    return True
        return False

    @staticmethod
    def parse_map_URI(uri):
        """
        Parses the URI format of a map

        :param uri: string uri based on map file supported sources and targets
        :returns: dict

        """
        try:
            parts = urlparse.urlparse(uri)
        except AttributeError:
            # probably a scalar
            parts = urlparse.urlparse('')

        result = {
            'scheme': parts.scheme,
            'netloc': parts.netloc,
            'path': parts.path.strip('/'),
            'query': parts.query,
            'fragment': parts.fragment,
            }
        if parts.scheme in ['attributes', 'output']:
            result['path'] = os.path.join(parts.netloc.strip('/'),
                                          parts.path.strip('/')).strip('/')
        return result

    @staticmethod
    def parse(template, **kwargs):
        """Parse template

        :param template: the template contents as a string
        :param kwargs: extra arguments are passed to the renderer

        """
        env = Environment(loader=DictLoader({'template': template}))

        def do_prepend(value, param='/'):
            """
            Prepend a string if the passed in string exists.

            Example:
            The template '{{ root|prepend('/')}}/path';
            Called with root undefined renders:
                /path
            Called with root defined as 'root' renders:
                /root/path
            """
            if value:
                return '%s%s' % (param, value)
            else:
                return ''
        env.filters['prepend'] = do_prepend

        env.json = json

        def parse_url(value):
            """
            Parse a url into its components.

            Example:
            The template '{{ root|prepend('/')}}/path';
            Called with root undefined renders:
                /path
            Called with root defined as 'root' renders:
                /root/path
            """
            return urlparse.urlparse(value)
        env.globals['parse_url'] = parse_url
        deployment = kwargs.get('deployment')
        resource = kwargs.get('resource')
        if deployment:
            if resource:
                fxn = lambda x: deployment.get_setting(x,
                        resource_type=resource['type'],
                        provider_key=resource['provider'],
                        service_name=resource['service'])
            else:
                fxn = lambda x: deployment.get_setting(x)
        else:
            fxn = lambda x: ''  # noop
        env.globals['setting'] = fxn
        env.globals['hash'] = hash_SHA512

        template = env.get_template('template')
        minimum_kwargs = {
                          'deployment': {'id': ''},
                          'resource': {},
                          'component': {},
                          'clients': [],
                          }
        minimum_kwargs.update(kwargs)
        return template.render(**minimum_kwargs)

#
# Celery Tasks
#
import threading
from celery import task
from checkmate.providers.opscode import local


@task(countdown=20, max_retries=3)
def cook(host, environment, recipes=None, roles=None, path=None,
         username='root', password=None, identity_file=None, port=22,
         attributes=None):
    """Apply recipes/roles to a server"""
    utils.match_celery_logging(LOG)
    root = local._get_root_environments_path(path)
    kitchen_path = os.path.join(root, environment, 'kitchen')
    if not os.path.exists(kitchen_path):
        raise CheckmateException("Environment kitchen does not exist: %s" %
                kitchen_path)
    node_path = os.path.join(kitchen_path, 'nodes', '%s.json' % host)
    if not os.path.exists(node_path):
        cook.retry(exc=CheckmateException("Node '%s' is not registered in %s"
                                          % (host, kitchen_path)))

    # Add any missing recipes to node settings
    run_list = []
    if roles:
        run_list.extend(["role[%s]" % role for role in roles])
    if recipes:
        run_list.extend(["recipe[%s]" % recipe for recipe in recipes])
    if run_list or attributes:
        add_list = []
        # Open file, read/parse/calculate changes, then write
        lock = threading.Lock()
        lock.acquire()
        try:
            with file(node_path, 'r') as f:
                node = json.load(f)
            if run_list:
                for entry in run_list:
                    if entry not in node['run_list']:
                        node['run_list'].append(entry)
                        add_list.append(entry)
            if attributes:
                utils.merge_dictionary(node, attributes)
            if add_list or attributes:
                with file(node_path, 'w') as f:
                    json.dump(node, f)
        finally:
            lock.release()
        if add_list:
            LOG.debug("Added to %s: %s" % (node_path, add_list))
        else:
            LOG.debug("All run_list already exists in %s: %s" % (node_path,
                      run_list))
        if attributes:
            LOG.debug("Wrote attributes to %s" % node_path,
                      extra={'data': attributes})
    else:
        LOG.debug("No recipes or roles to add and no attribute changes. Will "
                  "just run 'knife cook' for %s using bootstrap.json" %
                  node_path)

    # Build and run command
    if not username:
        username = 'root'
    params = ['knife', 'cook', '%s@%s' % (username, host),
              '-c', os.path.join(kitchen_path, 'solo.rb')]
    if not (run_list or attributes):
        params.extend(['bootstrap.json'])
    if identity_file:
        params.extend(['-i', identity_file])
    if password:
        params.extend(['-P', password])
    if port:
        params.extend(['-p', str(port)])
    local._run_kitchen_command(kitchen_path, params)
