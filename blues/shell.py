"""
Shell Blueprint
===============

This blueprint configures system-wide shell settings and templates.

**Fabric environment:**

.. code-block:: yaml

    blueprints:
      - blues.shell

    settings:
      shell:
        host_color: red     # Display color of the hostname

"""
from fabric.decorators import task
from fabric.utils import warn, abort

from refabric.api import info
from refabric.contrib import blueprints
from refabric.context_managers import sudo, silent, hide_prefix
from refabric.operations import run

from blues import debian

__all__ = ['setup', 'configure', 'grep']

blueprint = blueprints.get(__name__)


@task
def setup():
    """
    Install prerequisites and deploy profile
    """
    install()
    configure()


def install():
    with sudo():
        debian.apt_get('install', 'bash-completion:')


@task
def configure():
    ansi_colors = {
        'black': '\[\e[30;49m\]',
        'red': '\[\e[31;49m\]',
        'green': '\[\e[32;49m\]',
        'yellow': '\[\e[33;49m\]',
        'blue': '\[\e[34;49m\]',
        'magenta': '\[\e[35;49m\]',
        'cyan': '\[\e[36;49m\]',
        'white': '\[\e[37;49m\]',
        'none': '\[\e[0m\]'
    }

    cfg_color = blueprint.get('host_color', 'green')
    if cfg_color not in ansi_colors:
        warn('Invalid host color, defaulting to green')
        cfg_color = 'green'

    context = {
        'host_color': ansi_colors[cfg_color]
    }

    info('Configuring profile template')
    blueprint.upload('./bashrc', '/etc/skel/.bashrc', context)
    blueprint.upload('./bash_profile', '/etc/skel/.bash_profile')
    blueprint.upload('./bash_aliases', '/etc/skel/.bash_aliases')

    info('Configuring root profile')
    blueprint.upload('./bashrc', '/root/.bashrc', context)
    blueprint.upload('./bash_profile', '/root/.bash_profile')
    blueprint.upload('./bash_aliases', '/root/.bash_aliases')


@task
def grep(needle, haystack, flags="i"):
    """
    Basic file grepping, case-insensitive by default
    """

    if not needle and haystack:
        abort('Missing arguments')

    with hide_prefix(), sudo():
        run('grep{} -e "{}" {}'.format(
            ' -{}'.format(flags) if flags else '',
            needle,
            haystack))

