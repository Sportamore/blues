"""
BIND Blueprint
===============

**Fabric environment:**

.. code-block:: yaml

    blueprints:
      - blues.logrotate

      Config files in logrotate.d 

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

__all__ = [ 'list','force_run','configure','setup']


blueprint = blueprints.get(__name__)

config_dir = '/etc/'
logrotate_dir = os.path.join(config_dir, 'logrotate.d/')
path=os.getcwd()

@task
def setup():
    install()
    configure()

def install():
    with sudo(), silent():
        debian.apt_get('install', 'logrotate')

@task
def list():
    """
    List logrotate files
    """
    with sudo(), silent():
        for key in run("ls /etc/logrotate.d/").split('\n'):
            info(key)
@task
def force_run(value):
    """
    Run a logrotate.d file force_run:value=uwsgi
    """
    with sudo():
        run('logrotate -v -f /etc/logrotate.d/%s' % value)
@task
def configure():
    """
    Configure logrotate
    """
    with sudo():

        uploads = []

        # Configure application
        uploads.append(blueprint.upload('./logrotate.d/', logrotate_dir))
