"""
Node.js Blueprint
=================

**Fabric environment:**

.. code-block:: yaml

    blueprints:
      - blues.node

    settings:
      node:
        # version: latest    # Install latest node version
        # user: some_app_user
        packages:            # List of npm packages to install (Optional)
          # - coffee-script
          # - yuglify
          # - less

"""


from fabric.contrib import files
from fabric.context_managers import cd, prefix
from fabric.decorators import task
from fabric.utils import abort, warn

from refabric.api import info
from refabric.context_managers import sudo
from refabric.contrib import blueprints
from refabric.operations import run

from .application.project import git_repository_path, project_home, \
    sudo_project, project_name
from .util import maybe_managed

from . import debian

__all__ = ['setup', 'configure']


blueprint = blueprints.get(__name__)


@task
def setup():
    """
    Setup Nodejs
    """
    install()
    configure()


@task
def configure():
    """
    Install npm packages
    """
    install_packages()


def get_version(default=7):
    """
    Support only major versions, since it affects which repository to add.
    """
    version = blueprint.get('version')
    try:
        return int(version)

    except ValueError:
        abort('Unsupported node version: {}'.format(version))


def get_user():
    return blueprint.get('user')


def install(for_user=None):
    info('Installing node from apt')

    with sudo():
        lsb_release = debian.lsb_release()
        if lsb_release not in ('14.04', '16.04'):
            abort('Unsupported OS version: {}'.format(lsb_release))

        codename = debian.lsb_codename()
        version = get_version()

        repository = 'https://deb.nodesource.com/node_{}.x {} main'.format(version, codename)
        debian.add_apt_repository(repository)

        info('Adding apt key for', 'nodesource')
        debian.add_apt_key('https://deb.nodesource.com/gpgkey/nodesource.gpg.key')
        debian.apt_get_update()

        info('Installing Node')
        debian.apt_get('install', 'nodejs')


def install_packages():
    packages = blueprint.get('packages', [])
    if packages:
        info('Installing Packages')
        npm('install {}'.format(' '.join(packages)), user=get_user())


def npm(command, user='root', *args):
    info('Running npm {} (as {})', command, user)
    sudo = 'sudo -i' if user == 'root' else 'sudo -iu {}'.format(user)
    opts = ' '.join(args)
    run('{} npm {} {}'.format(sudo, opts, command))
