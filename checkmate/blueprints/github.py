'''
GitHub Classes

Manager for caching GitHub blueprints
Router for responding to webhooks

'''
from __future__ import absolute_import

import base64
import collections
import json
import logging
import os
import time
from urlparse import urlparse, unquote
import yaml

#pylint: disable=E0611
from bottle import abort, request
import eventlet
from eventlet.green import threading
from eventlet.green import socket
from eventlet.greenpool import GreenPile
github = eventlet.import_patched('github')  # pylint: disable=C0103
from github import GithubException

from checkmate import utils
from checkmate.base import ManagerBase
from checkmate.common import caching

LOG = logging.getLogger(__name__)
DEFAULT_CACHE_TIMEOUT = 10 * 60
BLUEPRINT_CACHE = {}


def _handle_ghe(ghe, msg="Unexpected Github error"):
    ''' Ignore a 404 response from github but log other errors '''
    if ghe.status != 404:
        LOG.warn(msg or "", exc_info=True)


class GitHubManager(ManagerBase):
    ''' Manage the catalog of "known good" blueprints '''

    def __init__(self, drivers, config):
        '''

        Config params used
        :github_api_base: Base uri for the github api hosting the
                                blueprint repository (required)
        :branch: tag/branch/ref to pull as the "supported" version of
                                the blueprint; defaults to 'master'
        :repo_org: the organization owning the blueprint repositories
        :cache_dir: directory to write cached blueprint data to
        '''
        ManagerBase.__init__(self, drivers)
        self._github_api_base = config.github_api
        if self._github_api_base:
            self._github = github.Github(base_url=self._github_api_base)
            self._api_host = urlparse(self._github_api_base).netloc
        self._repo_org = config.organization
        self._ref = config.ref
        self._cache_root = config.cache_dir or os.path.dirname(__file__)
        self._cache_file = os.path.join(self._cache_root, ".blueprint_cache")
        self._blueprints = {}
        self._preview_ref = config.preview_ref
        self._preview_tenants = config.preview_tenants
        self._group_refs = config.group_refs or {}
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
        self.load_cache()

    def get_tenant_tag(self, tenant_id, tenant_auth_groups):
        '''Find the tag to return for this tenant

        If the tenant is explicitely called out in preview-refs, then use the
        preview ref.
        If the tenant is in a group that has a tag, then return that ref (first
        match wins).
        Otherwise, default to ref.
        Finally, if none specified, use 'master'
        '''
        assert tenant_id, "must provide a tenant-id"

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
        ''' :return: source Github api host (not url) '''
        return self._api_host

    @property
    def repo_owner(self):
        ''' :return: repository owner '''
        return self._repo_org

    def get_blueprints(self, tenant_id=None, offset=0, limit=100, details=0):
        '''
        Return an abbreviated list of known deployment blueprints

        :param offset: pagination start
        :param limit: pagination length
        '''
        tag = self.get_tenant_tag(tenant_id, request.context.roles)
        if not self._blueprints:
            # Wait for refresh to complete (block)
            if self.background is None:
                self.start_background_refresh()
            try:
                LOG.warning("Call to GET /blueprints blocking on refresh")
                self.refresh_lock.acquire()
            finally:
                self.refresh_lock.release()

        if not tag:
            return
        if offset is None:
            offset = 0
        if limit is None:
            limit = 100

        preview = self._preview_tenants and tenant_id in self._preview_tenants
        results = self._get_blueprint_list_by_tag(tag, include_preview=preview)

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

        if (self.background is None and
                time.time() - self.last_refresh > DEFAULT_CACHE_TIMEOUT):
            self.start_background_refresh()

        return {
            'collection-count': len(results),
            '_links': {},
            'results': results,
        }

    @caching.MemorizeMethod(store=BLUEPRINT_CACHE, timeout=60)
    def _get_blueprint_list_by_tag(self, tag, include_preview=False):
        '''Filter blueprints to show

        :param tag: git to include
        :param include_preview: if preview blueprints should be included
        :returns: filtered blueprints dict
        '''
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
        '''
        :param blueprint_id: the deployment blueprint identifier
        :returns: the specified deployment blueprint
        '''
        if not self._blueprints:
            self.refresh_all()

        return self._blueprints.get(str(blueprint_id))

    def refresh(self, repo_name):
        '''
        Get updated deployment blueprint information from the specified
        github repository

        :param repo_name: the name of the github repository containing the
                          the blueprint
        '''
        self._refresh_from_repo(self._get_repo(repo_name))
        self._update_cache()

    def load_cache(self):
        '''pre-seed with existing cache if any in case we can't connect to the
        repo'''
        if os.path.exists(self._cache_file):
            try:
                with open(self._cache_file, 'r') as cache:
                    self._blueprints = json.load(cache)
            except IOError:
                LOG.warn("Could not load cache file", exc_info=True)

    def background_refresh(self):
        '''Called by background thread to start a refresh'''
        with self.refresh_lock:
            try:
                self.refresh_all()
                LOG.debug("Background refresh complete")
            finally:
                self.background = None

    def start_background_refresh(self):
        '''Initiate a background refresh of all blueprints'''
        if self.background is None and self.start_refresh_lock.acquire(False):
            try:
                self.background = threading.Thread(
                    target=self.background_refresh)
                self.background.setDaemon(False)
                LOG.debug("Refreshing blueprint cache")
                self.background.start()
            except StandardError:
                self.background = None
                LOG.error("Error initiating refresh", exc_info=True)
                raise
            finally:
                self.start_refresh_lock.release()
        else:
            LOG.debug("Already refreshing")

    def refresh_all(self):
        '''
        Get all deployment blueprints from the repositories owned by
        :self.repo_org:
        '''
        org = self._get_repo_owner()
        if not org:
            LOG.error("No user or group matching %s", self._repo_org)
            return
        refs = [self._ref, self._preview_ref] + self._group_refs.values()
        refs = list(set([ref for ref in refs if ref]))
        repos = org.get_repos()

        pool = GreenPile()
        for ref in refs:
            for repo in repos:
                pool.spawn(self._get_blueprint, repo, ref)

        fresh = {}
        for ref in refs:
            for repo, result in zip(repos, pool):
                self._store(result, ref, fresh)

        self._blueprints = fresh
        self._update_cache()
        self.last_refresh = time.time()

    def _get_repo_owner(self):
        ''' Return the user or organization owning the repo '''
        if self._repo_org:
            try:
                return self._github.get_organization(self._repo_org)
            except GithubException:
                LOG.info("Could not retrieve org information for %s; trying "
                         "users", self._repo_org, exc_info=True)
                try:
                    return self._github.get_user(self._repo_org)
                except GithubException:
                    LOG.warn("Could not find user %s.", self._repo_org)

    def _update_cache(self):
        ''' Write the current blueprint map to local disk '''
        if not os.path.exists(self._cache_root):
            try:
                os.makedirs(self._cache_root, 0766)
            except OSError:
                LOG.warn("Could not create cache directory", exc_info=True)
                return
        with open(self._cache_file, 'w') as cache:
            try:
                cache.write(json.dumps(self._blueprints))
            except IOError:
                LOG.warn("Error updating disk cache", exc_info=True)

    def _refresh_from_repo(self, repo):
        '''
        Store/update blueprint info from the specified repository

        :param repo: the repository containing blueprint data or :None:
        '''
        if repo:
            rid = "%s:%s" % (str(repo.id), self._ref)
            if rid in self._blueprints:
                del self._blueprints[rid]
            self._store(self._get_blueprint(repo, self._ref), self._ref,
                        self._blueprints)

            if not self._preview_ref:
                return

            rid = "%s:%s" % (str(repo.id), self._preview_ref)
            if rid in self._blueprints:
                del self._blueprints[rid]
            self._store(self._get_blueprint(repo, self._preview_ref),
                        self._preview_ref, self._blueprints)

    def _get_repo(self, repo_name):
        '''Return the specified github repo

        :param repo_name: the repo to get; must belong to :self.repo_org:
        '''
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
    def _repo_contains_ref(repo, ref_name):
        '''Check if a repo contains a tag or reference'''
        if '/' in ref_name:
            return ref_name in repo.get_git_refs()
        else:
            return any(ref for ref in repo.get_git_refs()
                       if ('/pull/' not in ref.ref and
                           ref.ref.endswith('/%s' % ref_name)))

        return False

    def _get_blueprint(self, repo, tag):
        '''
        Get the deployment blueprint from the specified repo if any; format
        and correct as needed

        :param repo: the repo containing the blueprint
        '''
        if repo and isinstance(repo, github.Repository.Repository) and tag:
            dep_file = None
            try:
                if not self._repo_contains_ref(repo, tag):
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
                                                  "%s#%s" % (
                                                  str(repo.clone_url), tag))
                ret = yaml.safe_load(dep_content)
                if "inputs" in ret:
                    del ret['inputs']

                if 'documentation' not in ret['blueprint']:
                    ret['blueprint']['documentation'] = {}

                # if blueprint does not contain abstract field, check repo for
                # abstract.md file
                self._inline_documentation_field(ret['blueprint'], repo,
                                                 'abstract')

                # if blueprint does not contain instructions field, check repo
                # for instructions.md
                self._inline_documentation_field(ret['blueprint'], repo,
                                                 'instructions')

                # if blueprint does not contain guide field, check repo for
                # guide.md
                self._inline_documentation_field(ret['blueprint'], repo,
                                                 'guide')

                ret['repo_id'] = repo.id
                return ret
        return None

    def _inline_documentation_field(self, blueprint, repo, doc_field):
        '''
        Set documentation field (documenation.abstract/instructions/guide
        etc... field if they are not present in the blueprint and respective
        abstract.md/instructions.md/guide.md files exists in repo

        :param blueprint: the blueprint blueprint
        :param repo: the repo containing the blueprint
        :param doc_field: documentation field in the blueprint
        '''

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
            file_content = self._get_repo_file_contents(repo,  file_name)
            if file_content:
                blueprint['documentation'][doc_field] = file_content

    @staticmethod
    def _get_repo_file_contents(repo, filename):
        '''
        Get contents of the given file from the repository

        :param repo: the repo containing the blueprint
        :param filename: file name
        '''
        isinstance(repo, github.Repository.Repository)
        try:
            repo_file = repo.get_file_contents(filename)
            return base64.b64decode(repo_file.content)

        except GithubException:
            return None

    @staticmethod
    def _store(blueprint, tag, target):
        '''
        Store the blueprint in the target memory

        :param blueprint: the deployment blueprint to store
        '''

        if blueprint and tag and isinstance(blueprint, collections.Mapping):
            if "repo_id" not in blueprint:
                LOG.warn("Deployment blueprint id missing in:\n%s", blueprint)
            else:
                bp_id = "%s:%s" % (blueprint.get("repo_id"), tag)
                del blueprint['repo_id']
                target.update({bp_id: blueprint})


class WebhookRouter(object):
    '''
    Handler for processing web-hook updates from Github

    Code ported from CrossCheck
    '''

    def __init__(self, app, manager):
        self.app = app
        self._manager = manager
        self._logger = logging.getLogger(__name__)
        self._resolved = {}

        # Webhook
        # TODO(zns): change path to somethng blueprint-specific
        app.route('/webhook', 'POST', self.on_post)  # deprecate
        app.route('/blueprints/webhook', 'POST', self.on_post)

    def on_post(self):
        """
        Handle a web-hook post from github
        :throws 500: if the request body could not
                be parsed
        :throws 403: if the request comes from
                an unknown Github service
        """

        self._logger.info("Received repo update notification %s",
                          request.headers)

        if not self._is_from_our_repo(request):
            self._logger.warn("Received request from invalid host '%s'!",
                              request.headers)
            abort(403, "Unauthorized")
        try:
            raw_json = request.body.read()
            self._logger.debug("Update data: %s", unquote(raw_json))
        except StandardError:
            self._logger.error("Error reading repo update post body",
                               exc_info=True)
            abort(500, "Error reading request body.")
        raw_json = raw_json.split("=")
        if raw_json:
            raw_json = raw_json[1] if len(raw_json) > 1 else raw_json[0]
        else:
            self._logger.warn("No update data from request")
            return
        try:
            updated = json.loads(unquote(raw_json))
        except ValueError:
            self._logger.error("Could not parse update payload %s",
                               raw_json, exc_info=True)
            abort(400, "Invalid payload: Error parsing json document")
        repo = updated.get("repository", {}).get("name")
        owner = updated.get("repository", {}).get("owner", {}).get("name")
        if owner and (self._manager.repo_owner == owner):
            self._logger.info("Updating %s", repo)
            try:
                self._manager.refresh(repo)
            except StandardError:
                msg = "Error refreshing repository %s" % repo
                self._logger.error(msg, exc_info=True)
                abort(500, "Could not refresh repository: %s" % msg)
            self._logger.info("%s updated", repo)
        else:
            self._logger.warn("Received update from invalid repo owner: %s",
                              owner)
            abort(403)

    def _is_from_our_repo(self, request):
        """
        :param request: the http request
        :returns: True if the request comes from the manager's configured
                  source api host; False otherwise
        """
        source = (request.get_header("X-Forwarded-Host") or
                  request.get_header("X-Remote-Host") or
                  request.get_header("X-Forwarded-For") or
                  request.get_header("REMOTE_ADDR"))
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
            src = urlparse(src)
            if src.scheme:
                return self._manager.api_host == src.netloc
            else:
                return self._manager.api_host == src.path
        self._logger.debug("%s was not a match for %s", source,
                           self._manager.api_host)
        return False
