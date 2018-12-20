"""
Redis Blueprint
===============

**Fabric environment:**

.. code-block:: yaml

    blueprints:
      - blues.redis

    settings:
      redis:
        # bind: 127.0.0.1       # Set the bind address
        # bgsave: False         # Background snapshots, can be a singe save statement or a list of them
        # appendonly: False
        # maxclients: 10000
        # maxmemory: 1024mb
        # maxmemory_policy: noeviction

"""
from fabric.decorators import task
from refabric.context_managers import sudo, silent, hide_prefix
from refabric.contrib import blueprints
from refabric import api

from . import debian

__all__ = ['start', 'stop', 'restart', 'setup', 'configure', 'info']


blueprint = blueprints.get(__name__)

start = debian.service_task('redis-server', 'start')
stop = debian.service_task('redis-server', 'stop')
restart = debian.service_task('redis-server', 'restart')


@task
def setup():
    """
    Install and configure Redis
    """
    install()
    configure()


def install():
    with sudo():
        debian.apt_get('install', 'redis-server')


@task
def configure():
    """
    Configure Redis
    """
    context = {
        'bind': blueprint.get('bind', '127.0.0.1'),
        'bgsave': ['""', ],
        'maxclients': blueprint.get('maxclients', 10000),
        'maxmemory': blueprint.get('maxmemory', '1024mb'),
        'maxmemory_policy': blueprint.get('maxmemory_policy', 'noeviction'),
        'appendonly': 'yes' if blueprint.get('appendonly', False) else 'no',
    }

    bgsave = blueprint.get('bgsave', False)
    if bgsave:
        if isinstance(bgsave, str):
            bgsave = [bgsave, ]

        context['bgsave'] = bgsave

    uploads = blueprint.upload('redis.conf', '/etc/redis/redis.conf', context)
    debian.chmod('/etc/redis/redis.conf', mode=640, owner='redis', group='redis')

    if uploads:
        restart()


@task
def info(scope=''):
    """
    Get runtime information from redis itself
    """
    with silent(), hide_prefix():
        output = api.run('redis-cli info ' + scope)
        api.info(output)
