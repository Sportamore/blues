"""
Cron Blueprint
==============

This blueprint has no settings.
Templates are handled as crontabs and should be named after related user.

**Fabric environment:**

.. code-block:: yaml

    blueprints:
      - blues.cron

"""
import os

from fabric.decorators import task
from fabric.utils import abort

from refabric.context_managers import sudo, silent, hide_prefix
from refabric.contrib import blueprints
from refabric.operations import run
from refabric.utils import info

from blues import debian

__all__ = ['configure', 'disable', 'status']


blueprint = blueprints.get(__name__)


@task
def configure():
    """
    Install crontab per template (i.e. user)
    """
    with sudo(), silent():
        with debian.temporary_dir(mode=555) as temp_dir:
            updates = blueprint.upload('./', temp_dir)
            for update in updates:
                user = os.path.basename(update)
                info('Installing new crontab for {}...', user)
                run('crontab -u {} {}'.format(user, os.path.join(temp_dir, user)))


@task
def disable(user=None):
    """
    Removes the crontab for a single user
    """
    if not user:
        abort('Please specify user account')

    with sudo():
        info('Disabling crontab for {}...', user)
        run('crontab -r -u {}'.format(user))


@task
def status(user=None):
    """
    Dumps the crontab for a single user
    """
    if not user:
        abort('Please specify user account')

    info('Current crontab for {}:', user)
    with sudo(), hide_prefix():
        run('crontab -l -u {}'.format(user))
