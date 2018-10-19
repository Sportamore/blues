"""
Kibana Blueprint
================

**Fabric environment:**

.. code-block:: yaml

    blueprints:
      - blues.kibana

    settings:
      kibana:
        # branch: 6.x                  # Major Version of kibana (Default: 6.x)
        # version: latest              # Speciifc version of kibana to install (Default: latest)
        name: kibana                   # Human-readable name of the instance Default: Kibana)
        host: localhost                # Listen host (Default: localhost)
        port: 5601                     # Listen port (Default: 5601)
        elasticsearch: localhost       # Elasticsearch server target (Default: localhost)
        basepath: ""                   # External url prefix (must not end with slash)
        default_app: home              # Kibana app to load by default
        plugins:                       # Optional list of plugins to install
          - elasticsearch/marvel/latest

"""
from fabric.decorators import task
from fabric.utils import abort

from refabric.api import run, info
from refabric.context_managers import sudo
from refabric.contrib import blueprints

from . import debian
from .elasticsearch import add_elastic_repo

__all__ = ['start', 'stop', 'restart', 'setup', 'configure', 'install_plugin']

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
        branch = blueprint.get('branch', '6.x')
        add_elastic_repo(branch)

        version = blueprint.get('version', 'latest')
        info('Installing {} version {}', 'kibana', version)
        package = 'kibana' + ('={}'.format(version) if version != 'latest' else '')
        debian.apt_get('install', package)

        debian.mkdir('/var/log/kibana', owner="kibana")

        # Enable on boot
        debian.add_rc_service('kibana', priorities='defaults 95 10')

        # Install plugins
        plugins = blueprint.get('plugins', [])
        for plugin in plugins:
            install_plugin(plugin)


@task
def configure():
    """
    Configure Kibana
    """
    context = {
        'name': blueprint.get('name', "Kibana"),
        'host': blueprint.get('host', 'localhost'),
        'elasticsearch': blueprint.get('elasticsearch', 'localhost'),
        'basepath': blueprint.get('basepath', ''),
        'default_app': blueprint.get('default_app', 'home')
    }
    context["rewritebasepath"] = "true" if context['basepath'] != '' else "false"
    config = blueprint.upload('./kibana.yml', '/etc/kibana/', context)

    if config:
        restart()


@task
def install_plugin(name=None):
    if not name:
        abort('No plugin name given')

    with sudo():
        run('/usr/share/kibana/bin/kibana-plugin install {}'.format(name))
