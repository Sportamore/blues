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
        packages:            # List of npm packages to install (Optional)
          # - coffee-script
          # - yuglify
          # - less

"""


import os.path

from fabric.decorators import task
from fabric.utils import abort

from refabric.api import info
from refabric.context_managers import sudo
from refabric.contrib import blueprints
from refabric.operations import run

from .application.project import project_home, project_name
from . import debian

__all__ = ['setup', 'configure', 'npm', 'install_package', 'node_binary']


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
    install_project_packages()


def get_version(default=7):
    """
    Support only major versions, since it affects which repository to add.
    """
    version = blueprint.get('version')
    try:
        return int(version)

    except ValueError:
        abort('Unsupported node version: {}'.format(version))


def node_binary(program):
    """
    Get the absolute path of an installed node binary
    """
    return os.path.join(project_home(), 'node_modules', '.bin', program)


def install(for_user=None):
    info('Installing node from apt')

    with sudo():
        lsb_release = debian.lsb_release()
        if lsb_release in ('14.04', '16.04'):
            codename = debian.lsb_codename()
            version = get_version()

            repository = 'https://deb.nodesource.com/node_{}.x {} main'.format(version, codename)
            debian.add_apt_repository(repository)

            info('Adding apt key for', 'nodesource')
            debian.add_apt_key('https://deb.nodesource.com/gpgkey/nodesource.gpg.key')
            debian.apt_get_update()

            info('Installing Node')
            debian.apt_get('install', 'nodejs')
        else:
            debian.apt_get('install','npm')


def install_package(package, local=True):
    """
    Install a single npm package, for the current project or globally
    """
    info('Installing package: {}', package)
    if local:
        npm('install {}'.format(package), user=project_name())

    else:
        npm('install -g {}'.format(package))


def install_project_packages():
    """
    Install all declared packages
    """
    packages = blueprint.get('packages', [])
    if packages:
        info('Installing project packages')
        npm('install {}'.format(' '.join(packages)), user=project_name())


def npm(command, user='root', quiet=True):
    """
    Run arbitrary NPM commands
    """
    sudo = 'sudo -i' if user == 'root' else 'sudo -iu {}'.format(user)
    info('Running npm as {}', user)
    if quiet:
        command = '--quiet ' + command

    run('{} npm --no-progress {}'.format(sudo, command))
