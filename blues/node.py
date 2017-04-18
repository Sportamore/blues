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


def get_version():
    """
    Support only major versions, since it affects which repository to add.
    """
    version = blueprint.get('version')
    if version in range(4, 8):
        return version

    else:
        abort('Unsupported node version: {}'.format(version))


def install(for_user=None):
    info('Installing node from apt')

    with sudo():
        lsb_release = debian.lsb_release()
        codename = debian.lsb_codename()
        version = get_version()

        if lsb_release in ('14.04', '16.04'):

            repository = 'https://deb.nodesource.com/node_{}.x {} main'.format(version, codename)
            debian.add_apt_repository(repository)

        else:
            abort('Unsupported OS version: {}'.format(lsb_release))

        info('Adding apt key for', 'nodesource')
        debian.add_apt_key('https://deb.nodesource.com/gpgkey/nodesource.gpg.key')
        debian.apt_get_update()

        info('Installing Node')
        debian.apt_get('install', 'nodejs')


def install_packages():
    packages = blueprint.get('packages', [])
    if packages:
        info('Installing Packages')
        npm('install', *packages)


def npm(command, *options):
    info('Running npm {}', command)
    with sudo():
        run('npm {} -g {}'.format(command, ' '.join(options)))
