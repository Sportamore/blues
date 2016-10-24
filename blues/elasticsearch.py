"""
Elasticsearch Blueprint
=======================

**Fabric environment:**

.. code-block:: yaml

    blueprints:
      - blues.elasticsearch

    settings:
      elasticsearch:
        # branch: 2.x                      # Major Version of elasticsearch (default: 2.x)
        version: 2.4.1                     # Speciifc version of elasticsearch to install (Required)
        # cluster:
          # name: foobar                   # Name of the cluster (Default: elasticsearch)
        # node:
          # name: foobarnode               # Node name (Default: <hostname>)
          # heap_size: 16gb                # Heap Size (defaults to 256m min, 1g max)
          # master: true                   # Allow node to be elected master (Default: True)
          # data: true                     # Allow node to store data (Default: True)
        # network:
          # bind_host: 127.0.0.1           # Set the bind address specifically, IPv4 or IPv6 (Default: 0.0.0.0)
          # publish_host: 127.0.0.1        # Set the address other nodes will use to communicate with this node (Optional)
          # host: 127.0.0.1                # Set both `network_bind_host` and `network_publish_host` (Optional)
        # multicast_discovery:             # Use multicast discovery (default: True)
        # default_shards: 5                # Number of shards/splits of an index (Default: 5)
        # default_replicas: 0              # Number of replicas / additional copies of an index (Default: 0)
        # mlockall: true                   # Allocate all allowed memory on startup (Default: True)
        # queue_size: 3000                 # Set thread pool queue size (Default: 1000)
        # log_level: WARN                  # Set the log level to use (Default: WARN)
        # plugins:                         # Optional list of plugins to install
        #   - mobz/elasticsearch-head

"""
from fabric.decorators import task
from fabric.utils import abort

from refabric.api import info
from refabric.context_managers import sudo
from refabric.contrib import blueprints

from . import debian
from refabric.operations import run

__all__ = ['start', 'stop', 'restart', 'reload', 'setup', 'configure',
           'install_plugin']


blueprint = blueprints.get(__name__)

start = debian.service_task('elasticsearch', 'start')
stop = debian.service_task('elasticsearch', 'stop')
restart = debian.service_task('elasticsearch', 'restart')
reload = debian.service_task('elasticsearch', 'force-reload')


@task
def setup():
    """
    Install Elasticsearch
    """
    install()
    configure()


def install():
    with sudo():
        from blues import java
        java.install()

        branch = blueprint.get('branch', '2.x')

        info('Adding apt repository for {} branch {}', 'elasticsearch', branch)
        repository = 'https://packages.elastic.co/elasticsearch/{0}/debian stable main'.format(branch)
        debian.add_apt_repository(repository)

        info('Adding apt key for', repository)
        debian.add_apt_key('https://packages.elastic.co/GPG-KEY-elasticsearch')
        debian.apt_get_update()

        # Install elasticsearch (and java)
        version = blueprint.get('version', '2.4.0')
        info('Installing elasticsearch version "{}"', version)
        package = 'elasticsearch' + ('={}'.format(version) if version else '')

        info('Installing {}', package)
        debian.apt_get('install', package)

        # Install plugins
        plugins = blueprint.get('plugins', [])
        for plugin in plugins:
            info('Installing elasticsearch "{}" plugin...', plugin)
            install_plugin(plugin)

        # Enable on boot
        debian.add_rc_service('elasticsearch', priorities='defaults 95 10')


def yaml_boolean(input):
    return str(input).lower()


@task
def configure():
    """
    Configure Elasticsearch
    """
    mlockall = blueprint.get('mlockall', True)

    context = {
        'cluster_name': blueprint.get('cluster.name', 'elasticsearch'),
        'node_name': blueprint.get('node.name', debian.hostname()),
        'node_master': yaml_boolean(blueprint.get('node.master', True)),
        'node_data': yaml_boolean(blueprint.get('node.data', True)),
        'bind_host': blueprint.get('network.bind_host'),
        'publish_host': blueprint.get('network.publish_host'),
        'host': blueprint.get('network.host'),
        'zen_multicast': yaml_boolean(blueprint.get('multicast_discovery', True)),
        'number_of_shards': blueprint.get('default_shards', '5'),
        'number_of_replicas': blueprint.get('default_replicas', '0'),
        'mlockall': yaml_boolean(mlockall),
        'queue_size': blueprint.get('queue_size', '1000')
    }
    config = blueprint.upload('./elasticsearch.yml', '/etc/elasticsearch/', context)

    context = {
        'log_level': blueprint.get('log_level', 'WARN'),
    }
    logging = blueprint.upload('./logging.yml', '/etc/elasticsearch/', context)

    debian.chmod('/etc/elasticsearch/', group='elasticsearch', recursive=True)

    context = {
        'heap_size': blueprint.get('node.heap_size', '256m'),
        'max_locked_memory': "unlimited" if mlockall else ""
    }
    default = blueprint.upload('./default', '/etc/default/elasticsearch', context)

    if config or logging or default:
        restart()


@task
def install_plugin(name=None):
    if not name:
        abort('No plugin name given')

    with sudo():
        run('/usr/share/elasticsearch/bin/plugin install {}'.format(name))
