"""
Java
====

Installs Oracle's Java JDK

**Fabric environment:**

.. code-block:: yaml

    blueprints:
      - blues.java

    settings:
      java:
        version: 9  # Major version of JDK to install (Default: 8)

"""
from fabric.decorators import task

from refabric.api import info
from refabric.context_managers import sudo
from refabric.contrib import blueprints

from . import debian

__all__ = ['setup']


blueprint = blueprints.get(__name__)


@task
def setup():
    """
    Install Java
    """
    install()


def install():
    with sudo():
        lsb_release = debian.lsb_release()

        if lsb_release in ('14.04', '16.04', '18.04'):
            debian.add_apt_ppa('webupd8team/java', src=True)
            debian.debconf_set_selections(
                'shared/accepted-oracle-license-v1-1 select true',
                'shared/accepted-oracle-license-v1-1 seen true'
            )

            version = blueprint.get('version', '8')
            package = 'oracle-java{}-installer'.format(version)
            info('Install Java JDK')

        else:
            info('Openjdk')
            version = blueprint.get('version', '8')
            package = 'openjdk-{}-jdk'.format(version)
            package2 = 'openjdk-{}-jre'.format(version)
            info('Install Java JDK')
            debian.apt_get('install', package2)
        
        debian.apt_get('install', package)
