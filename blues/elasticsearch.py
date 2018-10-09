"""
Elasticsearch Blueprint
=======================

**Fabric environment:**

.. code-block:: yaml

    blueprints:
      - blues.elasticsearch

    settings:
      elasticsearch:
        # branch: 6.x                      # Major Version of elasticsearch (default: 2.x)
        # version: latest                  # Speciifc version of elasticsearch to install
        # cluster:
          # name: foobar                   # Name of the cluster (Default: elasticsearch)
          # nodes:                         # Nodes to explicitly add to the cluster (Optional)
            # - node
        # node:
          # name: foobarnode               # Node name (Default: <hostname>)
          # heap_size: 16gb                # Heap Size (defaults to 256m min, 1g max)
          # lock_memory: true              # Allocate the entire heap during startup (Default: True)
          # master: true                   # Allow node to be elected master (Default: True)
          # data: true                     # Allow node to store data (Default: True)
          # bind: _site_                   # Set the bind address specifically, IPv4 or IPv6 (Default: _local_)
        # queue_size: 3000                 # Set thread pool queue size (Default: 1000)
        # plugins:                         # Optional list of plugins to install
        #   - mobz/elasticsearch-head

"""
import yaml

from fabric.decorators import task
from fabric.utils import abort

from refabric.api import info
from refabric.context_managers import sudo, silent
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


def add_elastic_repo(branch):
    with sudo():
        info('Adding apt repository for {} branch {}', 'elastic.co', branch)

        repository = 'https://artifacts.elastic.co/packages/{}/apt stable main'.format(branch)
        debian.add_apt_repository(repository)

        info('Adding apt key for', repository)
        debian.add_apt_key('https://artifacts.elastic.co/GPG-KEY-elasticsearch')
        debian.apt_get_update()


def install():
    with sudo():
        from blues import java
        java.install()

        branch = blueprint.get('branch', '6.x')
        add_elastic_repo(branch)

        version = blueprint.get('version', 'latest')
        info('Installing {} version {}', 'elasticsearch', version)
        package = 'elasticsearch' + ('={}'.format(version) if version != 'latest' else '')
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
    with silent():
        hostname = debian.hostname()

    mlockall = blueprint.get('node.lock_memory', True)
    cluster_nodes = blueprint.get('cluster.nodes', [])
    cluster_size = len(cluster_nodes)

    changes = []

    context = {
        'cluster_name': blueprint.get('cluster.name', 'elasticsearch'),
        'cluster_size': cluster_size,
        'zen_unicast_hosts': yaml.dump(cluster_nodes) if len(cluster_nodes) else None,
        'node_name': blueprint.get('node.name', hostname),
        'node_master': yaml_boolean(blueprint.get('node.master', True)),
        'node_data': yaml_boolean(blueprint.get('node.data', True)),
        'data_path': yaml_boolean(blueprint.get('node.data_path', '/var/lib/elasticsearch')),
        'network_host': blueprint.get('node.bind', '_local_'),
        'heap_size': blueprint.get('node.heap_size', '256m'),
        'queue_size': blueprint.get('queue_size', '1000'),
        'memory_lock': yaml_boolean(mlockall),
        'mlockall': mlockall
    }

    changes += blueprint.upload('./elasticsearch.yml', '/etc/elasticsearch/',
                                context=context, user='elasticsearch')

    changes += blueprint.upload('./jvm.options', '/etc/elasticsearch/',
                                context=context, user='elasticsearch')

    changes += blueprint.upload('./default', '/etc/default/elasticsearch',
                                context=context, user='elasticsearch')

    service_dir = "/etc/systemd/system/elasticsearch.service.d"

    debian.mkdir(service_dir)
    changes += blueprint.upload('./override.conf', service_dir + '/override.conf', context)

    if changes:
        restart()


@task
def install_plugin(name=None):
    if not name:
        abort('No plugin name given')

    with sudo():
        run('/usr/share/elasticsearch/bin/elasticsearch-plugin install {}'.format(name))
