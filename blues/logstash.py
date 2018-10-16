"""
Logstash Blueprint
==================

**Fabric environment:**

.. code-block:: yaml

    blueprints:
      - blues.logstash

    settings:
      logstash:
        ssl: false                        # Secure beats communication (Default: False)

        # branch: 6.x                    # Major Version of logstash (Default: 6.x)
        # version: latest                # Speciifc version of logstash to install (Default: latest)

        elasticsearch: localhost         # ES Server address (Default: localhost)
        workers: 2                       # The number of queue worker processes
        persistent_queue: false          # Usae the new persisted (disk-backed) queue

        plugins:                         # Optional community plugins
          - logstash-filter-translate

        auto_disable_conf: True          # Disable any config files not listed in 'config' (Default: True)
        config:                          # Mapping of weight: config_file
          11: input-lumberjack           # Included logstash-forwarder input handler
          12: input-beats                # Included beats input handler
          21: syslog                     # Included syslog grokker
          91: output-elasticsearch       # Included elasticsearch output handler


"""
import yaml
import os.path
from functools import partial

from fabric.context_managers import cd
from fabric.contrib import files
from fabric.decorators import task
from fabric.utils import warn, abort

from refabric.api import run, info
from refabric.context_managers import sudo, silent
from refabric.contrib import blueprints

from . import debian

__all__ = ['setup', 'configure', 'install_plugin', 'start', 'stop', 'restart']


blueprint = blueprints.get(__name__)

logstash_root = '/etc/logstash'
conf_available_path = os.path.join(logstash_root, 'conf.available')
conf_enabled_path = os.path.join(logstash_root, 'conf.d')
grokker_path = os.path.join(logstash_root, 'patterns')


def service(action=None):
    """
    Debian service dispatcher for logstash server
    """
    debian.service('logstash', action, check_status=False)


start = task(partial(service, action='start'))
stop = task(partial(service, action='stop'))
restart = task(partial(service, action='restart'))

start.__doc__ = 'Start logstash'
stop.__doc__ = 'Stop logstash'
restart.__doc__ = 'Restart logstash'


@task
def setup():
    """
    Setup Logstash server
    """
    from .elasticsearch import add_elastic_repo

    with sudo():
        branch = blueprint.get('branch', '6.x')
        add_elastic_repo(branch)

        version = blueprint.get('version', 'latest')
        info('Installing {} version {}', 'logstash', version)
        package = 'logstash' + ('={}'.format(version) if version != 'latest' else '')
        debian.apt_get('install', package)

        # Enable on boot
        debian.add_rc_service('logstash')

        # prep custom folders
        debian.mkdir(conf_available_path)
        debian.mkdir(conf_enabled_path)

        # Install plugins
        plugins = blueprint.get('plugins', [])
        for plugin in plugins:
            info('Installing logstash "{}" plugin...', plugin)
            install_plugin(plugin)

        # Create and download SSL cert
        create_server_ssl_cert()
        download_server_ssl_cert()

    configure()


@task
def install_plugin(name=None):
    if not name:
        abort('No plugin name given')

    with sudo():
        run('/usr/share/logstash/bin/logstash-plugin install {}'.format(name))


@task
def configure():
    """
    Configure Logstash server
    """
    uploads = []

    # Configure the logstash service
    persistent_queue = blueprint.get('persistent_queue', False)
    service_context = {
        'pipeline_workers': blueprint.get('workers', 2),
        'queue_type': 'persisted' if persistent_queue else 'memory',
        'metrics_host': blueprint.get('metrics_host', 'localhost'),
        'metrics_port': blueprint.get('metrics_port', 9600),
    }
    uploads += blueprint.upload('./logstash.yml', logstash_root, service_context)
    uploads += blueprint.upload('./patterns/', grokker_path)

    # Provision filters
    elasticsearch = blueprint.get('elasticsearch', 'localhost')
    config_context = {
        'ssl': blueprint.get('ssl', False),
        'elasticsearch': (
            elasticsearch if isinstance(elasticsearch, list) else [elasticsearch]
        )
    }

    uploads += blueprint.upload('./conf/', conf_available_path, config_context)
    filter_changes = update_filters()

    if uploads or filter_changes:
        restart()


def update_filters():
    changes = []

    # Generate desired state as enabled_name => source_name
    config = blueprint.get('config', {})
    filters = {
        '{}-{}.conf'.format(str(weight).zfill(2), conf): "{}.conf".format(conf)
        for weight, conf in config.iteritems()
    }

    # Get current state
    with silent():
        enabled_filters = run('ls {}'.format(conf_enabled_path)).split()

    # Disable extra services
    if blueprint.get('auto_disable_conf', True):
        for link in set(enabled_filters) - set(filters.keys()):
            info('Disabling conf: {}', link)
            changes.append(link)

            with silent(), sudo(), cd(conf_enabled_path):
                debian.rm(link)

    # Enable services
    for target in set(filters.keys()) - set(enabled_filters):
        source = os.path.join(conf_available_path, filters[target])
        info('Enabling conf: {}', target)
        changes.append(source)

        with silent(), sudo(), cd(conf_enabled_path):
            debian.ln(source, target)

    return changes


def create_server_ssl_cert():
    with sudo():
        info('Generating SSL certificate...')
        debian.mkdir('/etc/pki/tls/certs')
        debian.mkdir('/etc/pki/tls/private')
        with cd('/etc/pki/tls'):
            hostname = debian.hostname()
            key = 'private/logstash.key'
            crt = 'certs/logstash.crt'
            run('openssl req -x509 -batch -nodes -days 3650 -newkey rsa:2048 '
                '-keyout {} '
                '-out {} '
                '-subj "/CN={}"'.format(key, crt, hostname))


def download_server_ssl_cert(destination='ssl/'):
    blueprint.download('/etc/pki/tls/certs/logstash.crt', destination)
