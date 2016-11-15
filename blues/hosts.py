"""
Hosts Blueprint
===============
"""
from fabric.decorators import task

from refabric.context_managers import sudo
from refabric.contrib import blueprints

__all__ = ['configure']

blueprint = blueprints.get(__name__)


@task
def configure():
    """
    Configure hosts file
    """
    with sudo():
        blueprint.upload('hosts', '/etc/hosts')
