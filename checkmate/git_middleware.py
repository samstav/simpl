import os
import re
import git
from checkmate import wsgi_git_http_backend
from bottle import (
    get,
    post,
    Response,
    auth_basic,
    Bottle,
    request,
    HTTPError
)

GIT_SERVER_APP = Bottle()

expected_environ_list = [
    'wsgi.errors',
    'wsgi.input',
    'wsgi.multiprocess',
    'wsgi.multithread',
    'wsgi.run_once',
    'wsgi.url.scheme',
    'wsgi.version',
    'CONTENT_LENGTH',
    'CONTENT_TYPE',
    'PATH_INFO',
    'QUERY_STRING',
    'REQUEST_METHOD'
]


class GitMiddleware():

    '''Adds support for git http-backend interaction'''

    def __init__(self, app):
        self.app = app

    def __call__(self, e, h):
        if re.search('.git', e['PATH_INFO']):
            print "[["+e['PATH_INFO']+"]]\n"
            pass
        elif e['CONTENT_TYPE'] in [
            'application/x-git-upload-pack-request',
            'application/x-git-receive-pack-request'
        ]:
            pass
        elif e['QUERY_STRING'] in [
            'service=git-upload-pack',
            'service=git-receive-pack'
        ]:
            pass
        else:
            return self.app(e, h)
        try:
            GIT_SERVER_APP.match(e)
            return GIT_SERVER_APP(e, h)
        except HTTPError:
            pass
        return self.app(e, h)


# Route utility routines

def _check_git_auth(user, passwd):
    '''Basic Auth for git back-end (smart HTTP)'''
    # TODO: set this up? (ziad?)
    if user == 'zak':
        return True
    else:
        return False


def _is_git_repo(path):
    if os.path.isfile(os.path.join(path, '.git/config')):
        return True
    return False


def _git_init_deployment(dep_path):
    '''
    Ensure that an existing deployment folder and its sub-directories are
    git-ready.

    IMPORTANT NOTE: Typically, server based repos (ie: github) are 'bare' --
    repos without checkouts. Conversely, working repos for tracking/development
    are usually 'non-bare' -- repos with checkouts. Our deployments need to
    be remote-ready, but with checkouts.  So we'll need non-bare with
    some fine-tuning to work around this atypical setup.

    Here are the steps we employ:

    - We initialize the base root of a deployment folder as a new git repo.
    Contents are added and committed.  Any sub-repos (ie: kitchens) are
    created as submodules to the parent (deployment) repo.
    - Then we implement a special git repo event hook ('post-receive') so that
    whenever there are new updates, the checkout is always automatically reset
    to include those differences and to be current. (aka: HEAD)
    - Since non-bare repos aren't typically allowed for remote branch purposes,
    we set a configuration value in the repo to allow for this non-default
    functionality. (denyCurrentBranch=ignore)
    - We also need to set http.receivepack as True in the default git config.
    - Unless explicitly directed otherwise, any subsequent pushes/pulls to/from
    this repo, the submodules will sustain their original HEAD sha's
    (stable tags).
    '''

    dep_id = os.path.basename(dep_path)

    # check if this is already a repo
    if _is_git_repo(dep_path):
        return
    # init
    print "[init]\n"
    repo = git.Repo.init(dep_path)
    # add submodules
    sms_f = open(dep_path + '/.gitmodules', 'ab+')
    for foldfile in os.listdir(dep_path):
        #repo.git.submodule('add', '--path='+foldfile, '--ignore=dirty')
        if _is_git_repo(os.path.join(dep_path, foldfile)):
            git_buf = open(
                dep_path +
                '/' +
                foldfile +
                '/.git/config',
                'r').read()
            urls = re.findall('url = (.*?)\n', git_buf)
            url = urls[0]
            sms_f.seek(0)
            sms_buf = sms_f.read()
            sms = re.findall('submodule "' + foldfile + '"', sms_buf)
            if len(sms) == 0:
                sms_f.write(
                    '[submodule "' + foldfile + '"]\n' +
                    '  path = ' + foldfile + '\n' +
                    '  url = ' + url + '\n' +
                    '  ignore = dirty\n'
                )
        if os.path.isfile(dep_path + '/' + foldfile):
            repo.git.add(foldfile)
    sms_f.close()
    repo.git.commit(m="init deployment: " + str(dep_id))
    repo.git.submodule('update', '--init', '--recursive')
    repo.git.add('*')
    repo.git.commit(m="add subfolders: " + str(dep_id))
    # add post-receive hook
    hook_path = dep_path + '/.git/hooks/post-receive'
    post_recv_hook = '''#!/bin/bash
    cd ..
    GIT_DIR=".git"
    git reset --hard HEAD
    '''
    fo = open(hook_path, "w")
    fo.write(post_recv_hook)
    fo.close
    os.chmod(dep_path + '/.git/hooks/post-receive', 0o777)
    # config (ignore non-bare when using as remote)
    cw = repo.config_writer()
    cw.set_value('receive', 'denyCurrentBranch', 'ignore')
    # config (allow receivepack for pushes with http-backend)
    cw.set_value('http', 'receivepack', 'true')


def _set_git_environ(environE):
    '''Bottle environment tweaking for git kitchen routes'''
    environ = dict()
    for e_ in expected_environ_list:
        if e_ in environE:
            environ[e_] = environE[e_]
    if 'PATH_INFO' not in environ:
        environ['PATH_INFO'] = ''
    environ['GIT_HTTP_EXPORT_ALL'] = '1'
    path_info = environ['PATH_INFO'][53:]
    dep_id = environ['PATH_INFO'][20:52]
    dep_path = os.environ.get("CHECKMATE_CHEF_LOCAL_PATH",
                              "/var/local/checkmate/deployments"
                              ) + "/" + dep_id
    environ['GIT_PROJECT_ROOT'] = dep_path
    environ['PATH_INFO'] = '/.' + path_info
    if (
        re.search('/info/refs', environ['PATH_INFO']) and
        environ['REQUEST_METHOD'] == 'GET'
    ):
        environ['CONTENT_TYPE'] = ''
    # TODO: (REMOTE_USER) where some authorization could go
    return environ


def _git_route_callback():
    #print "[cb]\n"
    environ = _set_git_environ(dict(request.environ))
    if not os.path.isdir(environ['GIT_PROJECT_ROOT']):
        # TODO: not sure what to do about this
        return
    _git_init_deployment(environ['GIT_PROJECT_ROOT'])
    # beg: debugging
    print str(dict(environ))+"\n"
    # end: debugging
    (status_line, headers, response_body_generator
     ) = wsgi_git_http_backend.wsgi_to_git_http_backend(environ)
    return Response(response_body_generator, status_line, headers=headers)


# Routines for bottle usage


'''
-----------------------------------------------------------------------
Git http-backend Bottle Routes
-----------------------------------------------------------------------

Tested bottle routes:

    (1) git clone http://localhost:8080/deployments/{key}.git
    (2) git push (with local .git/config set from the clone)
    (3) git pull (with local .git/config set from the clone)

Currently, all git http-backend routes initiate with this request type:

    GET /{tenant_id}/deployments/{key}.git/info/refs HTTP/1.1

    PATH_INFO: /deployments/{key}.git/info/refs
    REQUEST_METHOD: GET
    CONTENT_TYPE: text/plain
    QUERY_STRING: service=git-upload-pack
    GIT_HTTP_EXPORT_ALL: 1
    wsgi.version: (1,0)
    wsgi.run_once: False
    wsgi.input: <eventlet.wsgi.Input object>
    wsgi.errors: <open file '<stderr>', mode 'w'>
    wsgi.multiprocess: False, 'wsgi.input': <eventlet.wsgi.Input object>
    wsgi.multithread: True

Currently, all successful git http-backend routes end with this response:

    HTTP/1.1 200 OK
    Content-Type: application/x-git-upload-pack-advertisement
    Pragma: no-cache
    Cache-Control: no-cache, max-age=0, must-revalidate
    Expires: Fri, 01 Jan 1980 00:00:00 GMT

    Note: reponse body data is in binary form.

Git clone request perform a 2nd chained request type:

    POST /{tenant_id}/deployments/{key}.git/git-upload-pack HTTP/1.1

    PATH_INFO: /deployments/{key}.git/git-upload-pack
    REQUEST_METHOD: POST
    CONTENT_TYPE: application/x-git-upload-pack-request
    CONTENT_LENGTH: 174
    GIT_HTTP_EXPORT_ALL: 1
    wsgi.version: (1,0)
    wsgi.run_once: False
    wsgi.input: <eventlet.wsgi.Input object>
    wsgi.errors: <open file '<stderr>', mode 'w'>
    wsgi.multiprocess: False
    wsgi.multithread: True

Git push request perform a 2nd chained request type:

    GET /{tenant_id}/deployments/{key}.git/HEAD HTTP/1.1

    PATH_INFO: '/ba3ce9f785f8438c9c8bd6a7cf1a7569.git/HEAD'
    REQUEST_METHOD': GET
    CONTENT_TYPE: text/plain
    GIT_HTTP_EXPORT_ALL: 1
    wsgi.version: (1,0)
    wsgi.run_once: False
    wsgi.input: <eventlet.wsgi.Input object>
    wsgi.errors: <open file '<stderr>', mode 'w'>
    wsgi.multiprocess: False
    wsgi.multithread: True

No other request or reponse environ/header settings are given
to/by gitHttpBackend.

    ie, not observed:

      # X-Auth-Token: 0d6f2078-55f9-4a7c-97c5-7acb57b1c663
      # Host: checkmate.rackspace.com
      # Content-Type: application/json

    Note-1: Tokens aren't observsed currently. We may want to add
    this ability however.
    Note-2: Mixed case 'Content-Type' isn't used. Upper case
    'CONTENT_TYPE' is.
    Note-3: Bottle sends alot of environ settings. Some are
    causing conflicts with gitHttpBackend. Attempts have been made
    to filter out only the absolutely necessary ones.
    This is why 'Host', etc. aren't seen.

-----------------------------------------------------------------------
'''


# Bottle routes

@GIT_SERVER_APP.get("/<tenant_id>/deployments/<url:re:.+>")
#@auth_basic(_check_git_auth) #basic auth
def git_route_get(tenant_id, url):
    return _git_route_callback()


@GIT_SERVER_APP.post("/<tenant_id>/deployments/<url:re:.+>")
#@auth_basic(_check_git_auth) #basic auth
def git_route_post(tenant_id, url):
    return _git_route_callback()
