"""
Kibana Blueprint
================

**Fabric environment:**

.. code-block:: yaml

    blueprints:
      - blues.kibana

    settings:
      kibana:
        version: 4.6            # Version of kibana to install (Required)
        es_host: localhost      # Elasticsearch server target (Default: localhost)
        basepath: ""            # External url prefix (must not end with slash)
        landing_page: discover  # Kibana app to load by default

"""
import os.path

from fabric.decorators import task
from fabric.operations import local, prompt
from fabric.state import env

from refabric.api import run, info
from refabric.context_managers import sudo
from refabric.contrib import blueprints

from . import debian

__all__ = ['start', 'stop', 'restart', 'setup', 'configure']

blueprint = blueprints.get(__name__)

start = debian.service_task('kibana', 'start')
stop = debian.service_task('kibana', 'stop')
restart = debian.service_task('kibana', 'restart')

start.__doc__ = 'Start Kibana'
stop.__doc__ = 'Stop Kibana'
restart.__doc__ = 'Restart Kibana'


@task
def setup():
    """
    Install and configure kibana
    """
    install()
    configure()


def install():
    with sudo():
        version = blueprint.get('version', '4.6')
        info('Adding apt repository for {} version {}', 'kibana', version)
        debian.add_apt_repository('https://packages.elastic.co/kibana/{}/debian stable main'.format(version))

        info('Installing {} version {}', 'kibana', version)
        debian.apt_get_update()
        debian.apt_get('install', 'kibana')

        # Enable on boot
        debian.add_rc_service('kibana', priorities='defaults 95 10')


@task
def configure():
    """
    Configure Kibana
    """
    context = {
        'es_host': blueprint.get('es_host', 'localhost'),
        'basepath': blueprint.get('basepath', ''),
        'landing_page': blueprint.get('landing_page', 'discover')
    }
    config = blueprint.upload('./kibana.yml', '/opt/kibana/config/', context)

    if config:
        restart()
