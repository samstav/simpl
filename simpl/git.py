"""Simpl git utilities.

Wraps many shellouts to git creating
easy-to-handle, pythonic results.

Tested against:

    git 2.1.2

"""

import atexit
import errno
import logging
import os
import pipes
import shutil
import tempfile

from simpl import exceptions
from simpl.utils import shell

LOG = logging.getLogger(__name__)
#: Minimum recommended git version
MIN_GIT_VERSION = (1, 9)

def execute_git_command(command, repo_dir=None):
    """Execute a git command and return the output.

    Catches CalledProcessErrors and OSErrors, wrapping them
    in a more useful SimplGitCommandError.

    Raises SimplCommandGitError if the command fails. Returncode and
    output from the attempt can be found in the SimplGitCommandError
    attributes.
    """
    try:
        output = shell.execute(command, cwd=repo_dir)
    except exceptions.SimplCalledProcessError as err:
        raise exceptions.SimplGitCommandError(err.returncode, err.cmd,
                                              output=err.output)
    except OSError as err:
        # OSError's errno *is not* the returncode
        raise exceptions.SimplGitCommandError(
            127, command, output=repr(err), oserror=err)
    else:
        return output


def git_init(repo_dir):
    """Run git init in `repo_dir'."""
    return execute_git_command('git init', repo_dir=repo_dir)


def git_clone(target_dir, repo_location, branch_or_tag=None, verbose=True):
    """Clone repo at repo_location to target_dir and checkout branch_or_tag.

    If branch_or_tag is not specified, the HEAD of the primary
    branch of the cloned repo is checked out.
    """
    target_dir = pipes.quote(target_dir)
    command = 'git clone'
    if verbose:
        command = "%s --verbose" % command
    command = '%s %s %s' % (command, repo_location, target_dir)
    if branch_or_tag:
        command = "%s --branch %s" % (command, branch_or_tag)
    return execute_git_command(command)


def git_tag(repo_dir, tagname, message=None, force=True):
    """Create an annotated tag at the current head."""
    message = pipes.quote(message or "%s" % tagname)
    command = 'git tag --annotate --message %s' % message
    if force:
        command = "%s --force" % command
    # append the tag as the final arg
    command = "%s %s" % (command, pipes.quote(tagname))
    return execute_git_command(command, repo_dir=repo_dir)


def git_list_config(repo_dir):
    """Return a list of the git configuration."""
    command = 'git config --list'
    raw = execute_git_command(command, repo_dir=repo_dir).splitlines()
    output = {key: val for key, val in
              [cfg.split('=', 1) for cfg in raw]}
    # TODO(sam): maybe turn this into more easily navigable
    # nested dicts?
    # e.g. {'alias': {'branches': ..., 'remotes': ...}}
    return output


def git_list_tags(repo_dir, with_messages=False):
    """Return a list of git tags for the git repo in `repo_dir'."""
    command = 'git tag -l'
    if with_messages:
        command = "%s -n1" % command
    raw = execute_git_command(command, repo_dir=repo_dir).splitlines()
    output = [l.strip() for l in raw if l.strip()]
    if with_messages:
        output = [tuple(j.strip() for j in line.split(None, 1))
                  for line in output]
    return output


def git_list_branches(repo_dir):
    """Return a list of git branches for the git repo in 'repo_dir'.

    Returns
        [
            {'branch': <branchname,
             'commit': <commit_hash>,
             'message': <commit message>},
            {...},
        ]
    """
    command = "git branch --remotes --all --verbose --no-abbrev"
    output = execute_git_command(command, repo_dir=repo_dir).splitlines()
    # remove nullish lines
    lines = [l.strip() for l in output if l.strip()]
    # find the * current branch
    try:
        current_branch = [l for l in lines if l.startswith('* ')][0]
    except IndexError:
        current_branch = None
    if current_branch:
        lines.remove(current_branch)
        current_branch = current_branch.replace('* ', '', 1)
        lines.insert(0, current_branch)
    # <branch> <hash> <commit_message>
    # make a list of lists with clean elements of equal length
    breakout = [k.split(None, 2) for k in lines]
    # remove any strange hashless outliers
    breakout = [k for k in breakout if len(k[1]) == 40]
    headers = ['branch', 'commit', 'message']
    return [dict(zip(headers, vals)) for vals in breakout]


def git_ls_remote(repo_dir, remote='origin', refs=None):
    """Run git ls-remote.

    'remote' can be a remote ref in a local repo, e.g. origin,
    or url of a remote repository.
    """
    command = 'git ls-remote %s' % remote
    if refs:
        if isinstance(refs, list):
            refs = " ".join(refs)
        command = "%s %s" % (command, refs)
    raw = execute_git_command(command, repo_dir=repo_dir).splitlines()
    output = [l.strip() for l in raw if l.strip()
              and not l.strip().lower().startswith('from ')]
    output = [tuple(j.strip() for j in line.split(None, 1))
              for line in output]
    return output


def git_branch(repo_dir, branch_name, start_point, force=True):
    """Create a new branch like `git branch <branch_name> <start_point>`."""
    command = 'git branch'
    if force:
        command = "%s --force" % command
    command = "%s %s %s" % (command, branch_name, start_point)
    return execute_git_command(command, repo_dir=repo_dir)


def git_checkout(repo_dir, ref):
    """Do a git checkout of `ref' in `repo_dir'."""
    return execute_git_command('git checkout --force %s'
                               % ref, repo_dir=repo_dir)


def git_fetch(repo_dir, remote="origin", refspec=None, verbose=False):
    """Do a git fetch of `refspec' in `repo_dir'."""
    command = 'git fetch --update-head-ok --tags'
    if verbose:
        command = "%s --verbose" % command
    if refspec:
        command = "%s %s %s" % (command, remote, pipes.quote(refspec))
    else:
        command = "%s %s" % (command, remote)
    return execute_git_command(command, repo_dir=repo_dir)


def git_pull(repo_dir, remote="origin", ref=None):
    """Do a git pull of `ref' from `remote'."""
    command = 'git pull --update-head-ok %s' % remote
    if ref:
        command = "%s %s" % (command, pipes.quote(ref))
    return execute_git_command(command, repo_dir=repo_dir)


def git_commit(repo_dir, message=None, amend=False, stage=True):
    """Commit any changes, optionally staging all changes beforehand."""
    if stage:
        git_add_all(repo_dir)
    command = "git commit --allow-empty"
    if amend:
        command = "%s --amend" % command
        if not message:
            command = "%s --no-edit" % command
    if message:
        command = "%s --message %s" % (command, pipes.quote(message))
    elif not amend:
        # if not amending and no message, allow an empty message
        command = "%s --message='' --allow-empty-message" % command
    return execute_git_command(command, repo_dir=repo_dir)


def git_ls_tree(repo_dir, treeish='HEAD'):
    """Run git ls-tree."""
    command = "git ls-tree -r --full-tree %s" % treeish
    raw = execute_git_command(command, repo_dir=repo_dir).splitlines()
    output = [l.strip() for l in raw if l.strip()]
    # <mode> <type> <object> <file>
    # make a list of lists with clean elements of equal length
    breakout = [k.split(None, 3) for k in output]
    headers = ['mode', 'type', 'object', 'file']
    return [dict(zip(headers, vals)) for vals in breakout]


def git_add_all(repo_dir):
    """Stage all changes in the working tree."""
    return execute_git_command('git add --all', repo_dir=repo_dir)


def git_status(repo_dir):
    """Get the working tree status."""
    return execute_git_command('git status', repo_dir=repo_dir)


def git_head_commit(repo_dir):
    """Return the current commit hash head points to."""
    return execute_git_command(
        'git rev-parse head', repo_dir=repo_dir)


def is_git_repo(repo_dir):
    """Return True if the directory is inside a git repo."""
    try:
        execute_git_command('git rev-parse', repo_dir=repo_dir)
    except exceptions.SimplGitCommandError:
        return False
    else:
        return True


class GitRepo(object):

    """Wrapper on a git repository.

    Git command failures raise SimplGitCommandException which includes
    attributes about the returncode, error output, etc.

    Unless 'repo_dir' is already an initialized git repository,
    the first classmethod you will need to run will probably be
    self.init() or self.clone(), both of which return an instance
    of GitRepo.
    """

    def __init__(self, repo_dir=None):
        """Initialize wrapper and check for existence of dir.

        The init() and clone() classmethods are common ways of
        initializing an instance of GitRepo.

        Defaults to current working directory if repo_dir is not supplied.

        If the repo_dir is not a git repository, SimplGitNotRepo is raised.
        """
        repo_dir = repo_dir or os.getcwd()
        repo_dir = os.path.abspath(
            os.path.expanduser(os.path.normpath(repo_dir)))
        if not os.path.isdir(repo_dir):
            raise OSError(errno.ENOENT, "No such directory")
        if not is_git_repo(repo_dir):
            raise exceptions.SimplGitNotRepo(
                "%s is not [in] a git repo." % repo_dir)
        self.repo_dir = repo_dir

    @classmethod
    def clone(cls, repo_location, repo_dir=None, branch_or_tag=None):
        """Clone repo at repo_location into repo_dir and checkout branch_or_tag.

        Defaults into current working directory if repo_dir is not supplied.

        If branch_or_tag is not specified, the HEAD of the primary
        branch of the cloned repo is checked out.
        """
        repo_dir = repo_dir or os.getcwd()
        response = git_clone(repo_dir, repo_location,
                             branch_or_tag=branch_or_tag)
        # assuming no errors
        return cls(repo_dir)

    @classmethod
    def init(cls, repo_dir=None):
        """Run `git init` in the repo_dir.

        Defaults to current working directory if repo_dir is not supplied.
        """
        repo_dir = repo_dir or os.getcwd()
        response = git_init(repo_dir)
        return cls(repo_dir)

    @property
    def head(self):
        """Return the current commit hash."""
        return git_head_commit(self.repo_dir)

    def status(self):
        """Get the working tree status."""
        return git_status(self.repo_dir)

    def tag(self, tagname, message=None, force=True):
        """Create an annotated tag."""
        return git_tag(self.repo_dir, tagname, message=message, force=force)

    def ls(self):
        """Return a list of *all* files & dirs in the repo.

        Think of this as a recursive `ls` command from the root of the repo.
        """
        tree = self.ls_tree()
        return [t.get('file') for t in tree if t.get('file')]

    def ls_tree(self, treeish='HEAD'):
        """List *all* files/dirs in the repo at ref 'treeish'.

        Returns
            [
                {'mode': <file permissions>,
                 'type': <git object type>, # blob, tree, commit or tag
                 'object': <object hash>,
                 'file': <path/to/file.py>},
                {...},
            ]
        """
        return git_ls_tree(self.repo_dir, treeish=treeish)

    def ls_remote(self, remote='origin', refs=None):
        """Return a list of refs for the given remote.

        Returns a list of (hash, ref) tuples
            [(<hash1>, <ref1>), (<hash2>, <ref2>)]
        """
        return git_ls_remote(
            self.repo_dir, remote=remote, refs=refs)

    def list_tags(self, with_messages=False):
        """Return a list of git tags for the git repo.

        If 'with_messages' is True, returns
        a list of (tag, message) tuples
            [(<tag1>, <message1>), (<tag2>, <message2>)]
        """
        return git_list_tags(
            self.repo_dir, with_messages=with_messages)

    def list_config(self):
        """Return a dictionary of the git config."""
        return git_list_config(self.repo_dir)

    def list_branches(self):
        """Return a list of dicts, describing the branches.

        Returns
            [
                {'branch': <branchname,
                 'commit': <commit_hash>,
                 'message': <commit message>},
                {...},
            ]
        """
        return git_list_branches(self.repo_dir)

    def branch(self, branch_name, start_point, force=True):
        """Create branch as in `git branch <branch_name> <start_point>`."""
        return git_branch(
            self.repo_dir, branch_name, start_point, force=force)

    def checkout(self, ref):
        """Do a git checkout of `ref'."""
        return git_checkout(self.repo_dir, ref)

    def fetch(self, remote="origin", refspec=None, verbose=False):
        """Do a git fetch of `refspec'."""
        return git_fetch(self.repo_dir, remote=remote,
                         refspec=refspec, verbose=verbose)

    def pull(self, remote="origin", ref=None):
        """Do a git pull of `ref' from `remote'."""
        return git_pull(self.repo_dir, remote=remote, ref=ref)

    def add_all(self):
        """Stage all changes in the working tree."""
        return git_add_all(self.repo_dir)

    def commit(self, message=None, amend=False, stage=True):
        """Commit any changes, optionally staging all changes beforehand."""
        return git_commit(self.repo_dir, message=message,
                          amend=amend, stage=stage)


def resolve_git_reference(gitrepo, ref, remote='origin'):
    """Try to find a revision (commit hash) that corresponds to 'ref'.

    Even if 'ref' is not fetched, use a combination of fetch and/or
    ls-remote to discover it and check it out.

    Note:
        stole these ideas from opscode chef, chef/provider/git.rb
    """
    ls_refs = dict(gitrepo.ls_remote(remote=remote, refs='%s*' % ref))
    # switch so they are keyed off of refs
    ls_refs = dict(zip(ls_refs.values(), ls_refs.keys()))
    if ref == 'HEAD':
        revision = ls_refs['HEAD']
    else:
        matching_refs = [
            'refs/tags/%s^{}' % ref,
            'refs/heads/%s^{}' % ref,
            '%s^{}',
            'refs/tags/%s',
            'refs/heads/%s',
            ref,
        ]
        for _ref in matching_refs:
            if _ref in ls_refs:
                revision = ls_refs[_ref]
                break
        else:
            raise ValueError("No revisions matched for ref %s." % ref)
    return revision


def tmp_clone(repo_location, ref=None, delete=True):
    """Clone repo from repo_location into a temp dir.

    If 'ref' is specified, check it out or fail.
    Return a GitRepo in a tempdir.

    If delete is True (default), the tempdir is scheduled for deletion
    (when the process exits) through an exit function registered with
    the atexit module.
    """
    target = tempfile.mkdtemp()
    if delete:
        atexit.register(shutil.rmtree, target)
    repo = GitRepo.clone(repo_location, repo_dir=target)
    # now resolve the ref
    if ref:
        ref = ref.strip()  # ensure no leading/trailing whitespace
        try:
            repo.fetch(refspec=ref)
        except exceptions.SimplGitCommandError:
            revision = resolve_git_reference(repo, ref)
        else:
            revision = ref
        branchname = 'temp_%s_branch' % ref
        repo.branch(branchname, revision)
        repo.checkout(branchname)
    return repo
