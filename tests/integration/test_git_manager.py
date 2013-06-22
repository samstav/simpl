# pylint: disable=C0103,C0111,R0903,R0904,W0212,W0232
import os
import shutil
import unittest
import uuid

import git
import mock

from checkmate.git import manager

TEST_PATH = '/tmp/checkmate/test'


class TestGitPython(unittest.TestCase):
    '''Test that GitPython works as we expect'''
    def setUp(self):
        self.repo_path = os.path.join(TEST_PATH, uuid.uuid4().hex)
        os.makedirs(self.repo_path)

    def tearDown(self):
        shutil.rmtree(self.repo_path)

    def test_git_repo_init_blank_dir(self):
        git.Repo.init(self.repo_path)
        git_path = os.path.join(self.repo_path, '.git')
        self.assertTrue(os.path.isdir(git_path))
        config_path = os.path.join(self.repo_path, '.git', 'config')
        self.assertTrue(os.path.isfile(config_path))

    def test_git_add_start_adds_dirs(self):
        subdir_path = os.path.join(self.repo_path, 'dir')
        os.makedirs(subdir_path)
        with open(os.path.join(subdir_path, 'readme'), 'w') as readme:
            readme.write('.')
        repo = git.Repo.init(self.repo_path)
        repo.git.add('*')
        repo.git.commit(m="Initial Commit")
        self.assertTrue(repo.git.ls_files(), 'dir\\readme')


class TestGitPythonSubmodules(unittest.TestCase):
    '''Test that GitPython works as we expect with submodules'''
    def setUp(self):
        self.repo_path = os.path.join(TEST_PATH, uuid.uuid4().hex)
        os.makedirs(self.repo_path)

        self.submodule_path = os.path.join(self.repo_path, 'subthing')
        os.makedirs(self.submodule_path)
        subrepo = git.Repo.init(self.submodule_path)
        self.submodule_git_path = os.path.join(self.submodule_path, '.git')
        self.assertTrue(os.path.isdir(self.submodule_git_path))
        subrepo.create_remote('origin', 'http://localhost/repo.git')

        self.submodule_path2 = os.path.join(self.repo_path, 'subthing2')
        os.makedirs(self.submodule_path2)
        subrepo2 = git.Repo.init(self.submodule_path2)
        self.submodule_git_path2 = os.path.join(self.submodule_path2, '.git')
        self.assertTrue(os.path.isdir(self.submodule_git_path2))
        subrepo2.create_remote('origin', 'http://localhost/repo2.git')

    def tearDown(self):
        shutil.rmtree(self.repo_path)

    def test_git_repo_add_submodule(self):
        '''Confirm .gitmodule change + commit adds submodule'''
        repo = git.Repo.init(self.repo_path)
        submodules = {'subthing': 'https://localhost/repo.git'}
        manager._add_submodules_to_config(self.repo_path, submodules)
        repo.git.add('.gitmodules')
        repo.git.commit(m="add subfolders")
        expected = ('[submodule "%s"]\n\tpath = %s\n\turl = %s\n'
                    '\tignore = dirty\n' % ('subthing', 'subthing',
                    'https://localhost/repo.git'))
        config = open(os.path.join(self.repo_path, '.gitmodules')).read()
        self.assertEqual(config, expected)

    def test_git_repo_add_submodules(self):
        '''Test that adding submodules with git.add works mor than once'''
        repo = git.Repo.init(self.repo_path)

        submodules = {'subthing': 'https://localhost/repo.git'}
        manager._add_submodules_to_config(self.repo_path,
                                                              submodules)
        repo.git.add('.gitmodules')
        repo.git.commit(m="add subfolder1")

        submodules = {'subthing2': 'https://localhost/repo2.git'}
        manager._add_submodules_to_config(self.repo_path,
                                                              submodules)
        repo.git.add('.gitmodules')
        repo.git.commit(m="add subfolder2")
        expected = ('[submodule "%s"]\n\tpath = %s\n\turl = %s\n'
                    '\tignore = dirty\n' % ('subthing', 'subthing',
                    'https://localhost/repo.git'))
        expected2 = ('[submodule "%s"]\n\tpath = %s\n\turl = %s\n'
                     '\tignore = dirty\n' % ('subthing2', 'subthing2',
                     'https://localhost/repo2.git'))
        config = open(os.path.join(self.repo_path, '.gitmodules')).read()
        self.assertEqual(config, '%s%s' % (expected, expected2))

    def test_git_repo_add_gitpython(self):
        '''Could not find a way to write ignore=dirty into config

        So not using submodules. Keeping this for future reference. Works, but
        without ignore=dirty
        '''
        repo = git.Repo.init(self.repo_path)

        repo.git.submodule('add',  # '--ignore=dirty',
                           'https://localhost/repo.git', self.submodule_path)
        repo.git.commit(m="add subfolder1")
        expected = '[submodule "%s"]\n\tpath = %s\n\turl = %s\n' % (
            self.submodule_path, self.submodule_path,
            'https://localhost/repo.git')
        config = open(os.path.join(self.repo_path, '.gitmodules')).read()
        self.assertEqual(config, expected)

        repo.git.submodule('add',  # '--ignore=dirty',
                           'https://localhost/repo2.git', self.submodule_path2)
        expected2 = '[submodule "%s"]\n\tpath = %s\n\turl = %s\n' % (
            self.submodule_path2, self.submodule_path2,
            'https://localhost/repo2.git')
        repo.git.commit(m="add subfolder2")
        config = open(os.path.join(self.repo_path, '.gitmodules')).read()
        self.assertEqual(config, '%s%s' % (expected, expected2))


class TestGitNoDir(unittest.TestCase):
    def setUp(self):
        self.repo_path = os.path.join(TEST_PATH, uuid.uuid4().hex)

    @mock.patch.object(git.Repo, 'init')
    def test_init_repo_bad_path(self, git_Repo_init):
        self.assertFalse(os.path.exists(self.repo_path))
        with self.assertRaises(OSError):
            manager.init_deployment_repo(self.repo_path)
        assert not git_Repo_init.called

    def test_find_unregistered_submodules(self):
        results = manager._find_unregistered_submodules(self.repo_path)
        self.assertEqual(results, {})


class TestGitBlankDir(unittest.TestCase):
    def setUp(self):
        self.repo_path = os.path.join(TEST_PATH, uuid.uuid4().hex)
        os.makedirs(self.repo_path)

    def tearDown(self):
        shutil.rmtree(self.repo_path)

    def test_init_repo_makes_repo(self):
        manager.init_deployment_repo(self.repo_path)
        git_path = os.path.join(self.repo_path, '.git')
        self.assertTrue(os.path.isdir(git_path))
        config_path = os.path.join(self.repo_path, '.git', 'config')
        self.assertTrue(os.path.isfile(config_path))

    def test_find_unregistered_submodules(self):
        results = manager._find_unregistered_submodules(self.repo_path)
        self.assertEqual(results, {})


class TestGitDirWithData(unittest.TestCase):
    def setUp(self):
        self.repo_path = os.path.join(TEST_PATH, uuid.uuid4().hex)
        self.sub_dir_normal = os.path.join(self.repo_path, 'normal')
        self.sub_dir_repo = os.path.join(self.repo_path, 'repo')
        self.readme = os.path.join(self.repo_path, 'readme')

        os.makedirs(self.repo_path)
        os.makedirs(self.sub_dir_normal)
        os.makedirs(self.sub_dir_repo)
        with open(self.readme, 'w') as readme:
            readme.write('This has content!')
        with open(os.path.join(self.sub_dir_normal, 'stuff'), 'w') as stuff:
            stuff.write('.')
        repo = git.Repo.init(self.sub_dir_repo)
        with open(os.path.join(self.sub_dir_repo, 'foo'), 'w') as foo_file:
            foo_file.write('.')
        repo.git.add('foo')
        repo.git.commit(m="Initial Submodule Commit")
        repo.create_remote("origin", "http://localhost/submodule.git")

    def tearDown(self):
        shutil.rmtree(self.repo_path)

    def test_find_unregistered_submodules(self):
        results = manager._find_unregistered_submodules(self.repo_path)
        self.assertEqual(results, {'repo': 'http://localhost/submodule.git'})

    def test_init_repo_makes_repo(self):
        manager.init_deployment_repo(self.repo_path)

        git_path = os.path.join(self.repo_path, '.git')
        self.assertTrue(os.path.isdir(git_path))
        config_path = os.path.join(self.repo_path, '.git', 'config')
        self.assertTrue(os.path.isfile(config_path))

        files = git.Repo(self.repo_path).git.ls_files()
        files = files.split('\n')
        expecting = ['repo', 'readme', 'normal/stuff', '.gitmodules']
        self.assertItemsEqual(files, expecting)


class TestGitRepo(unittest.TestCase):
    '''Repo is already a repo (no submodules)'''
    def setUp(self):
        self.repo_path = os.path.join(TEST_PATH, uuid.uuid4().hex)
        os.makedirs(self.repo_path)
        git.Repo.init(self.repo_path)

    def tearDown(self):
        shutil.rmtree(self.repo_path)

    @mock.patch.object(git.Repo, 'init')
    def test_init_repo_already_repo(self, git_Repo_init):
        manager.init_deployment_repo(self.repo_path)
        assert not git_Repo_init.called

    def test_find_unregistered_submodules(self):
        git_modules_path = os.path.join(self.repo_path, '.gitmodules')
        self.assertFalse(os.path.exists(git_modules_path))
        results = manager._find_unregistered_submodules(self.repo_path)
        self.assertEqual(results, {})


if __name__ == '__main__':
    # Any change here should be made in all test files
    import sys
    from checkmate.test import run_with_params
    run_with_params(sys.argv[:])
