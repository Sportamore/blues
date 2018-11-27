"""
APM Server Blueprint
==================

**Fabric environment:**

.. code-block:: yaml

    blueprints:
      - blues.apmserver

    settings:
      apmserver:
        # branch: 6.x                    # Major Version of beats (Default: 6.x)
        # version: latest                # Speciifc version of beats to install (Default: latest)

        host: localhost                  # Set the host address specifically, (Default localhost)
        port: 8200                       # Event listening port

        token: secrettoken               # Client authentication token (Default: None)

        elasticsearch:                   # ES Server(s) (Default: localhost)
          - localhost

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

start = task(partial(debian.service, 'apm-server', 'start', check_status=False))
stop = task(partial(debian.service, 'apm-server', 'stop', check_status=False))
restart = task(partial(debian.service, 'apm-server', 'restart', check_status=False))

start.__doc__ = 'Start beats'
stop.__doc__ = 'Stop beats'
restart.__doc__ = 'Restart beats'


@task
def setup():
    """
    Setup apm-server
    """
    from .elasticsearch import add_elastic_repo

    with sudo():
        branch = blueprint.get('branch', '6.x')
        add_elastic_repo(branch)

        version = blueprint.get('version', 'latest')
        info('Installing {} version {}', 'apm-server', version)
        package = 'apm-server' + ('={}'.format(version) if version != 'latest' else '')
        debian.apt_get('install', package)

    configure()


@task
def configure():
    """
    Configure apm-server
    """
    es_hosts = ["{}:9200".format(h) for h in blueprint.get('elasticsearch', [])]
    context = {
        'host': "{}:8200".format(blueprint.get('host', 'localhost')),
        'es_hosts': yaml.dump(es_hosts or ['localhost:9200']),
        'token': blueprint.get('token', '')
    }

    changes = blueprint.upload('./apm-server.yml', '/etc/apm-server/', context=context)

    if changes:
        restart()
