"""
Beats Blueprint
==================

**Fabric environment:**

.. code-block:: yaml

    blueprints:
      - blues.beats

    settings:
      beats:
        # branch: 6.x                    # Major Version of beats (Default: 6.x)
        # version: latest                # Speciifc version of beats to install (Default: latest)

        logstash:                        # One or more target hosts
          - some.host.tld

        environment: undefined           # An optional environment to tag emssages with

        filebeat:
          plugins:                       # One or more plugins to activate
            - system

          inputs:                        # One or more file blocks
            nginx-access:                # The log_type to add to the event
              - '/var/log/*.log'         # Wildcards are supported

        metricbeat:
          plugins:                       # One or more plugins to activate
            - system

"""
import yaml
import os.path
from functools import partial

from fabric.context_managers import cd
from fabric.decorators import task
from fabric.utils import warn, abort

from refabric.api import run, info
from refabric.context_managers import sudo, silent
from refabric.contrib import blueprints

from . import debian

__all__ = ['setup', 'configure', 'start', 'stop', 'restart']


blueprint = blueprints.get(__name__)


def is_beat(name):
    return blueprint.get(name) is not None


def service(target=None, action=None):
    """
    Debian service dispatcher for logstash server and forwarder
    """
    for beat in ('filebeat', 'metricbeat'):
        if is_beat(beat):
            debian.service('beat', action, check_status=False)


start = task(partial(service, action='start'))
stop = task(partial(service, action='stop'))
restart = task(partial(service, action='restart'))

start.__doc__ = 'Start beats'
stop.__doc__ = 'Stop beats'
restart.__doc__ = 'Restart beats'


@task
def setup():
    """
    Setup beats
    """
    from .elasticsearch import add_elastic_repo

    with sudo():
        branch = blueprint.get('branch', '6.x')
        add_elastic_repo(branch)

        for beat in ('filebeat', 'metricbeat'):
            if is_beat(beat):
                version = blueprint.get('version', 'latest')
                info('Installing {} version {}', beat, version)
                package = beat + ('={}'.format(version) if version != 'latest' else '')
                debian.apt_get('install', package)

    configure()


@task
def configure():
    """
    Configure all available beats
    """
    logstash_hosts = blueprint.get('logstash', [])
    base_context = {
        'logstash': yaml.dump({
            'output.logstash': (
                {
                    'enabled': False
                } if not logstash_hosts else {
                    'hosts': ['{}:5050'.format(host) for host in logstash_hosts]
                }
            )
        }),
        'environment': blueprint.get('environment', 'undefined'),
        'inputs': ''
    }

    uploads = []
    module_changes = []

    if is_beat('filebeat'):
        inputs = blueprint.get('filebeat.inputs', {})
        input_configs = []
        for input_type, input_spec in inputs.iteritems():
            input_conf = {
                'fields_under_root': True,
                'fields': {
                    'application': input_type
                }
            }

            if isinstance(input_spec, list):
                input_conf['paths'] = input_spec

            else:
                input_conf.update(input_spec)

            input_configs.append(input_conf)

        context = base_context.copy()
        if input_configs:
            context['inputs'] = yaml.dump({
                'filebeat.inputs': input_configs
            })

        uploads += blueprint.upload('filebeat.yml',
                                    '/etc/filebeat/filebeat.yml',
                                    context=context)

        module_changes += update_modules('filebeat')

    if is_beat('metricbeat'):
        uploads += blueprint.upload('metricbeat.yml',
                                    '/etc/metricbeat/metricbeat.yml',
                                    context=base_context)

        module_changes += update_modules('metricbeat')

    if uploads or module_changes:
        # restart()
        pass


def update_modules(beat):
    changes = []

    # Get desired state
    desired_modules = set(blueprint.get('{}.modules'.format(beat), []))

    # Get current state
    with silent():
        module_files = run('find /etc/{}/modules.d -iname "*.yml"'.format(beat)).split()
        enabled_modules = {os.path.basename(module).split('.')[0] for module in module_files}

    # Disable extra services
    for extra in enabled_modules - desired_modules:
        info('Disabling {} module: {}', beat, extra)
        changes.append(extra)

        with silent(), sudo():
            run('{} modules disable {}'.format(beat, extra))

    # Enable services
    for missing in desired_modules - enabled_modules:
        info('Enabling {} module: {}', beat, missing)
        changes.append(missing)

        with silent(), sudo():
            run('{} modules enable {}'.format(beat, missing))

    return changes
