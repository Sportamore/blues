"""
Curator Blueprint
=======================

**Fabric environment:**

.. code-block:: yaml

    blueprints:
      - blues.curator

    settings:
      curator:
        # branch: 5                        # Major Version of curator (default: 5)
        # version: latest                  # Speciifc version of curator to install

        timeout: 60                        # Default action timeout

        es_hosts:                          # ES Server(s) (Default: localhost)
          - localhost

        actions:
          delete:
            some-index: 7                  # index_prefix: days_to_keep

"""
import yaml

from fabric.decorators import task

from refabric.api import info
from refabric.context_managers import sudo
from refabric.contrib import blueprints

from . import debian

__all__ = ['setup', 'configure']


blueprint = blueprints.get(__name__)


@task
def setup():
    """
    Install Elasticsearch
    """
    install()
    configure()


def install():
    with sudo():
        branch = blueprint.get('branch', '5')
        info('Adding apt repository for {} branch {}', 'curator', branch)

        repository = 'https://packages.elastic.co/curator/{}/debian stable main'.format(branch)
        debian.add_apt_repository(repository)

        info('Adding apt key for', repository)
        debian.add_apt_key('https://packages.elastic.co/GPG-KEY-elasticsearch')
        debian.apt_get_update()

        version = blueprint.get('version', 'latest')
        info('Installing {} version {}', 'elasticsearch-curator', version)
        package = 'elasticsearch-curator' + ('={}'.format(version) if version != 'latest' else '')
        debian.apt_get('install', package)


def yaml_boolean(input):
    return str(input).lower()


@task
def configure():
    """
    Configure Elasticsearch
    """

    actions = [
        {
            'action': 'delete_indices',
            'prefix': prefix,
            'days_gt': days_gt
        }
        for prefix, days_gt
        in blueprint.get('actions.delete', {}).iteritems()
    ]

    context = {
        'es_hosts': yaml.dump(blueprint.get('es_hosts', []) or ['localhost']),
        'timoeut': blueprint.get('timoeut', 60),
        'actions': actions
    }

    debian.mkdir("/etc/curator/", owner='elasticsearch')
    blueprint.upload('./', "/etc/curator/", context=context, user='elasticsearch')
