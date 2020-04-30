# coding=utf-8
import os
import re

import yaml

from fabric.context_managers import settings
from fabric.decorators import task
from fabric.state import env
from fabric.utils import indent, abort
from blues.application.deploy import maybe_install_requirements

from refabric.utils import info
from refabric.contrib import blueprints


from .. import git

blueprint = blueprints.get('blues.app')

__all__ = []


def get_providers(*args, **kw):
    from .providers import get_providers as real
    return real(*args, **kw)


@task
def setup():
    """
    Install project user, structure, env, source, dependencies and providers
    """
    from .deploy import install_project, install_virtualenv, \
        install_requirements, install_providers
    from .project import requirements_txt, use_virtualenv

    install_project()

    if use_virtualenv():
        install_virtualenv()
        install_requirements(requirements_txt(), update_pip=True)

    install_providers()
    configure_providers()


@task
def configure():
    """
    Deploy and configure providers
    """
    code_changed = deploy(auto_reload=False)
    configure_providers(force_reload=code_changed)


@task
def deploy(revision=None, auto_reload=True, force=False, update_pip=False):
    """
    Reset source to configured branch and install requirements, if needed

    :param bool auto_reload: Reload application providers if source has changed
    :param bool force: Force install of requirements
    :return bool: Source code has changed?
    """
    from .deploy import update_source
    from .project import use_virtualenv, project_home, project_name

    # Reset git repo
    previous_commit, current_commit = update_source(revision)
    code_changed = current_commit is not None and previous_commit != current_commit

    if code_changed:
        info('Updated git repository from: {} to: {}', previous_commit, current_commit)

    else:
        info('Reset git repository to: {}', current_commit)

    # Add Google Service User Credentials if present
    gcloudAccountKey = blueprint.get('gcloud_service_account_key')

    if gcloudAccountKey:
        context = {
        'service_account_key': gcloudAccountKey,
        }

        blueprint.upload('../gcloud/gcloud-service-account.json',
            os.path.join(project_home(), 'gcloud-service-account.json'),
            context, user=project_name())

    if code_changed or force:
        # Install python dependencies
        if use_virtualenv():
            maybe_install_requirements(previous_commit, current_commit, force,
                                       update_pip=update_pip)

        # Reload providers
        if auto_reload:
            reload()

    return (previous_commit, current_commit) if code_changed else False


@task
def install_requirements():
    """
    Install requirements witihn a virtualenv
    """
    from .deploy import install_requirements
    from .project import use_virtualenv

    if use_virtualenv():
        install_requirements()
    else:
        abort('Cannot install requirements without virtualenv')


@task
def deployed():
    """
    Show deployed and last origin commit
    """
    from .project import sudo_project, git_repository_path

    msg = ''
    params = []

    with sudo_project():
        repository_path = git_repository_path()
        git.fetch(repository_path)

        head_tag, head_tag_delta = git.current_tag(repository_path)
        if head_tag_delta > 0:
            msg += 'Latest tag: {} distance: {}'
            params += [head_tag, head_tag_delta]
        else:
            msg += 'Deployed tag: {}'
            params += [head_tag]

        head_commit, head_message = git.log(repository_path)[0]
        msg += '\nRevision: {} comment: {}'
        params += [head_commit, head_message]

        origin = git.get_origin(repository_path)
        origin_commit, origin_message = git.log(repository_path, refspec=origin)[0]
        if head_commit != origin_commit:
            msg += '\nRemote: {} revision: {} comment: {}'
            params += [origin, origin_commit, origin_message]

        info(msg, *params)
        return head_commit, origin_commit


@task
def incoming(revision=None):
    """
    Show changes since the deployed revision
    """
    from .project import sudo_project, git_repository_path

    with sudo_project():
        repository_path = git_repository_path()
        git.fetch(repository_path)

        current_revision, head_message = git.log(repository_path)[0]

        if not revision:
            origin = git.get_origin(repository_path)
            revision, _ = git.log(repository_path, refspec=origin)[0]

        if current_revision == revision:
            info("No changes detected")
            return None

        refspec = '{0}..{1}'.format(current_revision, revision)
        git_log = git.log(repository_path, refspec=refspec, count=False, author=True)

        if not git_log:
            info("Unable to get changelog (possibly different branches)")
            return None

        # (Re)fabric isn't always unicode safe
        summary = u'\n'.join([u' :: '.join(row) for row in git_log])
        info('Changes since deploy:\n{}', summary.encode('utf-8'))

        return git_log


@task
def start():
    """
    Start all application providers on current host
    """
    providers = get_providers(env.host_string)
    for provider in set(providers.values()):
        provider.start()


@task
def stop():
    """
    Stop all application providers on current host
    """
    providers = get_providers(env.host_string)
    for provider in set(providers.values()):
        provider.stop()


@task
def reload():
    """
    Reload all application providers on current host
    """
    providers = get_providers(env.host_string)
    for provider in set(providers.values()):
        provider.reload()


@task
def status():
    """
    get status from all application providers on current host
    """
    providers = get_providers(env.host_string)
    for provider in set(providers.values()):
        provider.status(blueprint.get('project'))


@task
def configure_providers(force_reload=False):
    """
    Render, upload and reload web & worker config

    :param bool force_reload: Force reload of providers, even if not updated
    :return dict: Application providers for current host
    """
    from .project import sudo_project

    with sudo_project():
        providers = get_providers(env.host_string)
        if 'web' in providers:
            providers['web'].configure_web()
        if 'worker' in providers:
            providers['worker'].configure_worker()

    # This may become a real provider in the future.
    configure_environment()

    for provider in set(providers.values()):
        if provider.updates or force_reload:
            provider.reload()

    return providers


@task
def configure_environment():
    from .project import project_home, project_name, sudo_project, git_repository_path
    from ..shell import configure_profile

    context = {"project_name": project_name()}
    blueprint.upload('dotenv/dotenv',
                     os.path.join(project_home(), '.env'),
                     context=context,
                     user=project_name())

    # Exports dotenv to the app user's interactive sessions
    configure_profile(project_home(), dotenv=True)

    config = blueprint.get('config', None)
    if config:
        context.update(config=config)
        blueprint.upload('dotenv/dotconf',
                         os.path.join(git_repository_path(), '.env'),
                         context=context,
                         user=project_name())


@task
def configure_beat_schedule():
    from .project import project_home, project_name

    schedule = blueprint.get('schedule', None)
    if schedule:
        blueprint.upload('beat/schedule',
                         os.path.join(project_home(), '.schedule'),
                         context={'schedule': yaml.dump(schedule)},
                         user=project_name())


@task
def generate_nginx_conf(role='www'):
    """
    Genereate nginx site config for web daemon

    :param str role: Name of role (directory) to generate config to
    """
    name = blueprint.get('project')
    socket = blueprint.get('web.socket', default='0.0.0.0:3030')
    host, _, port = socket.partition(':')
    if port:
        if len(env.hosts) > 1:
            # Multiple hosts -> Bind upstream to each host:port
            sockets = ['{}:{}'.format(host, port) for host in env.hosts]
        else:
            # Single host -> Bind upstream to unique configured socket
            sockets = [socket]
    else:
        sockets = ['unix:{}'.format(socket)]

    context = {
        'name': name,
        'sockets': sockets,
        'domain': blueprint.get('web.domain', default='_'),
        'ssl': blueprint.get('web.ssl', False),
        'ip_hash': blueprint.get('web.ip_hash', False)
    }

    template = blueprint.get('web.nginx_conf')

    if template is None:
        template = 'nginx/site.conf'
    else:
        template = 'nginx/{}.conf'.format(template)

    web_provider = blueprint.get('web.provider')
    if web_provider and web_provider == 'uwsgi':
        template = 'nginx/uwsgi_site.conf'

    with settings(template_dirs=['templates']):
        conf = blueprint.render_template(template, context)
        conf_dir = os.path.join(
            os.path.dirname(env['real_fabfile']),
            'templates',
            role,
            'nginx',
            'sites-available')
        conf_path = os.path.join(conf_dir, '{}.conf'.format(name))

    if not os.path.exists(conf_dir):
        os.makedirs(conf_dir)

    with open(conf_path, 'w+') as f:
        f.write(conf)
