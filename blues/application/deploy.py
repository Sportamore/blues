# coding=utf-8

import os
import pkg_resources
import re

from functools import partial

from fabric.context_managers import cd
from fabric.state import env
from fabric.utils import indent, abort, warn
from blues.application.project import git_repository_path

from refabric.context_managers import sudo, silent
from refabric.operations import run
from refabric.utils import info
from refabric.contrib import blueprints

from .providers import get_providers

from .. import debian
from .. import git
from .. import user
from .. import python
from .. import virtualenv
from .. import slack

__all__ = [
    'install_project',
    'install_project_user',
    'install_project_structure',
    'install_system_dependencies',
    'install_virtualenv',
    'install_requirements',
    'install_or_update_source',
    'install_source',
    'update_source',
    'install_providers',
    'notify_start',
    'notify_finish',
    'notify_event'
]


blueprint = blueprints.get('blues.app')


def install_project():
    create_app_root()
    install_project_user()
    install_project_structure()
    install_system_dependencies()
    install_or_update_source()


def create_app_root():
    from .project import app_root

    with sudo():
        # Create global apps root
        root_path = app_root()
        debian.mkdir(root_path, recursive=True)


def install_project_user():
    """
    Create project user and groups.
    Create user home dir.
    Disable ssh host checking.
    Create log dir.
    """
    from .project import project_home

    with sudo():
        info('Install application user')
        username = blueprint.get('project')
        home_path = project_home()

        # Setup groups for project user
        project_user_groups = ['app-data', 'www-data']
        for group in project_user_groups:
            debian.groupadd(group, gid_min=10000)

        # Get UID for project user
        user.create_system_user(username, groups=project_user_groups,
                                home=home_path)

        # Create application log path
        application_log_path = os.path.join('/var', 'log', username)
        debian.mkdir(application_log_path, group='app-data', mode=1775)

        # Configure ssh for github
        user.set_strict_host_checking(username, 'github.com')


def install_project_structure():
    """
    Create project directory structure
    """
    from .project import static_base, use_static

    with sudo():
        info('Install application directory structure')

        create_app_root()

        if use_static():
            # Create static web paths
            static_path = os.path.join(static_base(), 'static')
            media_path = os.path.join(static_base(), 'media')
            debian.mkdir(static_path, group='www-data', mode=1775)
            debian.mkdir(media_path, group='www-data', mode=1775)


def install_system_dependencies():
    """
    Install system wide packages that application depends on.
    """
    with sudo(), silent():
        info('Install system dependencies')
        system_dependencies = blueprint.get('system_dependencies')

        if system_dependencies:
            dependencies = []
            repositories = []
            ppa_dependencies = []
            for dependency in system_dependencies:
                dep, _, rep = dependency.partition('@')
                if rep:
                    if rep not in repositories:
                        repositories.append(rep)

                    ppa_dependencies.append(dep)
                elif dep not in dependencies:
                    dependencies.append(dep)

            debian.apt_get_update()
            debian.apt_get('install', *dependencies)

            if repositories:
                for repository in repositories:
                    debian.add_apt_repository(repository, src=True)

                debian.apt_get_update()
                debian.apt_get('install', *ppa_dependencies)


def install_virtualenv():
    """
    Create a project virtualenv.
    """
    from .project import sudo_project, virtualenv_path

    with sudo():
        virtualenv.install()

    with sudo_project():
        virtualenv.create(virtualenv_path())


def maybe_install_requirements(previous_commit, current_commit, force=False, update_pip=False):
    from .project import requirements_txt, git_repository_path

    installation_file = requirements_txt()

    installation_method = get_installation_method(installation_file)

    has_changed = False

    commit_range = '{}..{}'.format(previous_commit, current_commit)

    if not force:
        if installation_method == 'pip':
            has_changed, added, removed = diff_requirements(
                previous_commit,
                current_commit,
                installation_file)

            if has_changed:
                info('Requirements have changed, added: {}, removed: {}'.format(
                    ', '.join(added),
                    ', '.join(removed)))
        else:
            # Check if installation_file has changed
            commit_range = '{}..{}'.format(previous_commit, current_commit)
            has_changed, _, _ = git.diff_stat(
                git_repository_path(),
                commit_range,
                installation_file)

    if has_changed or force:
        install_requirements(installation_file, update_pip=update_pip)
    else:
        info(indent('(requirements not changed in {}...skipping)'),
             commit_range)


def diff_requirements(previous_commit, current_commit, filename):
    """
    Diff requirements file

    :param previous_commit:
    :param current_commit:
    :param filename:
    :return: 3-tuple with (has_changed, additions, removals) where
        has_changed is a bool, additions and removals may be sets or None.
    """
    try:
        return diff_requirements_smart(previous_commit,
                                       current_commit,
                                       filename,
                                       strict=True)
    except ValueError:
        warn('Smart requirements diff failed, falling back to git diff')

    has_changed, insertions, deletions = git.diff_stat(
        git_repository_path(),
        '{}..{}'.format(previous_commit, current_commit),
        filename)

    return has_changed, [str(insertions)], [str(deletions)]


def patch_requirements(s):
    """
    Replaces VCS urls by `pkg==version` so that setuptools can parse
    requirements and we can diff them.
    """
    ex = re.compile('(\-e\s+)?(git|hg|svn|bzr)(\+|://)\S*@([\S^@]+)#egg=(\S+)',
                    flags=re.MULTILINE)
    return ex.sub('\\5==\\4', s)


def parse_requirements(strs):
    """
    Parse requirements after VCS urls are replaced by `pkg==version`.
    """
    if isinstance(strs, basestring):
        strs = patch_requirements(strs)
    else:
        strs = map(patch_requirements, strs)
    return pkg_resources.parse_requirements(strs)


def diff_requirements_smart(previous_commit, current_commit, filename,
                            strict=False):
    filename = os.path.relpath(filename, git_repository_path())

    get_requirements = partial(git.show_file,
                               repository_path=git_repository_path(),
                               filename=filename)

    force_changed = False

    try:
        # Can't fit this is one line :(
        previous = parse_requirements(get_requirements(revision=previous_commit))
        previous = {str(r) for r in previous}
    except ValueError as exc:
        warn('Failed to parse previous requirements: {}'.format(exc))
        previous = set()
        force_changed = True

        if strict:
            raise

    try:
        # Can't fit this is one line :(
        current = parse_requirements(get_requirements(revision=current_commit))
        current = {str(r)for r in current}
    except ValueError as exc:
        warn('Failed to parse new requirements: {}'.format(exc))
        current = set()
        force_changed = True

        if strict:
            raise

    additions = current.difference(previous)
    removals = previous.difference(current)

    has_changed = force_changed or bool(additions or removals)

    return has_changed, additions, removals


def get_installation_method(filename):
    """
    Guess installation method from the requirements file

    :return: 'pip' or 'setuptools'
    """
    if filename.endswith('.txt') or \
            filename.endswith('.pip'):
        return 'pip'

    if os.path.basename(filename) == 'setup.py':
        return 'setuptools'


def install_requirements(installation_file=None, update_pip=False):
    """
    Pip install requirements in project virtualenv.
    """
    from .project import sudo_project, virtualenv_path, requirements_txt

    if not installation_file:
        installation_file = requirements_txt()

    with sudo_project():
        path = virtualenv_path()

        with virtualenv.activate(path):
            installation_method = get_installation_method(installation_file)
            if update_pip:
                python.update_pip(quiet=True)

            if installation_method == 'pip':
                info('Installing requirements from: {}', installation_file)
                python.pip('install', '-r', installation_file, quiet=True)

            elif installation_method == 'setuptools':
                src_path = git_repository_path()

                info('Installing directory: {}', src_path)
                python.pip('install', '-e', src_path, quiet=True)

            else:
                raise ValueError(
                    '"{}" is not a valid installation file'.format(
                        installation_file))


def install_or_update_source():
    """
    Try to install source, if already installed then update.
    """
    new_install = install_source()
    if not new_install:
        update_source()


def install_source():
    """
    Install git and clone application repository.

    :return: True, if repository got cloned
    """
    from .project import sudo_project, git_repository, git_root

    with sudo():
        git.install()

    with sudo_project() as project:
        path = git_root()
        debian.mkdir(path, owner=project, group=project)
        with cd(path):
            repository = git_repository()
            path, cloned = git.clone(repository['url'], branch=repository['branch'])
            if cloned is None:
                abort('Failed to install source, aborting!')

    return cloned


def update_source(revision=None):
    """
    Update application repository to the specified revision,
    defaults to the projects branch if not specified.

    :return: tuple(previous commit, current commit)
    """
    from .project import sudo_project, git_repository_path, remote_head

    if not revision:
        branch, revision = remote_head()

    with sudo_project():
        # Get current commit
        repository_path = git_repository_path()
        previous_commit = git.get_commit(repository_path, short=True)

        # Update source from git (reset)
        current_commit = git.reset(repository_path=repository_path,
                                   revision=revision,
                                   ignore=blueprint.get('git_force_ignore'))

        return previous_commit, current_commit


def install_providers():
    """
    Install application providers on current host.
    """
    host = env.host_string
    providers = get_providers(host)
    for provider in providers.values():
        if getattr(provider, 'manager', None) is not None:
            provider.manager.install()

        provider.install()


def _deploy_summary(title, revision):
    from hashlib import md5
    from time import time
    from .project import project_name

    deployer = git.get_local_commiter()
    email = git.get_local_email()
    project = project_name()
    state = env.get('state', 'Unknown')

    avatar_hash = md5(email.strip().lower()).hexdigest()
    avatar_url = 'https://www.gravatar.com/avatar/{}?s=16'.format(avatar_hash)
    fallback = "Deploy: {} ({}) by {}".format(project, state, deployer)

    summary = {
        'fallback': fallback,
        'color': '#439FE0',
        'author_name': deployer,
        'author_icon': avatar_url,
        # 'ts': int(time()),
        'title': u'{} ({})'.format(project, state),
        'fields': [
            {'title': 'Label', 'value': title, 'short': True}
        ],
        'mrkdwn_in': ['text', 'fields']
    }

    if revision:
        summary['fields'].append({
            'title': 'revision',
            'value': '_{}_'.format(revision),
            'short': True
        })

    return summary


def notify_start(title, revision=None, changes=None):
    """
    Send a message to slack about the start of a deployment

    :return str: plaintext message part
    """
    from .project import github_link

    summary = _deploy_summary(title, revision)
    summary["color"] = "warning"

    if changes:
        base_url = github_link()
        log_template = u'`<{base_url}/commit/{rev}|{rev}>` {msg}'
        formatted_changes = [log_template.format(base_url=base_url, rev=rev, msg=msg)
                             for rev, msg in changes]

        summary['fields'].append({
            'title': 'Changes',
            'value': u'\n'.join(formatted_changes),
            'short': False
        })

    slack.notify(None, summary)


def notify_finish(title, revision=None):
    """
    Send a message to slack about the end of a deployment

    :return str: plaintext message part
    """
    summary = _deploy_summary(title, revision)
    summary["color"] = "good"

    slack.notify(None, summary)


def notify_event(commits=None):
    """
    Send a message to slack about a successful deployment

    :return str: formatted message
    """
    from .project import project_name, git_repository_path, github_link

    msg = u'*{project}* (*{state}*)'

    if commits:
        msg += u' deployed `<{base_url}/compare/{old}...{new}|{old} → {new}>`'
    else:
        msg += u' reset to `<{base_url}/commit/{commit}|{commit}>`'

    msg += u' on `{host}`'

    old_commit, new_commit = commits or (None, None)
    commit = commits or git.get_commit(repository_path=git_repository_path(), short=True)
    msg = msg.format(
        project=project_name(),
        base_url=github_link(),
        state=env.get('state', 'unknown'),
        old=old_commit,
        new=new_commit,
        commit=commit,
        host=env['host_string']
    )

    slack.notify(msg)
    return msg
