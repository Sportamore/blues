"""
BIND Blueprint
===============

**Fabric environment:**

.. code-block:: yaml

    blueprints:
      - blues.tuned


    role/tuned/tuned/profilename/tuned.conf
    Sample of config file
    [main]
    summary=Description on service
    include=latency-performance

    [vm]
    transparent_hugepages=never

    [sysctl]
    net.core.busy_read=50
    net.core.busy_poll=50
    net.ipv4.tcp_fastopen=3
    kernel.numa_balancing=0

    [bootloader]
    cmdline=skew_tick=1
"""
import os
from time import time

from fabric.context_managers import cd, settings
from fabric.contrib import files
from fabric.decorators import task, parallel
from fabric.api import put,env,local

from refabric.context_managers import sudo, silent, hide_prefix
from refabric.contrib import blueprints
from refabric.operations import run
from refabric.utils import info

from . import debian

__all__ = [ 'list','active','set', 'configure','setup']


blueprint = blueprints.get(__name__)

config_dir = '/etc/'
tuned_dir = os.path.join(config_dir, 'tuned/')
path=os.getcwd()

@task
def setup():
    install()
    configure()

def install():
    with sudo(), silent():
        debian.apt_get('install', 'tuned')

@task
def list():
    """
    List tuned-adm
    """
    with sudo(), silent():
        for key in run('tuned-adm list').split('\n'):
            info(key)

@task 
def active():
    """
    List active tuned-adm
    """
    with sudo(), silent():
        for key in run('tuned-adm active').split('\n'):
            info(key)
@task 
def set(value):
    """
    Active tuned-adm fab command fab -E env -R role tuned.set:value=sportamore-test
    """
    with sudo(), silent():
        run('tuned-adm profile %s ' % value)
    active()

@task
def configure():
    """
    Configure tuned-adm settings
    """
    with sudo():

        uploads = []

        # Configure application
        uploads.append(blueprint.upload('./tuned/', tuned_dir))

        info("In order to active a profile run fab -E enviroment -R role tuned.set:value=profilename")
        info("You can list avalible profiles with fab -E enviroment -R role tuned.list ")
