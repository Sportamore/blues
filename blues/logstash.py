"""
Logstash Blueprint
==================

**Fabric environment:**

.. code-block:: yaml

    blueprints:
      - blues.logstash

    settings:
      logstash:
        ssl: true                          # Secure communication between forwarder and server (Default: True)

        server:                            # The presence of this key will cause the host to be considered a server
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

        forwarder:                         # The presence of this key will install the forwarder
          servers:                         # One or more target servers (Required)
            - some.host.tld

          files:                           # One or more file blocks
            nginx-access:                  # The document_type to add to the event
              - '/var/log/*.log'           # Wildcards are supported

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
from .elasticsearch import add_elastic_repo

__all__ = ['setup', 'configure', 'install_plugin', 'enable', 'disable', 'start', 'stop', 'restart']


blueprint = blueprints.get(__name__)

logstash_root = '/etc/logstash'
conf_available_path = os.path.join(logstash_root, 'conf.available')
conf_enabled_path = os.path.join(logstash_root, 'conf.d')
grokker_path = os.path.join(logstash_root, 'patterns')


def is_role(role):
    return blueprint.get(role) is not None


@task
def setup():
    """
    Setup Logstash server and/or forwarder
    """
    if is_role('server'):
        install_server()

    if is_role('forwarder'):
        install_filebeat()

    # TMP
    configure()


@task
def configure():
    """
    Configure Logstash server and/or forwarder
    """
    if is_role('server'):
        configure_server()

    if is_role('forwarder'):
        configure_filebeat()


@task
def disable(conf, do_restart=True):
    """
    Disable logstash input/output provider

    :param conf: Input or output provider config file
    :param do_restart: Restart service
    :return: Got disabled?
    """
    disabled = False
    conf = conf if conf.endswith('.conf') else '{}.conf'.format(conf)
    with sudo(), cd(conf_enabled_path):
        if files.is_link(conf):
            info('Disabling conf: {}', conf)
            with silent():
                debian.rm(conf)
                disabled = True
            if do_restart:
                restart('server')
        else:
            warn('Invalid conf: {}'.format(conf))

    return disabled


@task
def enable(conf, weight, do_restart=True):
    """
    Enable logstash input/output provider

    :param conf: Input or output provider config file
    :param weight: Weight of provider
    :param do_restart: Restart service
    :return: Got enabled?
    """
    enabled = False
    conf = conf if conf.endswith('.conf') else '{}.conf'.format(conf)

    with sudo():
        available_conf = os.path.join(conf_available_path, conf)
        if not files.exists(available_conf):
            warn('Invalid conf: {}'.format(conf))
        else:
            with cd(conf_enabled_path):
                weight = str(weight).zfill(2)
                conf = '{}-{}'.format(weight, conf)
                if not files.exists(conf):
                    info('Enabling conf: {}', conf)
                    with silent():
                        debian.ln(available_conf, conf)
                        enabled = True
                    if do_restart:
                        restart('server')

    return enabled


def install_server():
    with sudo():
        branch = blueprint.get('server.branch', '6.x')
        add_elastic_repo(branch)

        version = blueprint.get('server.version', 'latest')
        info('Installing {} version {}', 'logstash', version)
        package = 'logstash' + ('={}'.format(version) if version != 'latest' else '')
        debian.apt_get('install', package)

        # Enable on boot
        debian.add_rc_service('logstash')

        # prep custom folders
        debian.mkdir(conf_available_path)
        debian.mkdir(conf_enabled_path)

        # # Install plugins
        # plugins = blueprint.get('server.plugins', [])
        # for plugin in plugins:
        #     info('Installing logstash "{}" plugin...', plugin)
        #     install_plugin(plugin)

        # # Create and download SSL cert
        # create_server_ssl_cert()
        # download_server_ssl_cert()


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


@task
def install_plugin(name=None):
    if not name:
        abort('No plugin name given')

    with sudo():
        run('/usr/share/logstash/bin/logstash-plugin install {}'.format(name))


def configure_server():
    uploads = []

    # Configure the logstash service
    persistent_queue = blueprint.get('server.persistent_queue', False)
    service_context = {
        'pipeline_workers': blueprint.get('server.workers', 2),
        'queue_type': 'persisted' if persistent_queue else 'memory',
        'metrics_host': blueprint.get('server.metrics_host', 'localhost'),
        'metrics_port': blueprint.get('server.metrics_port', 9600),
    }
    uploads += blueprint.upload('./logstash.yml', logstash_root, service_context)
    uploads += blueprint.upload('./patterns/', grokker_path)

    # Provision filters
    elasticsearch = blueprint.get('server.elasticsearch', 'localhost')
    config_context = {
        'ssl': blueprint.get('ssl', True),
        'elasticsearch': (
            elasticsearch if isinstance(elasticsearch, list) else [elasticsearch]
        )
    }

    uploads += blueprint.upload('./conf/', conf_available_path, config_context)

    # Disable previously enabled conf not configured through config in settings
    config = blueprint.get('server.config', {})
    auto_disable_conf = blueprint.get('server.auto_disable_conf', True)
    changes = []
    if auto_disable_conf:
        with silent():
            enabled_conf_links = run('ls {}'.format(conf_enabled_path)).split()

        conf_prospects = [
            '{}-{}.conf'.format(str(weight).zfill(2), conf)
            for weight, conf in config.iteritems()
        ]

        for link in enabled_conf_links:
            if link not in conf_prospects:
                changed = disable(link, do_restart=False)
                changes.append(changed)

    # Enable conf from settings
    for weight, conf in config.iteritems():
        changed = enable(conf, weight, do_restart=False)
        changes.append(changed)

    if uploads or any(changes):
        restart('server')


def install_filebeat():
    with sudo():
        info('Adding apt repository for FileBeat')
        debian.add_apt_repository('https://packages.elastic.co/beats/apt stable main')

        info('Adding apt key for Elastic.co')
        debian.add_apt_key('https://packages.elastic.co/GPG-KEY-elasticsearch')

        info('Installing FileBeat')
        debian.apt_get_update()
        debian.apt_get('install', 'filebeat')

        # Enable on boot
        debian.add_rc_service('filebeat')


def configure_filebeat():
    output_cfg = {
        'output': {
            'logstash': {
                'hosts': [
                    '{}:5050'.format(s)
                    for s in blueprint.get('forwarder.servers', [])
                ]
            }
        }
    }

    if blueprint.get('ssl', True):
        output_cfg['output']['logstash']['tls'] = {
            'certificate_authorities': [
                '/etc/pki/tls/certs/logstash.crt',
            ]
        }

    prospectors = []
    for doc_type, cfg in blueprint.get('forwarder.files', {}).items():
        prospector = {'document_type': doc_type}

        if isinstance(cfg, dict):
            prospector.update(cfg)

        elif isinstance(cfg, list):
            prospector['paths'] = cfg

        else:
            continue

        prospectors.append(prospector)

    filebeat_cfg = {
        'filebeat': {
            'prospectors': prospectors
        }
    }

    context = {
        'output': yaml.dump(output_cfg),
        'filebeat': yaml.dump(filebeat_cfg)
    }

    uploads = blueprint.upload('./filebeat.yml', '/etc/filebeat/', context=context)

    ssl_path = 'ssl/logstash.crt'
    if not os.path.exists(blueprint.get_user_template_path(ssl_path)):
        download_server_ssl_cert(ssl_path)

    debian.mkdir('/etc/pki/tls/certs')
    uploads += blueprint.upload(ssl_path, '/etc/pki/tls/certs/')

    if uploads:
        restart('forwarder')


def service(target=None, action=None):
    """
    Debian service dispatcher for logstash server and forwarder
    """
    if not target:
        abort('Missing logstash service target argument, start:<server|forwarder|both>')

    if target in ('server', 'both'):
        debian.service('logstash', action, check_status=False)

    if target in ('forwarder', 'both'):
        debian.service('filebeat', action, check_status=False)


start = task(partial(service, action='start'))
stop = task(partial(service, action='stop'))
restart = task(partial(service, action='restart'))

start.__doc__ = 'Start logstash'
stop.__doc__ = 'Stop logstash'
restart.__doc__ = 'Restart logstash'
