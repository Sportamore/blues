"""
Logstash Blueprint
==================

**Fabric environment:**

.. code-block:: yaml

    blueprints:
      - blues.logstash

    settings:
      logstash:
        use_ssl: true                      # Secure communication between forwarder and server (Default: True)

        server:                            # The presence of this key will cause the host to be considered a server
          version: 2.4                     # Version of the server to install (Default: 2.4)
          elasticsearch_host: localhost    # ES Server address (Default: localhost)
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

__all__ = ['setup', 'configure', 'enable', 'disable', 'start', 'stop', 'restart']


blueprint = blueprints.get(__name__)

logstash_root = '/etc/logstash'
conf_available_path = os.path.join(logstash_root, 'conf.available')
conf_enabled_path = os.path.join(logstash_root, 'conf.d')


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

    configure()


@task
def configure():
    """
    Configure Logstash server and/or forwarder
    """
    if is_role('server'):
        upgrade_server()

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
        version = blueprint.get('server.version', '2.4')
        info('Adding apt repository for {} version {}', 'logstash', version)
        debian.add_apt_repository('https://packages.elastic.co/logstash/{}/debian stable main'.format(version))

        info('Installing {} version {}', 'logstash', version)
        debian.apt_get_update()
        debian.apt_get('install', 'logstash')

        # Enable on boot
        debian.add_rc_service('logstash')

        # Create and download SSL cert
        create_server_ssl_cert()
        download_server_ssl_cert()


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


def configure_server(config, auto_disable_conf=True, **context):
    context.setdefault('use_ssl', True)
    context.setdefault('elasticsearch_host', 'localhost')
    uploads = blueprint.upload('./server/', '/etc/logstash/', context)

    # Disable previously enabled conf not configured through config in settings
    changes = []
    if auto_disable_conf:
        with silent():
            enabled_conf_links = run('ls {}'.format(conf_enabled_path)).split()
        conf_prospects = ['{}-{}.conf'.format(str(weight).zfill(2), conf) for weight, conf in config.iteritems()]
        for link in enabled_conf_links:
            if link not in conf_prospects:
                changed = disable(link, do_restart=False)
                changes.append(changed)

    # Enable conf from settings
    for weight, conf in config.iteritems():
        changed = enable(conf, weight, do_restart=False)
        changes.append(changed)

    return bool(uploads or any(changes))


def upgrade_server():
    config = blueprint.get('server.config', {})
    auto_disable_conf = blueprint.get('server.auto_disable_conf', True)
    context = {
        'use_ssl': blueprint.get('use_ssl', True),
        'elasticsearch_host': blueprint.get('server.elasticsearch_host', '127.0.0.1')
    }

    changed = configure_server(config, auto_disable_conf=auto_disable_conf, **context)

    # Restart logstash if new templates or any conf has been enabled/disabled
    if changed:
        restart('server')


def install_filebeat():
    with sudo():
        info('Adding apt repository for FileBeat')
        debian.add_apt_repository('https://packages.elastic.co/beats/apt stable main')

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
                    '"{}:5050"'.format(s)
                    for s in blueprint.get('forwarder.servers', [])
                ]
            }
        }
    }

    if blueprint.get('ssl', True):
        output_cfg['output']['logstash']["tls"] = {
            'certificate_authorities': [
                '/etc/pki/tls/certs/logstash.crt',
            ]
        }

    filebeat_cfg = {
        'filebeat': {
            'prospectors': [
                {
                    'paths': paths,
                    'document_type': doc_type
                }
                for doc_type, paths
                in blueprint.get('forwarder.files', {}).items()
            ]
        }
    }

    context = {
        'output': yaml.dump(output_cfg),
        'filebeat': yaml.dump(filebeat_cfg)
    }

    uploads = blueprint.upload('./forwarder/',
                               '/etc/filebeat/',
                               context=context)

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
