# coding=utf-8

import os
import re
from contextlib import contextmanager
from collections import OrderedDict

from refabric.context_managers import sudo
from refabric.contrib import blueprints
from refabric.utils import info

from .. import git

__all__ = [
    'app_root', 'project_home', 'git_root', 'use_virtualenv', 'virtualenv_path',
    'git_repository', 'git_repository_path', 'python_path', 'sudo_project',
    'requirements_txt', 'use_python', 'static_base', 'project_name',
    'releases', 'remote_head', 'github_repository', 'github_link'
]

blueprint = blueprints.get('blues.app')

# install python runtime and libs
use_python = lambda: blueprint.get('use_python', True)

# install virtualenv and python dependencies
use_virtualenv = lambda: blueprint.get('use_virtualenv', True) and use_python()

# Should we set up /srv/www?
use_static = lambda: blueprint.get('use_static', True)

# /srv/app
app_root = lambda: blueprint.get('root_path') or '/srv/app'
# /srv/app/project
project_home = lambda: os.path.join(app_root(), blueprint.get('project'))
# /srv/app/project/src
git_root = lambda: os.path.join(project_home(),
                                'src')
# /srv/app/project/env
virtualenv_path = lambda: os.path.join(project_home(),
                                       'env')
# git repo dict
git_repository = lambda: git.parse_url(blueprint.get('git_url'),
                                       branch=blueprint.get('git_branch'))
# /srv/app/project/src/repo.git
git_repository_path = lambda: os.path.join(git_root(),
                                           git_repository()['name'])
# 1.2, 1.2.3, v1.0
git_tag_pattern = lambda: blueprint.get('release_pattern') or r'^v?\d+(\.\d+)+$'

# /srv/app/project/src/repo.git
python_path = lambda: os.path.join(git_repository_path(),
                                   blueprint.get('git_source', 'src'))
# /srv/app/project/src/repo.git/requirements.txt
requirements_txt = lambda: os.path.join(git_repository_path(),
                                        blueprint.get('requirements',
                                                      'requirements.txt'))
# <project>
project_name = lambda: blueprint.get('project')

# /srv/www/project
static_base = lambda: blueprint.get('static_base',
                                    os.path.join('/srv/www/', project_name()))


@contextmanager
def sudo_project():
    with sudo(project_name()):
        yield project_name()


def releases():
    """
    Get the name and reivision of the latest remote tag.
    :return OrderedDict: {label: revision, ...}
    """
    repo = git_repository()
    remote_tags = git.lsremote(repo['url'], reftype='tags')

    filtered_tags = [(tag, rev[:7]) for (tag, rev) in remote_tags.items()
                     if re.match(git_tag_pattern(), tag)]
    releases_tags = OrderedDict(sorted(filtered_tags,
                                       key=lambda x: x[0]))

    # info('Got {} releases from: {}', len(releases_tags), repo['url'])

    return releases_tags


def remote_head():
    """
    Get the name and reivision of the remote head.
    :return: (branchname, revision)
    """
    repo = git_repository()
    ls = git.lsremote(repo['url'], reftype='branches')

    # info('Got {} branches from: {}', len(ls), repo['url'])

    branch = repo['branch']
    return ('origin/{}'.format(branch), ls[branch][:7])


def github_repo():
    """
    Get the canonical name of a github repo

    :return str: repository name
    """
    repo = git_repository()

    repo_owner = repo['gh_owner']
    repo_name = repo['name']

    if repo_name.endswith('.git'):
        repo_name = repo_name[:-4]

    if not repo_owner and repo_name:
        return None

    return '{}/{}'.format(repo_owner, repo_name)


def github_link():
    """
    Get the HTTP url to the configured github repo

    :return str: repository url
    """
    repo = github_repo()
    if not repo:
        return None

    return 'https://github.com/{}'.format(repo)
