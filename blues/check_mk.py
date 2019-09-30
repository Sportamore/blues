"""
CHECK_MK Bluep1rint
===============

**Fabric environment:**

.. code-block:: yaml

    blueprints:
      - blues.check_mk

    settings:
      check_mk:
         whitelist:
           - 10.130.230.85
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

__all__ = ['start', 'stop', 'restart', 'reload', 'setup', 'configure','upload_plugins']


blueprint = blueprints.get(__name__)

service_name = 'xinetd'
start = debian.service_task(service_name, 'start')
stop = debian.service_task(service_name, 'stop')
restart = debian.service_task(service_name, 'restart')
reload = debian.service_task(service_name, 'reload')

config_dir = '/etc/xinetd.d/'


@task
def setup():
    """
    Install and configure check_mk
    """
    install()
    configure(force_reload=True)


def install():
    with settings(warn_only=True):
        context = {
            'whitelist': blueprint.get('whitelist', '10.130.230.85')
        }
        uploads=[]
        uploads.append(blueprint.upload('check_mk_agent.linux', '/usr/local/bin/check_mk_agent'))
        uploads.append(blueprint.upload('check_mk_caching_agent.linux', '/usr/local/bin/check_mk_caching_agent'))
        test=run("ls -al /etc/|grep xinetd.d")
        if test:
            uploads.append(blueprint.upload('check_mk_template', os.path.join(config_dir, 'check_mk'),context))
        else:
            with sudo():
                debian.apt_get('install', 'xinetd')    
            uploads.append(blueprint.upload('check_mk_template', os.path.join(config_dir, 'check_mk'),context))
        test=run("ls -al /usr/lib/ |grep check_mk_agent")
        if test:
            info("Catalog already exists")
        else:
            debian.mkdir("/usr/lib/check_mk_agent")
               debian.mkdir("/usr/lib/check_mk_agent/plugins")
            info("Catalogs created")
        if uploads:
            debian.chmod("/usr/local/bin/check_mk_agent",mode=755)
            debian.chmod("/usr/local/bin/check_mk_caching_agent",mode=755)
            info("Installed")
@task
def upload_plugins():
    """
    Upload plugins to check_mk
    """
    uploads=[]
    uploads.append(blueprint.upload('plugins/', '/usr/lib/check_mk_agent/plugins'))
    if uploads:
        run("find /usr/lib/check_mk_agent/plugins -not -name '*.py' -exec chmod +x {} \\;")
    with settings(warn_only=True):
        test=run("ls -al /etc/|grep check_mk")
        uploads=[]
        if test:
            uploads.append(blueprint.upload('check_mk/', '/etc/check_mk'))
        else:
            debian.mkdir("/etc/check_mk")
            uploads.append(blueprint.upload('check_mk/', '/etc/check_mk'))
        if uploads:
            info("Uploads are completed")


@task
def configure(force_reload=False):
    """
    Configure check_mk
    """
    context = {
    'whitelist': blueprint.get('whitelist', '10.130.230.85')
    }
    uploads=[]
    uploads.append(blueprint.upload('check_mk_template', os.path.join(config_dir, 'check_mk'),context))
    if uploads:
        info("configure")
    if force_reload:   
        restart()
