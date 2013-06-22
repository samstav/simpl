'''
All the git things (git calls, repo management, configs, etc...)
'''
import errno
import os
import re

import git


def _is_git_repo(path):
    if os.path.isfile(os.path.join(path, '.git/config')):
        return True
    return False


def _find_unregistered_submodules(dep_path):
    '''Loops through directory and finds unregistered submodules

    :param path: a path to check
    :returns: dict of paths and submodule urls

    Note: will return an empty dict in cases where the directory does not exist
    or is not a valid git repo
    '''
    if not os.path.exists(dep_path):
        return {}

    try:
        repo = git.Repo(dep_path)
        existing_submodule_paths = [s.path for s in repo.submodules]
    except git.BadObject:
        existing_submodule_paths = []
    except git.InvalidGitRepositoryError:
        existing_submodule_paths = []

    unregistered_submodules = {}
    directory_entries = os.listdir(dep_path)
    if directory_entries:
        for dir_entry in directory_entries:
            sub_folder = os.path.join(dep_path, dir_entry)
            if _is_git_repo(sub_folder):
                sub_folder_git_config = os.path.join(dep_path, dir_entry,
                                                     '.git', 'config')
                git_buf = open(sub_folder_git_config, 'r').read()
                urls = re.findall('url = (.*?)\n', git_buf)
                url = urls[0]
                if dir_entry not in existing_submodule_paths:
                    unregistered_submodules[dir_entry] = url

    return unregistered_submodules


def _add_submodules_to_config(dep_path, submodules_to_add):
    '''Adds list of path/urls to existing repo'''
    with open(os.path.join(dep_path, '.gitmodules'), 'ab+') as sms_f:
        for path, url in submodules_to_add.items():
            sms_f.write(
                '[submodule "%s"]\n'
                '\tpath = %s\n'
                '\turl = %s\n'
                '\tignore = dirty\n' % (path, path, url)
            )


def add_post_receive_hook(dep_path):
    '''implement a special git repo event hook ('post-receive').

    Whenever there are new updates, the checkout is always automatically reset
    to include those differences and to be current. (aka: HEAD)
    '''
    hook_path = os.path.join(dep_path, '.git', 'hooks', 'post-receive')
    post_recv_hook = '''#!/bin/bash
cd ..
GIT_DIR=".git"
git reset --hard HEAD
'''
    with open(hook_path, "w") as hook_file_w:
        hook_file_w.write(post_recv_hook)
    os.chmod(hook_path, 0o777)
    # config (ignore non-bare when using as remote)
    repo = git.Repo(dep_path)
    writer = repo.config_writer()
    writer.set_value('receive', 'denyCurrentBranch', 'ignore')
    # config (allow receivepack for pushes with http-backend)
    writer.set_value('http', 'receivepack', 'true')


def init_deployment_repo(dep_path):
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
    if not os.path.exists(dep_path):
        raise OSError(errno.ENOENT, "No such file or directory")

    # check if this is already a repo
    if _is_git_repo(dep_path):
        return
    repo = git.Repo.init(dep_path)

    # find submodules to add
    submodules_to_add = _find_unregistered_submodules(dep_path)

    # find files or folders to add
    entries_to_add = repo.git.ls_files('--exclude-standard', '--others')

    if entries_to_add or submodules_to_add:
        if submodules_to_add:
            _add_submodules_to_config(dep_path, submodules_to_add)
        repo.git.add('*')
        repo.git.commit(m="Initial Commit")

    add_post_receive_hook(dep_path)
