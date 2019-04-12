"""
Docker Blueprint
=======================

**Fabric environment:**

.. code-block:: yaml

    blueprints:
      - blues.docker

    settings:
      docker:
        version: latest
        config:
          # Any daemon.json options
          userns-remap: default
          log-driver: json-file


"""
import json
from fabric.decorators import task

from refabric.api import info
from refabric.context_managers import sudo
from refabric.contrib import blueprints

from . import debian

__all__ = ['start', 'stop', 'restart', 'reload', 'setup', 'configure']


blueprint = blueprints.get(__name__)

start = debian.service_task('docker', 'start')
stop = debian.service_task('docker', 'stop')
restart = debian.service_task('docker', 'restart')
reload = debian.service_task('docker', 'reload')


@task
def setup():
    """
    Install Docker
    """
    install()
    configure()


def install():
    with sudo():
        info('Adding apt repository for {}', 'docker')
        repository = '[arch=amd64] https://download.docker.com/linux/ubuntu {} stable'.format(
            debian.lsb_codename())
        debian.add_apt_repository(repository)

        gpg_key = 'https://download.docker.com/linux/ubuntu/gpg'
        info('Adding apt key from {}', gpg_key)
        debian.add_apt_key(gpg_key)
        debian.apt_get_update()

        # Install Docker
        version = blueprint.get('version', 'latest')
        info('Target version {}', version)
        package = 'docker-ce' + ('={}'.format(version) if version != 'latest' else '')

        info('Installing {}', package)
        debian.apt_get('install', package)

        if debian.lsb_release() == '14.04':
            blueprint.upload('./docker.default', '/etc/default/docker')

        else:
            blueprint.upload('./docker.service',
                             '/etc/systemd/system/docker.service')
            debian.ln(
                '/etc/systemd/system/docker.service',
                '/etc/systemd/system/multi-user.target.wants/docker.service',
            )
            debian.systemd_daemon_reload()


@task
def configure():
    """
    Configure Docker
    """
    daemon_json = json.dumps(blueprint.get('config', '') or {})

    changes = blueprint.upload('./daemon.json', '/etc/docker/', context={"config": daemon_json})

    if changes:
        restart()
