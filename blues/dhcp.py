"""
BIND Blueprint
===============

**Fabric environment:**

.. code-block:: yaml

    blueprints:
      - blues.dhcp

    settings:
      dhcp:
        # intefaces:
        #   - enp1.5 #(vlan 5)
        scope:
          - net: 10.1.0.0
        domain: 
          - "sportamore.local"
        routers:
          - 10.1.0.1
        options: 
          - 'domain-search "sportamore.internal","mrf.internal","sportamore.local"

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

__all__ = [ 'start', 'stop', 'restart', 'configure','setup']


blueprint = blueprints.get(__name__)

config_dir = '/etc/dhcp'
dhcp_default_dir = '/etc/default'


service_name='isc-dhcp-server'
start = debian.service_task(service_name, 'start')
stop = debian.service_task(service_name, 'stop')
restart = debian.service_task(service_name, 'restart')
reload = debian.service_task(service_name, 'reload')




@task
def configure():
    """
    Configure sysctl settings
    """
    with sudo():
       

        uploads = []

        # Configure application
        local_params=blueprint.get('interfaces',[])
        uploads.append(blueprint.upload('./isc-dhcp-server',dhcp_default_dir,{"params" : local_params}))
        scopes=blueprint.get('scope',[])
        routers=blueprint.get('routers',[])
        options=blueprint.get('options',[])


        uploads.append(blueprint.upload('./dhcpd.conf', config_dir,{"scopes" : scopes, "routers" : routers, "options" : options}))
   
        info("In order for the new settings to work you need to reboot the system !!")

def install():
    with sudo():
        debian.apt_get('install', 'isc-dhcp-server')
@task
def setup():
    install()
    configure()