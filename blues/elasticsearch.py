"""
Elasticsearch Blueprint
=======================

**Fabric environment:**

.. code-block:: yaml

    blueprints:
      - blues.elasticsearch

    settings:
      elasticsearch:
        # branch: 7.x                      # Major Version of elasticsearch (default: 7.x)
        # version: latest                  # Speciifc version of elasticsearch to install
        # cluster:
          # name: foobar                   # Name of the cluster (Default: elasticsearch)
          # nodes:                         # Nodes to explicitly add to the cluster (Optional)
            # - node
        # node:
          # name: foobarnode               # Node name (Default: <hostname>)
          # heap_size: 16gb                # Heap Size (defaults to 256m min, 1g max)
          # lock_memory: true              # Allocate the entire heap during startup (Default: false)
          # disable_swap: false            # Disable swap on nodes (Default: true)
          # master: true                   # Allow node to be elected master (Default: true)
          # data: true                     # Allow node to store data (Default: true)
          # bind: _site_                   # Set the bind address specifically, IPv4 or IPv6 (Default: _local_)
        # queue_size: 3000                 # Set thread pool queue size (Default: 1000)
        # plugins:                         # Optional list of plugins to install
        #   - repository-gcs

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
           'install_plugin', 'add_elastic_snapshot_repos', 'add_gcs_credentials']


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
        branch = blueprint.get('branch', '7.x')
        add_elastic_repo(branch)

        # ES 7 and higher bundles java
        if branch == '6.x':
            from blues import java
            java.install()

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

    cluster_repos = blueprint.get('cluster.repositories', [])
    repo_locations = []
    repo_url_locations = []
    if cluster_repos:
        for repo in cluster_repos:
            if cluster_repos[repo]['type'] == 'fs':
                repo_locations.append('"{}"'.format(cluster_repos[repo]['location']))
            elif cluster_repos[repo]['type'] == 'url':
                repo_url_locations.append('"{}"'.format(cluster_repos[repo]['url']))
    repo_locations = '[ {} ]'.format(", ".join(repo_locations))
    repo_url_locations = '[ {} ]'.format(", ".join(repo_url_locations))

    changes = []

    context = {
        'cluster_name': blueprint.get('cluster.name', 'elasticsearch'),
        'cluster_size': cluster_size,
        'zen_unicast_hosts': yaml.dump(cluster_nodes) if len(cluster_nodes) else None,
        'repos': repo_locations if len(repo_locations) else None,
        'urls': repo_url_locations if len(repo_url_locations) else None,
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

    disable_swap = blueprint.get('node.disable_swap', False)
    if disable_swap:
        debian.disable_swap()

    changes += blueprint.upload('./override.conf', service_dir + '/override.conf', context)

    if changes:
        restart()

@task
def add_gcs_credentials():
    import requests
    from fabric.state import env

    with silent():
        hostname = debian.hostname()
    node_name = blueprint.get('node.name', hostname)

    repos = blueprint.get('cluster.repositories', [])

    for repo in repos:

        if repos[repo]['type'] == 'gcs': 

            if 'client' in repos[repo]:
                client = repos[repo]['client']
            else:
                client = 'default'

            cred_file = '/elastic-snapshots-user-{}.json'.format(client)
            bin_path = '/usr/share/elasticsearch/bin/'


            blueprint.upload('./{}/elastic-snapshots-user-{}.json'.format(env.state, client),
                            cred_file, user='root', group='root')

            with sudo():
                run('{}elasticsearch-keystore add-file gcs.client.{}.credentials_file {}'.format(bin_path, client, cred_file))
                run('rm {} {}.md5 || true'.format(cred_file, cred_file))

    reload_url = 'http://{}:9200/_nodes/reload_secure_settings'.format(node_name)
    reload_reply = requests.post(url = reload_url)

    status_code = reload_reply.status_code

    if status_code != 200:
        abort("Could not reload keystore\nstatus code: {}\nmessage:\n{}".format(
            status_code, reload_reply.text))

@task
def add_elastic_snapshot_repos():
    import requests

    repos = blueprint.get('cluster.repositories', [])
    with silent():
        hostname = debian.hostname()
    node_name = blueprint.get('node.name', hostname)

    for repo in repos:
        repocheck = requests.get(url = 'http://{}:9200/_snapshot/{}'.format(node_name, repo))

        if repocheck.status_code == 404:
            info("Adding elastic snapshot repository '{}'".format(repo))
            url = 'http://{}:9200/_snapshot/{}'.format(node_name, repo)

            if 'readonly' in repos[repo]:
                readonly = repos[repo]['readonly']
            else:
                readonly = 'false'

            if repos[repo]['type'] == 'gcs':

                if 'client' in repos[repo]:
                    client = repos[repo]['client']
                else:
                    client = 'default'
                
                body = {
                    "type": 'gcs',
                    "settings": {
                        "bucket": repos[repo]['bucket'],
                        "client": client,
                        "readonly": readonly
                    }
                }
            elif repos[repo]['type'] == 'url':
                body = {
                    "type": repos[repo]['type'],
                    "settings": {
                        "url": repos[repo]['url']
                    }
                }
            else:
                body = {
                    "type": repos[repo]['type'],
                    "settings": {
                        "location": repos[repo]['location'],
                        "readonly": readonly
                    }
                }

            repoadd_reply = requests.put(url = url, json = body)
            status_code = repoadd_reply.status_code
            
            if status_code != 200:
                abort("Could not add elastic snapshot repository '{}'\nstatus code: {}\nmessage:\n{}".format(
                    repo, status_code, repoadd_reply.text))


@task
def install_plugin(name=None):
    if not name:
        abort('No plugin name given')

    with sudo():
        run('/usr/share/elasticsearch/bin/elasticsearch-plugin install {}'.format(name))
        restart()
