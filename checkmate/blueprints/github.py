# eventlet raising false 'no member' warnings - pylint: disable=E1101

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

"""GitHub Classes.

Manager for caching GitHub blueprints
Router for responding to webhooks
"""

from __future__ import absolute_import

import base64
import collections
import copy
import json
import logging
import os
import time
import urlparse

import bottle
import eventlet
from eventlet.green import socket
from eventlet.green import threading
from eventlet import greenpool
import github
from github import GithubException
import redis
from redis import exceptions as redisexc
import yaml

from checkmate.common import caching
from checkmate import exceptions

LOG = logging.getLogger(__name__)
DEFAULT_CACHE_TIMEOUT = 10 * 60
BLUEPRINT_CACHE = {}
ANONYMOUS_BLUEPRINT_CACHE = {}

REDIS = None
if 'CHECKMATE_CACHE_CONNECTION_STRING' in os.environ:
    try:
        REDIS = redis.from_url(os.environ['CHECKMATE_CACHE_CONNECTION_STRING'])
    except StandardError as exc:
        LOG.warn("Error connecting to Redis: %s", exc)


def _handle_ghe(ghe, msg="Unexpected Github error"):
    """Ignore a 404 response from github but log other errors."""
    if ghe.status != 404:
        LOG.warn(msg or "", exc_info=True)


class GitHubManager(object):

    """Manage the catalog of "known good" blueprints."""

    def __init__(self, git_config):
        """Init Github blueprint manager.

        Config params used
        :github_api_base: Base uri for the github api hosting the
                                blueprint repository (required)
        :branch: tag/branch/ref to pull as the "supported" version of
                                the blueprint; defaults to 'master'
        :repo_org: the organization owning the blueprint repositories
        :cache_dir: directory to write cached blueprint data to
        """
        self._github_api_base = git_config.github_api
        if self._github_api_base:
            self._github = github.Github(git_config.github_token,
                                         base_url=self._github_api_base)
            self._api_host = urlparse.urlparse(self._github_api_base).netloc
        self._repo_org = git_config.organization
        self._ref = git_config.ref
        self._cache_root = git_config.cache_dir
        self._cache_file = os.path.join(self._cache_root, ".blueprint_cache")
        self._blueprints = {}
        self._preview_ref = git_config.preview_ref
        self._preview_tenants = git_config.preview_tenants
        self._group_refs = git_config.group_refs or {}
        self._groups = set(self._group_refs.keys())
        assert self._github_api_base, ("Must specify a source blueprint "
                                       "repository")
        assert self._repo_org, ("Must specify a Github organization owning "
                                "blueprint repositories")
        assert self._ref, "Must specify a branch or tag"
        self.background = None
        self.last_refresh = time.time() - DEFAULT_CACHE_TIMEOUT
        self.start_refresh_lock = threading.Lock()
        self.refresh_lock = threading.Lock()
        if not git_config.bottle_parent:
            self.load_cache()
            self.check_cache_freshess()

    def get_tenant_tag(self, tenant_id, tenant_auth_groups):
        """Find the tag to return for this tenant.

        If the tenant is explicitly called out in preview-refs, then use the
        preview ref.
        If the tenant is in a group that has a tag, then return that ref (first
        match wins).
        Otherwise, default to ref.
        Finally, if none specified, use 'master'
        """
        assert tenant_id, "must provide a tenant id"

        if self._preview_tenants and tenant_id in self._preview_tenants:
            return self._preview_ref or self._ref or 'master'

        if tenant_auth_groups and self._groups:
            try:
                group = (x for x in tenant_auth_groups
                         if x in self._groups).next()
                return self._group_refs[group]
            except StopIteration:
                pass  # No match

        return self._ref or 'master'

    @property
    def api_host(self):
        """Source for github request.

        :return: source Github api host (not url)
        """
        return self._api_host

    @property
    def repo_owner(self):
        """Github repository owner (org or user).

        :return: repository owner
        """
        return self._repo_org

    #
    # blueprint calls
    #
    def _paginate(self, results, offset, limit, details):
        """ Paginate a set of results.

        :param results: Result dict that need to be paginated
        :param offset: pagination offset
        :param limit: pagination limit
        :param details: amount of detail to return about a blueprint
        :return: A dict of the results paginated if needed.
        """
        # Skip filtering for most common use case (details=1 and no pagination)
        only_basic_info = details is 0
        paginate = offset > 0 or len(results) > limit
        collection_count = len(results)
        if results and (only_basic_info or paginate):
            LOG.debug("Paginating blueprints for %s/%s with offset:%d, "
                      "limit:%d, details:%d" %
                      (self._github_api_base, self._repo_org,
                       offset, limit, details))

            blueprint_ids = results.keys()
            blueprint_ids.sort()
            if only_basic_info:
                results = {
                    k: v for k, v in results.iteritems()
                    if k in blueprint_ids[offset:offset + limit]
                }
            else:
                results = {
                    k: {
                        "name": v.get("blueprint", {}).get("name"),
                        "description": v.get("blueprint", {})
                                        .get("description")
                    } for k, v in self._blueprints.iteritems()
                    if k in blueprint_ids[offset:offset + limit]
                }

        self.check_cache_freshess()

        return {
            'collection-count': collection_count,
            '_links': {},
            'results': results,
        }

    def get_blueprints(self, tenant_id=None, offset=0, limit=100, details=0,
                       roles=None):
        """Return an abbreviated list of known deployment blueprints.

        :param offset: pagination start
        :param limit: pagination length
        """
        tag = self.get_tenant_tag(tenant_id, roles)
        self._blocking_refresh_if_needed()

        if not tag:
            return
        offset = offset or 0
        limit = limit or 100

        preview = self._preview_tenants and tenant_id in self._preview_tenants
        results = self._get_blueprint_list_by_tag(tag, include_preview=preview)

        return self._paginate(results, offset, limit, details)

    def get_all_blueprints(self, offset=None, limit=100, details=0):
        """Return a full list of known blueprints.

        :param offset: pagination start
        :param limit: pagination length
        :param details: detail level of blueprints
        """
        offset = offset or 0
        limit = limit or 100
        results = self._get_full_blueprint_list()

        return self._paginate(results, offset, limit, details)

    def list_cache(self):
        """List cached blueprints."""
        results = {}
        for key, blueprint in self._blueprints.iteritems():
            try:
                source = blueprint['blueprint'].get('source') or {}
                sha = source.get('sha') or key  # to not break on old format
                results[sha] = {
                    'id': blueprint['blueprint'].get('id') or key,
                    'name': blueprint['blueprint']['name'],
                    'version': blueprint['blueprint'].get('version'),
                    'repo-url': source.get('repo-url'),
                    'sha': sha,
                }
            except KeyError as exc:
                LOG.info("Error parsing blueprint '%s': missing key %s", key,
                         exc)
                continue
            except StandardError as exc:
                LOG.info("Error parsing blueprint '%s': %s", key, exc)
                continue
        return {
            'collection-count': len(results),
            '_links': {},
            'results': results,
        }

    @caching.CacheMethod(store=BLUEPRINT_CACHE, timeout=60,
                         backing_store=REDIS)
    def _get_full_blueprint_list(self):
        """Return a full dict of known blueprints."""
        return self._blueprints

    @caching.CacheMethod(store=BLUEPRINT_CACHE, timeout=60,
                         backing_store=REDIS)
    def _get_blueprint_list_by_tag(self, tag, include_preview=False):
        """Filter blueprints to show.

        :param tag: git to include
        :param include_preview: if preview blueprints should be included
        :returns: filtered blueprints dict
        """
        LOG.debug("Filtering blueprints: cache miss")
        results = {}
        if include_preview:
            # override default blueprint with preview blueprint
            preview_filter = ":%s" % self._preview_ref
            preview_blueprint_id_prefixes = [
                key.split(":")[0] for key in self._blueprints.keys()
                if key.endswith(preview_filter)
            ]
            filtered_ids = self._blueprints.keys()
            for key in self._blueprints.keys():
                for preview_key in preview_blueprint_id_prefixes:
                    if (key.startswith("%s:" % preview_key) and
                            key != "%s:%s" % (preview_key, self._preview_ref)):
                        filtered_ids.remove(key)
            results = {
                key: value for key, value in self._blueprints.items()
                if key in filtered_ids
            }
        else:
            tag_filter = ":%s" % tag
            results = {
                key: value for key, value in self._blueprints.items()
                if key.endswith(tag_filter)
            }
        return results

    def get_blueprint(self, blueprint_id):
        """Get blueprint by id.

        :param blueprint_id: the deployment blueprint identifier
        :returns: the specified deployment blueprint
        """
        if not self._blueprints:
            self.refresh_all()

        return self._blueprints.get(str(blueprint_id))

    #
    # refresh
    #
    def _blocking_refresh_if_needed(self):
        """If _blueprints is None, perform a refresh of all blueprints."""
        if not self._blueprints:
            # Wait for refresh to complete (block)
            if self.background is None:
                self.start_background_refresh()
            try:
                LOG.warning("Call to GET /blueprints blocking on refresh")
                self.refresh_lock.acquire()
            finally:
                self.refresh_lock.release()

    def background_refresh(self):
        """Called by background thread to start a refresh."""
        with self.refresh_lock:
            LOG.info("Starting background refresh of blueprint cache")
            try:
                self.refresh_all()
                LOG.info("Background refresh of blueprint cache complete")
            except StandardError as exc:
                LOG.warning("Background refresh of blueprint cache failed: %s",
                            exc)
            finally:
                self.background = None

    def start_background_refresh(self):
        """Initiate a background refresh of all blueprints."""
        if self.background is None and self.start_refresh_lock.acquire(False):
            try:
                self.background = eventlet.spawn_n(self.background_refresh)
                LOG.debug("Refreshing blueprint cache")
            except StandardError:
                self.background = None
                LOG.error("Error initiating refresh", exc_info=True)
                raise
            finally:
                self.start_refresh_lock.release()
        else:
            LOG.debug("Already refreshing")

    def _update_cache(self):
        """Write the current blueprint map to local disk and Redis."""
        if REDIS:
            try:
                timestamped = copy.copy(self._blueprints)
                timestamped['timestamp'] = self.last_refresh
                value = json.dumps(timestamped)
                REDIS.setex('blueprint_cache', value, DEFAULT_CACHE_TIMEOUT)
                LOG.info("Wrote blueprints to Redis")
            except redisexc.ConnectionError as exc:
                LOG.warn("Error connecting to Redis: %s", exc)
            except StandardError:
                pass

        if not os.path.exists(self._cache_root):
            try:
                os.makedirs(self._cache_root, 0o770)
            except (OSError, IOError):
                LOG.warn("Could not create cache directory", exc_info=True)
                return
        try:
            with open(self._cache_file, 'w') as cache:
                cache.write(json.dumps(self._blueprints))
        except IOError:
            LOG.warn("Error updating disk cache", exc_info=True)
        else:
            LOG.info("Cached blueprints to file: %s", self._cache_file)

    def _refresh_from_repo(self, repo):
        """Store/update blueprint info from the specified repository.

        :param repo: the repository containing blueprint data or :None:
        """
        if repo:
            self._refresh_blueprint(repo, self._ref)
            if self._preview_ref:
                self._refresh_blueprint(repo, self._preview_ref)

    def _refresh_blueprint(self, repo, ref):
        """Get a new copy of the specified blueprint."""
        rid = "%s:%s" % (str(repo.id), ref)
        blueprint = self._get_blueprint(repo, ref)
        if rid in self._blueprints:
            del self._blueprints[rid]
        self._store(blueprint, self._ref, self._blueprints)

    def refresh(self, repo_name):
        """Get updated blueprint info from GitHub

        Get updated deployment blueprint information from the specified
        github repository.

        :param repo_name: the name of the github repository containing the
                          the blueprint
        """
        self._refresh_from_repo(self._get_repo(repo_name))
        self._update_cache()

    def refresh_all(self):
        """Get deployment blueprints owned by :self.repo_org:.

        Get all deployment blueprints from the repositories owned by
        :self.repo_org:.
        """
        org = self._get_repo_owner()
        if not org:
            LOG.error("No user or group matching %s", self._repo_org)
            return
        refs = [self._ref, self._preview_ref] + self._group_refs.values()
        refs = list(set([ref for ref in refs if ref]))
        repos = org.get_repos()

        pool = greenpool.GreenPile()
        for ref in refs:
            for repo in repos:
                pool.spawn(self._get_blueprint, repo, ref)

        fresh = {}
        for ref in refs:
            for repo, result in zip(repos, pool):
                self._store(result, ref, fresh)

        self._blueprints = fresh
        self.last_refresh = time.time()
        self._update_cache()

    def check_cache_freshess(self):
        """Check if cache is up to date and trigger refresh if not."""
        if (self.background is None and
                time.time() - self.last_refresh > DEFAULT_CACHE_TIMEOUT):
            if not self._load_redis_cache():
                self.start_background_refresh()

    def _load_redis_cache(self):
        """Load blueprints from Redis.

        :returns: True if loaded valid blueprints
        """
        if REDIS:
            try:
                cache = REDIS['blueprint_cache']
                data = json.loads(cache)
                timestamp = data.pop('timestamp', None)
                self._blueprints = data  # make available to calls
                if timestamp:
                    self.last_refresh = timestamp
                    expire = (timestamp + DEFAULT_CACHE_TIMEOUT) - time.time()
                    if expire > 0:
                        LOG.info("Retrieved blueprints from Redis with %ss "
                                 "left until they expire", int(expire))
                        return True
                    else:
                        LOG.debug("Retrieved expired blueprints.")
            except redisexc.ConnectionError as exc:
                LOG.warn("Error connecting to Redis: %s", exc)
            except KeyError:
                pass  # expired or not there
            except StandardError as exc:
                LOG.debug("Error retrieving blueprints from Redis: %s", exc)
        return False

    def load_cache(self):
        """Pre-seed with existing cache if any

        Only in case we can't connect to the repo.
        """
        if not self._load_redis_cache():
            if os.path.exists(self._cache_file):
                try:
                    with open(self._cache_file, 'r') as cache:
                        self._blueprints = json.load(cache)
                        LOG.info("Retrieved blueprints from cache file")
                except IOError:
                    LOG.warn("Could not load cache file", exc_info=True)
                except ValueError:
                    LOG.warn("Cache file contains invalid data", exc_info=True)

    #
    # blueprint parsing
    #
    def blueprint_is_invalid(self, untrusted_blueprint):
        """Return true if passed-in blueprint does NOT pass validation."""
        return not self.blueprint_is_valid(untrusted_blueprint)

    def blueprint_is_valid(self, untrusted_blueprint):
        """Return true if passed-in blueprint passes validation."""
        self._blocking_refresh_if_needed()
        for key, trusted_blueprint in self._blueprints.iteritems():
            try:
                if self._same_source_new(untrusted_blueprint,
                                         trusted_blueprint):
                    untrusted_blueprint['blueprint'] = \
                        trusted_blueprint['blueprint']
                    self._clean_env(untrusted_blueprint['environment'],
                                    trusted_blueprint['environment'])
                    return True
            except StandardError:
                LOG.error("Error processing blueprint: %s", key,
                          extra={'data': trusted_blueprint})
                continue
        return False

    def parse_blueprint(self, repo, content):
        """Parse dict as a checkmate blueprint."""
        if 'documentation' not in content['blueprint']:
            content['blueprint']['documentation'] = {}

        # if blueprint does not contain abstract field, check repo for
        # abstract.md file
        self._inline_documentation_field(content['blueprint'], repo,
                                         'abstract')

        # if blueprint does not contain instructions field, check repo
        # for instructions.md
        self._inline_documentation_field(content['blueprint'], repo,
                                         'instructions')

        # if blueprint does not contain guide field, check repo for
        # guide.md
        self._inline_documentation_field(content['blueprint'], repo,
                                         'guide')

        content['repo_id'] = repo.id
        return content

    @staticmethod
    def parse_hot(content):
        """Parse dict as a HOT template."""
        types = {
            'String': 'string',
            'Number': 'integer',
        }
        blueprint = {}
        if 'parameters' in content:
            blueprint['options'] = copy.deepcopy(content['parameters'])
            for _, value in blueprint['options'].iteritems():
                value['type'] = types.get(value.get('type'), 'String')
            blueprint['options']['API Key'] = {
                'label': 'Your API Key',
                'help': 'Heat requires your API key',
                'type': 'string',
                'required': True
            }
        blueprint['meta-data'] = {
            "schema-version": "v0.7",
            "application-name": "Heat Template",
            "blueprint-type": "Application",
            "flavor": "Example Heat Template",
            "flavor-weight": 2,
            "application-version": "Preview",
            "reach-info": {
                "tattoo": "http://7555e8905adb704bd73e-744765205721eed93c384da\
e790e86aa.r66.cf2.rackcdn.com/heat-tattoo.png",
                "icon-20x20": "http://7555e8905adb704bd73e-744765205721eed93c3\
84dae790e86aa.r66.cf2.rackcdn.com/heat-20x20.png",
            },
        }
        blueprint["documentation"] = {
            "abstract": "HOT template converted for Rackspace Deployements "
            "compatibility",
            "instructions": "This is a demo conversion from HOT (OpenStack's "
            "Heat Orchestration Template) syntax to Rackspace Deployments "
            "Service format."
        }
        content['blueprint'] = blueprint
        return content

    def _inline_documentation_field(self, blueprint, repo, doc_field):
        """Set documentation field.

        'documentation.abstract/instructions/guide' etc... field if they are
        not present in the blueprint and respective
        abstract.md/instructions.md/guide.md files exists in repo

        :param blueprint: the blueprint blueprint
        :param repo: the repo containing the blueprint
        :param doc_field: documentation field in the blueprint
        """

        file_name = ""
        # if a field (abstract/instructions/guide) does not exist in the
        # blueprint, then check for {field}.md file in the repo
        if doc_field not in blueprint['documentation']:
            file_name = doc_field + ".md"
        else:
            # if the field exists, check if it is a relative path. If it
            # is a relative path, then inline the content from that file
            field_content = blueprint['documentation'][doc_field]
            if field_content and field_content.startswith("=include('"):
                file_name = field_content.replace("=include('", '')
                file_name = file_name.replace("')", '')

        if file_name:
            file_content = self._get_repo_file_contents(repo, file_name)
            if file_content:
                blueprint['documentation'][doc_field] = file_content

    #
    # github repo
    #
    def _get_repo_owner(self):
        """Return the user or organization owning the repo."""
        if self._repo_org:
            try:
                return self._github.get_organization(self._repo_org)
            except GithubException:
                LOG.debug("Could not retrieve org information for %s; trying "
                          "users", self._repo_org, exc_info=True)
                try:
                    return self._github.get_user(self._repo_org)
                except GithubException:
                    LOG.warn("Could not find user or org %s.", self._repo_org)

    @staticmethod
    def _get_source(provider):
        """Given a dict of providers, return the 'source' from 'chef-solo'."""
        # Scary assumptions here...
        return provider['constraints'][0]['source']

    def _same_source_new(self, untrusted, trusted):
        """Checks source in blueprints. Falls back to chef-solo for now.

        TODO(zns): remove chef-solo logic once all is rolled out (pawn, etc...)
        """
        try:
            return (trusted['blueprint']['source'] ==
                    untrusted['blueprint']['source'])
        except StandardError:
            LOG.info('X-Source-Untrusted: source did not match: %s', untrusted)
            return self._same_source(untrusted, trusted)  # fall back

    def _same_source(self, untrusted, trusted):
        """If chef-solo's 'source' is the same in both, return True."""
        if not untrusted or not trusted:
            return False
        if 'environment' not in trusted:
            return False
        if 'environment' not in untrusted:
            return False
        untrusted_p = untrusted['environment'].get('providers', {})
        try:  # Something in `trusted` can sometimes be a float?!
            trusted_p = trusted['environment'].get('providers', {})
        except TypeError:  # Because float doesn't have a __getitem__
            LOG.info('X-Source-Untrusted: something in cached blueprint '
                     'should be a dict but is not. Blueprint: %s', trusted)
            return False
        if not untrusted_p.get('chef-solo') or not trusted_p.get('chef-solo'):
            return False
        return (self._get_source(untrusted_p['chef-solo']) ==
                self._get_source(trusted_p['chef-solo']))

    @staticmethod
    def _clean_env(untrusted_env, trusted_env):
        """Update all values in untrusted_env with thsoe from trusted_env."""
        delta = set(untrusted_env.keys()) - set(trusted_env.keys())
        if delta:
            LOG.info('X-Source-Untrusted: invalid environment options found.')
            raise exceptions.CheckmateValidationException(
                'POST deployment: environment not valid.')
        for key in untrusted_env.keys():
            untrusted_env[key] = trusted_env[key]

    def _get_repo(self, repo_name):
        """Return the specified github repo.

        :param repo_name: the repo to get; must belong to :self.repo_org:
        """
        if repo_name:
            owner = self._get_repo_owner()
            if owner:
                try:
                    return owner.get_repo(repo_name)
                except GithubException as ghe:
                    _handle_ghe(ghe,
                                msg="Unexpected error getting repository %s"
                                % repo_name)

    @staticmethod
    def _repo_find_ref(repo, ref_name):
        """Return a reference or tag if the repo contains it."""
        refs = repo.get_git_refs()
        if '/' in ref_name:
            return refs.get(ref_name)
        else:
            ref_ending = '/%s' % ref_name
            for ref in refs:
                if '/pull/' not in ref.ref and ref.ref.endswith(ref_ending):
                    return ref

    def _get_blueprint(self, repo, tag):
        """Get the deployment blueprint from the specified repo if any; format
        and correct as needed.

        :param repo: the repo containing the blueprint
        """
        if repo and isinstance(repo, github.Repository.Repository) and tag:
            dep_file = None
            try:
                github_ref = self._repo_find_ref(repo, tag)
                if not github_ref:
                    return None

                dep_file = repo.get_file_contents("checkmate.yaml",
                                                  ref=tag)
            except GithubException as ghe:
                _handle_ghe(ghe,
                            msg="Unexpected error getting blueprint from repo "
                            "%s" % repo.clone_url)
            if dep_file and dep_file.content:
                dep_content = base64.b64decode(dep_file.content)
                dep_content = dep_content.replace("%repo_url%",
                                                  "%s" % str(repo.ssh_url))
                try:
                    ret = yaml.safe_load(dep_content)
                except (yaml.scanner.ScannerError, yaml.parser.ParserError):
                    LOG.warn("Blueprint '%s' has invalid YAML", repo.clone_url)
                    return None

                if "inputs" in ret:
                    del ret['inputs']

                if 'heat_template_version' in ret:
                    parsed = self.parse_hot(ret)
                elif 'blueprint' in ret:
                    parsed = self.parse_blueprint(repo, ret)
                else:
                    LOG.warn("Blueprint '%s' is not in a recognized format",
                             repo.clone_url)
                    return None

                parsed['repo_id'] = repo.id
                parsed['blueprint']['source'] = {
                    'repo-url': repo.ssh_url,
                    'sha': github_ref.object.sha,
                    'ref': github_ref.ref,
                }
                LOG.info("Retrieved blueprint: %s#%s", repo.url, tag)
                return parsed
        return None

    @staticmethod
    def _get_repo_file_contents(repo, filename):
        """Get contents of the given file from the repository.

        :param repo: the repo containing the blueprint
        :param filename: file name
        """
        isinstance(repo, github.Repository.Repository)
        try:
            repo_file = repo.get_file_contents(filename)
            return base64.b64decode(repo_file.content)

        except GithubException:
            return None

    @staticmethod
    def _store(blueprint, tag, target):
        """Store the blueprint in the target memory.

        :param blueprint: the deployment blueprint to store
        """
        if blueprint and tag and isinstance(blueprint, collections.Mapping):
            if "repo_id" not in blueprint:
                LOG.warn("Blueprint id missing in: %s", blueprint)
            else:
                bp_id = "%s:%s" % (blueprint.get("repo_id"), tag)
                del blueprint['repo_id']
                target.update({bp_id: blueprint})


class AnonymousGitHubManager(object):

    """Manage the catalog of "known good" anonymous blueprints."""

    def __init__(self, git_config):
        """Init Github blueprint manager.

        Config params used
        :anonymous_github_base_uri: Base uri for the github api hosting the
                                blueprint repository (required)
        :anonymous_github_ref: tag/branch/ref to pull as the "supported"
                                version of the blueprint; defaults to 'master'
        :anonymous_github_org: the organization owning the blueprint
                                repositories.
        :cache_dir: directory to write cached blueprint data to
        """
        self._github_api_base = git_config.anonymous_github_base_uri
        if self._github_api_base:
            self._github = github.Github(base_url=self._github_api_base)
            self._api_host = urlparse.urlparse(self._github_api_base).netloc
        self._repo_org = git_config.anonymous_github_org
        self._ref = git_config.anonymous_github_ref
        self._cache_root = git_config.cache_dir
        self._cache_file = os.path.join(self._cache_root,
                                        ".anon_blueprint_cache")
        self._blueprints = {}
        assert self._github_api_base, ("Must specify a source blueprint "
                                       "repository")
        assert self._repo_org, ("Must specify a Github organization owning "
                                "blueprint repositories")
        assert self._ref, "Must specify a branch or tag"
        self.background = None
        self.last_refresh = time.time() - DEFAULT_CACHE_TIMEOUT
        self.start_refresh_lock = threading.Lock()
        self.refresh_lock = threading.Lock()
        if not git_config.bottle_parent:
            self.load_cache()
            self.check_cache_freshness()

    @property
    def api_host(self):
        """Source for github request.

        :return: source Github api host (not url)
        """
        return self._api_host

    @property
    def repo_owner(self):
        """Github repository owner (org or user).

        :return: repository owner
        """
        return self._repo_org

    #
    # blueprint calls
    #
    def get_blueprints(self, offset=0, limit=100, details=0):
        """Return an abbreviated list of known deployment blueprints.

        :param offset: pagination start
        :param limit: pagination length
        :param details: amount detail to include
        """
        tag = self._ref
        if not tag:
            return
        offset = offset or 0
        limit = limit or 100

        results = self._get_blueprint_list_by_tag(tag)

        # Skip filtering for most common use case (details=1 and no pagination)
        only_basic_info = details is 0
        paginate = offset > 0 or len(results) > limit
        if results and (only_basic_info or paginate):
            LOG.debug("Paginating blueprints")
            blueprint_ids = results.keys()
            blueprint_ids.sort()
            if only_basic_info:
                results = {
                    k: v for k, v in results.iteritems()
                    if k in blueprint_ids[offset:offset + limit]
                }
            else:
                results = {
                    k: {
                        "name": v.get("blueprint", {}).get("name"),
                        "description": v.get("blueprint", {})
                                        .get("description")
                    } for k, v in self._blueprints.iteritems()
                    if k in blueprint_ids[offset:offset + limit]
                }

        self.check_cache_freshness()

        return {
            'collection-count': len(results),
            '_links': {},
            'results': results,
        }

    def list_cache(self):
        """List cached blueprints."""
        results = {}
        for key, blueprint in self._blueprints.iteritems():
            try:
                source = blueprint['blueprint'].get('source') or {}
                sha = source.get('sha') or key  # to not break on old format
                results[sha] = {
                    'id': blueprint['blueprint'].get('id') or key,
                    'name': blueprint['blueprint']['name'],
                    'version': blueprint['blueprint'].get('version'),
                    'repo-url': source.get('repo-url'),
                    'sha': sha,
                }
            except KeyError as exc:
                LOG.info("Error parsing blueprint '%s': missing key %s", key,
                         exc)
                continue
            except StandardError as exc:
                LOG.info("Error parsing blueprint '%s': %s", key, exc)
                continue
        return {
            'collection-count': len(results),
            '_links': {},
            'results': results,
        }

    @caching.CacheMethod(store=ANONYMOUS_BLUEPRINT_CACHE, timeout=60,
                         backing_store=REDIS,
                         backing_store_key='anon_blueprint_cache')
    def _get_blueprint_list_by_tag(self, tag):
        """Filter blueprints to show.

        :param tag: git to include
        :returns: filtered blueprints dict
        """
        LOG.debug("Filtering blueprints: cache miss")
        tag_filter = ":%s" % tag
        return {
            key: value for key, value in self._blueprints.items()
            if key.endswith(tag_filter)
        }

    def get_blueprint(self, blueprint_id):
        """Get blueprint by id.

        :param blueprint_id: the deployment blueprint identifier
        :returns: the specified deployment blueprint
        """
        if not self._blueprints:
            self.refresh_all()

        return self._blueprints.get(str(blueprint_id))

    #
    # refresh
    #
    def _blocking_refresh_if_needed(self):
        """If _blueprints is None, perform a refresh of all blueprints."""
        if not self._blueprints:
            # Wait for refresh to complete (block)
            if self.background is None:
                self.start_background_refresh()
            try:
                LOG.warning("Call to GET /blueprints blocking on refresh")
                self.refresh_lock.acquire()
            finally:
                self.refresh_lock.release()

    def background_refresh(self):
        """Called by background thread to start a refresh."""
        with self.refresh_lock:
            LOG.info("Starting background refresh of blueprint cache")
            try:
                self.refresh_all()
                LOG.info("Background refresh of blueprint cache complete")
            except StandardError as exc:
                LOG.warning("Background refresh of blueprint cache failed: %s",
                            exc)
            finally:
                self.background = None

    def start_background_refresh(self):
        """Initiate a background refresh of all blueprints."""
        if self.background is None and self.start_refresh_lock.acquire(False):
            try:
                self.background = eventlet.spawn_n(self.background_refresh)
                LOG.debug("Refreshing blueprint cache")
            except StandardError:
                self.background = None
                LOG.error("Error initiating refresh", exc_info=True)
                raise
            finally:
                self.start_refresh_lock.release()
        else:
            LOG.debug("Already refreshing")

    def _update_cache(self):
        """Write the current blueprint map to local disk and Redis."""
        if REDIS:
            try:
                timestamped = copy.copy(self._blueprints)
                timestamped['timestamp'] = self.last_refresh
                value = json.dumps(timestamped)
                REDIS.setex('anon_blueprint_cache', value,
                            DEFAULT_CACHE_TIMEOUT)
                LOG.info("Wrote blueprints to Redis")
            except redisexc.ConnectionError as exc:
                LOG.warn("Error connecting to Redis: %s", exc)
            except StandardError:
                pass

        if not os.path.exists(self._cache_root):
            try:
                os.makedirs(self._cache_root, 0o770)
                LOG.info("Created cache directory: %s", self._cache_root)
            except (OSError, IOError):
                LOG.warn("Could not create cache directory", exc_info=True)
                return
        try:
            with open(self._cache_file, 'w') as cache:
                cache.write(json.dumps(self._blueprints))
        except IOError:
            LOG.warn("Error updating disk cache", exc_info=True)
        else:
            LOG.info("Cached blueprints to file: %s", self._cache_file)

    def _refresh_from_repo(self, repo):
        """Store/update blueprint info from the specified repository.

        :param repo: the repository containing blueprint data or :None:
        """
        if repo:
            self._refresh_blueprint(repo, self._ref)

    def _refresh_blueprint(self, repo, ref):
        """Get a new copy of the specified blueprint."""
        rid = "%s:%s" % (str(repo.id), ref)
        blueprint = self._get_blueprint(repo, ref)
        if rid in self._blueprints:
            del self._blueprints[rid]
        self._store(blueprint, self._ref, self._blueprints)

    def refresh(self, repo_name):
        """Get updated deployment blueprint information from the specified
        github repository.

        :param repo_name: the name of the github repository containing the
                          the blueprint
        """
        self._refresh_from_repo(self._get_repo(repo_name))
        self._update_cache()

    def refresh_all(self):
        """Get all deployment blueprints from the repositories owned by
        :self._repo_org:.
        """
        org = self._get_repo_owner()
        if not org:
            LOG.error("No user or group matching %s", self._repo_org)
            return
        repos = org.get_repos()

        pool = greenpool.GreenPile()
        for repo in repos:
            pool.spawn(self._get_blueprint, repo, self._ref)

        fresh = {}

        for repo, result in zip(repos, pool):
            self._store(result, self._ref, fresh)

        self._blueprints = fresh
        self.last_refresh = time.time()
        self._update_cache()

    def check_cache_freshness(self):
        """Check if cache is up to date and trigger refresh if not."""
        if (self.background is None and
                time.time() - self.last_refresh > DEFAULT_CACHE_TIMEOUT):
            if not self._load_redis_cache():
                self.start_background_refresh()

    def _load_redis_cache(self):
        """Load blueprints from Redis.

        :returns: True if loaded valid blueprints
        """
        if REDIS:
            try:
                cache = REDIS['anon_blueprint_cache']
                data = json.loads(cache)
                timestamp = data.pop('timestamp', None)
                self._blueprints = data  # make available to calls
                if timestamp:
                    self.last_refresh = timestamp
                    expire = (timestamp + DEFAULT_CACHE_TIMEOUT) - time.time()
                    if expire > 0:
                        LOG.info("Retrieved blueprints from Redis with %ss "
                                 "left until they expire", int(expire))
                        return True
                    else:
                        LOG.debug("Retrieved expired blueprints.")
            except redisexc.ConnectionError as exc:
                LOG.warn("Error connecting to Redis: %s", exc)
            except KeyError:
                pass  # expired or not there
            except StandardError as exc:
                LOG.debug("Error retrieving blueprints from Redis: %s", exc)
        return False

    def load_cache(self):
        """Pre-seed with existing cache if any in case we can't connect to the
        repo.
        """
        if not self._load_redis_cache():
            if os.path.exists(self._cache_file):
                try:
                    with open(self._cache_file, 'r') as cache:
                        self._blueprints = json.load(cache)
                        LOG.info("Retrieved blueprints from cache file")
                except IOError:
                    LOG.warn("Could not load cache file", exc_info=True)
                except ValueError:
                    LOG.warn("Cache file contains invalid data", exc_info=True)

    #
    # blueprint parsing
    #
    def parse_blueprint(self, repo, content):
        """Parse dict as a checkmate blueprint."""
        if 'documentation' not in content['blueprint']:
            content['blueprint']['documentation'] = {}

        # if blueprint does not contain abstract field, check repo for
        # abstract.md file
        self._inline_documentation_field(content['blueprint'], repo,
                                         'abstract')

        # if blueprint does not contain instructions field, check repo
        # for instructions.md
        self._inline_documentation_field(content['blueprint'], repo,
                                         'instructions')

        # if blueprint does not contain guide field, check repo for
        # guide.md
        self._inline_documentation_field(content['blueprint'], repo,
                                         'guide')

        content['repo_id'] = repo.id
        return content

    @staticmethod
    def parse_hot(content):
        """Parse dict as a HOT template."""
        types = {
            'String': 'string',
            'Number': 'integer',
        }
        blueprint = {}
        if 'parameters' in content:
            blueprint['options'] = copy.deepcopy(content['parameters'])
            for _, value in blueprint['options'].iteritems():
                value['type'] = types.get(value.get('type'), 'String')
            blueprint['options']['API Key'] = {
                'label': 'Your API Key',
                'help': 'Heat requires your API key',
                'type': 'string',
                'required': True
            }
        blueprint['meta-data'] = {
            "schema-version": "v0.7",
            "application-name": "Heat Template",
            "blueprint-type": "Application",
            "flavor": "Example Heat Template",
            "flavor-weight": 2,
            "application-version": "Preview",
            "reach-info": {
                "tattoo": "http://7555e8905adb704bd73e-744765205721eed93c384da\
e790e86aa.r66.cf2.rackcdn.com/heat-tattoo.png",
                "icon-20x20": "http://7555e8905adb704bd73e-744765205721eed93c3\
84dae790e86aa.r66.cf2.rackcdn.com/heat-20x20.png",
            },
        }
        blueprint["documentation"] = {
            "abstract": "HOT template converted for Rackspace Deployements "
            "compatibility",
            "instructions": "This is a demo conversion from HOT (OpenStack's "
            "Heat Orchestration Template) syntax to Rackspace Deployments "
            "Service format."
        }
        content['blueprint'] = blueprint
        return content

    def _inline_documentation_field(self, blueprint, repo, doc_field):
        """Set documentation field.

        'documentation.abstract/instructions/guide' etc... field if they are
        not present in the blueprint and respective
        abstract.md/instructions.md/guide.md files exists in repo

        :param blueprint: the blueprint blueprint
        :param repo: the repo containing the blueprint
        :param doc_field: documentation field in the blueprint
        """

        file_name = ""
        # if a field (abstract/instructions/guide) does not exist in the
        # blueprint, then check for {field}.md file in the repo
        if doc_field not in blueprint['documentation']:
            file_name = doc_field + ".md"
        else:
            # if the field exists, check if it is a relative path. If it
            # is a relative path, then inline the content from that file
            field_content = blueprint['documentation'][doc_field]
            if field_content and field_content.startswith("=include('"):
                file_name = field_content.replace("=include('", '')
                file_name = file_name.replace("')", '')

        if file_name:
            file_content = self._get_repo_file_contents(repo, file_name)
            if file_content:
                blueprint['documentation'][doc_field] = file_content

    #
    # github repo
    #
    def _get_repo_owner(self):
        """Return the user or organization owning the repo."""
        if self._repo_org:
            return self._retrieve_repo_owner(self._github, self._repo_org)

    @staticmethod
    def _retrieve_repo_owner(github_instance, owner):
        try:
            return github_instance.get_organization(owner)
        except GithubException:
            LOG.debug("Could not retrieve org information for %s; trying "
                      "users", owner, exc_info=True)
            try:
                return github_instance.get_user(owner)
            except GithubException:
                LOG.warn("Could not find user or org %s.", owner)

    def _get_repo(self, repo_name):
        """Return the specified github repo.

        :param repo_name: the repo to get; must belong to :self.repo_org:
        """
        if repo_name:
            owner = self._get_repo_owner()
            if owner:
                try:
                    return owner.get_repo(repo_name)
                except GithubException as ghe:
                    _handle_ghe(ghe,
                                msg="Unexpected error getting repository %s"
                                % repo_name)

    @staticmethod
    def _repo_find_ref(repo, ref_name):
        """Return a reference or tag if the repo contains it."""
        refs = repo.get_git_refs()
        if '/' in ref_name:
            return refs.get(ref_name)
        else:
            ref_ending = '/%s' % ref_name
            for ref in refs:
                if '/pull/' not in ref.ref and ref.ref.endswith(ref_ending):
                    return ref

    def _get_blueprint(self, repo, tag):
        """Get the deployment blueprint from the specified repo if any; format
        and correct as needed.

        :param repo: the repo containing the blueprint
        """
        if repo and isinstance(repo, github.Repository.Repository) and tag:
            dep_file = None
            try:
                github_ref = self._repo_find_ref(repo, tag)
                if not github_ref:
                    return None

                dep_file = repo.get_file_contents("checkmate.yaml", ref=tag)
            except GithubException as ghe:
                _handle_ghe(ghe,
                            msg="Unexpected error getting blueprint from repo "
                            "%s" % repo.clone_url)

            if dep_file and dep_file.content:
                dep_content = base64.b64decode(dep_file.content)
                dep_content = dep_content.replace("%repo_url%",
                                                  "%s" % str(repo.ssh_url))
                try:
                    ret = yaml.safe_load(dep_content)
                except (yaml.scanner.ScannerError, yaml.parser.ParserError):
                    LOG.warn("Blueprint '%s' has invalid YAML", repo.clone_url)
                    return None

                if "inputs" in ret:
                    del ret['inputs']

                if 'heat_template_version' in ret:
                    parsed = self.parse_hot(ret)
                elif 'blueprint' in ret:
                    parsed = self.parse_blueprint(repo, ret)
                else:
                    LOG.warn("Blueprint '%s' is not in a recognized format",
                             repo.clone_url)
                    return None

                parsed['repo_id'] = repo.id
                parsed['blueprint']['source'] = {
                    'repo-url': repo.ssh_url,
                    'sha': github_ref.object.sha,
                    'ref': github_ref.ref,
                }
                LOG.info("Retrieved blueprint: %s#%s", repo.url, tag)
                return parsed
        return None

    @staticmethod
    def _get_repo_file_contents(repo, filename):
        """Get contents of the given file from the repository.

        :param repo: the repo containing the blueprint
        :param filename: file name
        """
        isinstance(repo, github.Repository.Repository)
        try:
            repo_file = repo.get_file_contents(filename)
            return base64.b64decode(repo_file.content)

        except GithubException:
            return None

    @staticmethod
    def _store(blueprint, tag, target):
        """Store the blueprint in the target memory.

        :param blueprint: the deployment blueprint to store
        """
        if blueprint and tag and isinstance(blueprint, collections.Mapping):
            if "repo_id" not in blueprint:
                LOG.warn("Blueprint id missing in: %s", blueprint)
            else:
                bp_id = "%s:%s" % (blueprint.get("repo_id"), tag)
                del blueprint['repo_id']
                target.update({bp_id: blueprint})


class WebhookRouter(object):

    """Handler for processing web-hook updates from Github.

    Note: Code ported from CrossCheck
    """

    def __init__(self, app, manager):
        self.app = app
        self._manager = manager
        self._logger = logging.getLogger(__name__)
        self._resolved = {}

        # Webhook
        app.route('/webhooks/blueprints', 'POST', self.on_post)

    def on_post(self):
        """Handle a web-hook post from github.

        :throws 500: if the request body could not be parsed
        :throws 403: if the request comes from an unknown Github service
        """
        self._logger.info("Received repo update notification: %s %s",
                          bottle.request.method, bottle.request.url)

        if not self._is_from_our_repo():
            source = (bottle.request.get_header("X-Forwarded-Host") or
                      bottle.request.get_header("X-Remote-Host") or
                      bottle.request.get_header("X-Forwarded-For") or
                      bottle.request.get_header("REMOTE_ADDR"))
            self._logger.warn("Received request from unauthorized host: %s",
                              source)
            bottle.abort(403, "Unauthorized")
        try:
            raw_json = bottle.request.body.read()
            self._logger.debug("Update data: %s", urlparse.unquote(raw_json))
        except StandardError:
            self._logger.error("Error reading repo update post body",
                               exc_info=True)
            bottle.abort(500, "Error reading request body.")
        raw_json = raw_json.split("=")
        if raw_json:
            raw_json = raw_json[1] if len(raw_json) > 1 else raw_json[0]
        else:
            self._logger.warn("No update data from request")
            return
        try:
            updated = json.loads(urlparse.unquote(raw_json))
        except ValueError:
            self._logger.error("Could not parse update payload %s",
                               raw_json, exc_info=True)
            bottle.abort(400, "Invalid payload: Error parsing json document")
        repo = updated.get("repository", {}).get("name")
        owner = updated.get("repository", {}).get("owner", {}).get("name")
        if owner and (self._manager.repo_owner == owner):
            self._logger.info("Updating %s", repo)
            try:
                self._manager.refresh(repo)
            except StandardError:
                msg = "Error refreshing repository %s" % repo
                self._logger.error(msg, exc_info=True)
                bottle.abort(500, "Could not refresh repository: %s" % msg)
            self._logger.info("%s updated", repo)
        else:
            self._logger.warn("Received update from invalid repo owner: %s",
                              owner)
            bottle.abort(403)

    def _is_from_our_repo(self):
        """Check if the call came from a trusted repo.

        :returns: True if the request comes from the manager's configured
                  source api host; False otherwise
        """
        source = (bottle.request.get_header("X-Forwarded-Host") or
                  bottle.request.get_header("X-Remote-Host") or
                  bottle.request.get_header("X-Forwarded-For") or
                  bottle.request.get_header("REMOTE_ADDR"))
        self._logger.debug("Checking source %s against %s", source,
                           self._manager.api_host)
        if source:
            if source not in self._resolved:
                lookup = None
                try:
                    lookup = socket.gethostbyaddr(source)
                except socket.error:
                    self._logger.error("Could not resolve %s", source,
                                       exc_info=True)
                    return False
                if lookup:
                    self._resolved[lookup[0]] = lookup[2]
                    for addr in lookup[2]:
                        self._resolved[addr] = lookup[0]
            src = self._resolved.get(source)
            if hasattr(src, "append"):
                src = self._resolved[src[0]]
            src = urlparse.urlparse(src)
            if src.scheme:
                return self._manager.api_host == src.netloc
            else:
                return self._manager.api_host == src.path
        self._logger.debug("%s was not a match for %s", source,
                           self._manager.api_host)
        return False
