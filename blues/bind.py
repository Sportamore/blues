"""
BIND Blueprint
===============

**Fabric environment:**

.. code-block:: yaml

    blueprints:
      - blues.bind

    settings:
      bind:
        # listen:
        #   - 127.0.0.1
        # allow-query:
        #   - 127.0.0.1
        # allow-reqursion:
        #   - 127.0.0.1
        # forwarders:
        #   - "8.8.8.8"
        #   - "8.8.4.4"
        zones:
          - company.local
          - some.other.zone

"""
import os
from time import time

from fabric.context_managers import cd, settings
from fabric.contrib import files
from fabric.decorators import task, parallel

from refabric.context_managers import sudo, silent, hide_prefix
from refabric.contrib import blueprints
from refabric.operations import run
from refabric.utils import info

from . import debian

__all__ = ['start', 'stop', 'restart', 'reload', 'setup', 'configure']


blueprint = blueprints.get(__name__)

service_name = 'bind9'
start = debian.service_task(service_name, 'start')
stop = debian.service_task(service_name, 'stop')
restart = debian.service_task(service_name, 'restart')
reload = debian.service_task(service_name, 'reload')

config_dir = '/etc/bind/'
zones_dir = os.path.join(config_dir, 'zones')
reverse_dir = os.path.join(config_dir, 'reverse')


@task
def setup():
    """
    Install and configure Bind
    """
    install()
    configure(force_reload=True)


def install():
    with sudo():
        debian.apt_get('install', 'bind9')


@task
def configure(force_reload=False):
    """
    Configure Bind
    """
    with sudo():
        debian.mkdir(zones_dir)
        debian.mkdir(reverse_dir)

        uploads = []

        # Configure application
        uploads.append(blueprint.upload('./named.conf.main',
                                        os.path.join(config_dir, 'named.conf')))
        uploads.append(blueprint.upload('./named.conf.default-zones',
                                        config_dir))

        options_ctx = {
            'listen': blueprint.get(
                'listen', ['127.0.0.1']),
            'allow_query': blueprint.get(
                'allow-query', ['127.0.0.1']),
            'allow_recursion': blueprint.get(
                'allow-recursion', ['127.0.0.1']),
            'forwarders': blueprint.get(
                'forwarders', ['8.8.8.8', '8.8.4.4'])
        }
        uploads.append(blueprint.upload(
            './named.conf.options', config_dir, options_ctx))

        uploads.append(blueprint.upload(
            './zones/', zones_dir))

        # Zones
        serial = int(time())
        ttl = blueprint.get('ttl', 604800)

        zones = blueprint.get('zones', [])
        local_zones = {}
        for zone in zones:
            filename = 'db.{}'.format(zone)
            file_path = os.path.join(zones_dir, filename)
            local_zones[zone] = file_path
            uploads.append(blueprint.upload(
                filename,
                file_path,
                {
                    'zone': zone,
                    'serial': serial,
                    'ttl': ttl
                }
            ))

        uploads.append(blueprint.upload(
            './named.conf.local', config_dir, {'zones': local_zones}))

        slave_zones = blueprint.get('slave', [])
        uploads.append(blueprint.upload(
            './named.conf.slave', config_dir, {'slave_zones': slave_zones}))

        if uploads or force_reload:
            reload()
