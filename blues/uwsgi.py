"""
uWSGI Blueprint
===============

Installs uWSGI and contains service tasks and other useful helpers for other blueprints to use.
Currently only acts as a provider for the application blueprint and can not be used standalone to deploy vassals.

**Fabric environment:**

.. code-block:: yaml

    blueprints:
      - blues.uwsgi

    settings:
      uwsgi:
        version: 2.0.8  # Version of uWSGI to install (Required)
        # emperor: /etc/uwsgi/vassals (Default: /srv/app/*/uwsgi.d)

"""
import os
import json
from datetime import datetime

from fabric.decorators import task
from fabric.utils import warn

from refabric.api import run, info
from refabric.context_managers import sudo, hide_prefix, silent
from refabric.contrib import blueprints

from . import debian
from . import python

__all__ = ['start', 'stop', 'restart', 'reload', 'status', 'setup', 'configure', 'top', 'fifo']


blueprint = blueprints.get(__name__)

log_path = '/var/log/uwsgi'
tmpfs_path = '/run/uwsgi/'

start = debian.service_task('uwsgi', 'start')
stop = debian.service_task('uwsgi', 'stop')
restart = debian.service_task('uwsgi', 'restart')


@task
def setup():
    """
    Install uWSGI system wide and upload vassals
    """
    install()
    configure()


def install():
    with sudo():
        # Ensure python (pip) is installed
        python.install()

        # PIP install system wide uWSGI
        package = 'uwsgi'
        version = blueprint.get('version')
        if version:
            package += '=={}'.format(version)
        info('Installing: {} ({})', 'uWSGI', version if version else 'latest')
        python.pip('install', package)
        python.pip('install', 'uwsgitop', 'gevent')

        # Create group
        debian.groupadd('app-data', gid_min=10000)

        # Create directories
        debian.mkdir(log_path, owner='root', group='app-data', mode=1775)
        debian.mkdir(tmpfs_path, owner='root', group='app-data', mode=1775)


@task
def configure():
    """
    Upload vassals
    """
    with sudo():
        # Upload templates
        blueprint.upload('init/', '/etc/init/')


@task
def top(vassal_name=None):
    """
    Launch uwsgitop for vassal stats socket

    :param vassal_name: The vassal to show stats for (Default: project setting)
    """
    # TODO: fix missing output
    with sudo(), hide_prefix():
        vassal = vassal_name or blueprint.get('project')
        stats_path = os.path.join(tmpfs_path, '{}-stats.sock'.format(vassal))
        run('uwsgitop {}'.format(stats_path))


@task
def fifo(vassal_name, command):
    """
    Issue FIFO commands to a vassal.

    :param vassal_name: The vassal to command
    :param command: The FIFO command to issue

    See: http://uwsgi-docs.readthedocs.org/en/latest/MasterFIFO.html
    """
    fifo_file = '/run/uwsgi/fifo-{}'.format(vassal_name)
    with sudo(), silent():
        run('echo {} > {}'.format(command, fifo_file))


@task
def reload(vassal_path=None):
    """
    Reload uwsgi or reload specific vassal @ path, via touch.

    :param vassal_path: The absolute path to vassal ini to reload. If not given, the uwsgi service will reload
    """
    if not vassal_path:
        debian.service('uwsgi', 'reload', check_status=False)
    else:
        vassal_name = os.path.splitext(os.path.basename(vassal_path))[0]
        with sudo():
            info('Reloading {} uWSGI vassal', vassal_name)
            run('touch {}'.format(vassal_path))


@task
def status(vassal_name=None):
    """
    Get basic stats from UWSGI
    """
    with sudo(), silent():
        vassal = vassal_name or blueprint.get('project')
        stats_path = os.path.join(tmpfs_path, '{}-stats.sock'.format(vassal))
        try:
            stats = json.loads(run('uwsgi --connect-and-read {}'.format(stats_path)))
            for worker_stats in stats['workers']:
                start_time = datetime.fromtimestamp(worker_stats['last_spawn'])
                uptime = datetime.now().replace(microsecond=0) - start_time
                info('Worker {}, status: {}, uptime: {!s}'.format(
                    worker_stats['pid'],
                    worker_stats['status'],
                    uptime))

        except Exception:
            warn('Unable to read UWSGI stats')


def get_worker_count(cores):
    """
    Get number of workers to run depending on server core count
    """
    return cores * 2


def get_cpu_affinity(cores, workers=None):
    """
    Get CPU affinity depending on server core count
    http://lists.unbit.it/pipermail/uwsgi/2011-March/001594.html
    """
    workers = workers or get_worker_count(cores)
    if workers <= 4:
        return 1
    elif cores < 8:
        return 2
    else:
        return 3


def get_max_requests(gb_memory):
    """
    Get max_requests setting depending on server memory in GB
    """
    return gb_memory * 2000


def get_reload_on_as(gb_memory):
    """
    Get reload_on_as setting depending on server memory in GB
    """
    return gb_memory * 256


def get_reload_on_rss(gb_memory):
    """
    Get reload_on_rss setting depending on server memory in GB
    """
    return get_reload_on_as(gb_memory) / 2


def get_limit_as(gb_memory):
    """
    Get limit_as setting depending on server memory in GB
    """
    return gb_memory * 512
