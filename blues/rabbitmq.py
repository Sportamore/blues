"""
RabbitMQ Blueprint
==================

**Fabric environment:**

.. code-block:: yaml

    blueprints:
      - blues.rabbitmq

"""
from fabric.decorators import task
from fabric.utils import abort

from refabric.api import run, info
from refabric.context_managers import sudo
from refabric.contrib import blueprints
from fabric.operations import prompt

from . import debian

__all__ = ['start', 'stop', 'restart', 'reload', 'setup', 'setup_users','configure',
           'ctl', 'reset', 'useradd']


blueprint = blueprints.get(__name__)

start = debian.service_task('rabbitmq-server', 'start')
stop = debian.service_task('rabbitmq-server', 'stop')
restart = debian.service_task('rabbitmq-server', 'restart')
reload = debian.service_task('rabbitmq-server', 'reload')


@task
def setup():
    """
    Install Rabbitmq
    """
    if debian.lsb_release() < '14.04':
        install_testing()
    else:
        install_stable()

    blueprint.upload('default/rabbitmq-server',
                     '/etc/default/rabbitmq-server',
                     context={
                        'ulimit': blueprint.get('ulimit', '102400')
                     })

    configure()

    enable_plugins('rabbitmq_management')


def install_stable():
    with sudo():
        debian.apt_get('install', 'rabbitmq-server')


def install_testing():
    package_name = 'rabbitmq-server'
    debian.debconf_set_selections('%s rabbitmq-server/upgrade_previous note' % package_name)

    with sudo():
        info('Adding apt key for {}', package_name)
        run("apt-key adv --keyserver pgp.mit.edu --recv-keys 0x056E8E56")

        info('Adding apt repository for {}', package_name)
        debian.add_apt_repository('http://www.rabbitmq.com/debian/ testing main')
        debian.apt_get_update()

        info('Installing {}', package_name)
        debian.apt_get('install', package_name)


def enable_plugins(plugin):
    with sudo():
        info('Enable {} plugin', plugin)
        output = run('rabbitmq-plugins enable {}'.format(plugin))
        if output.stdout.strip().startswith('The following plugins have been'):
            restart()


@task
def configure():
    """
    Configure Rabbitmq
    """
    uploads = blueprint.upload('rabbitmq/', '/etc/rabbitmq/')
    uploads.extend(blueprint.upload('erlang.cookie',
                                    '/var/lib/rabbitmq/.erlang.cookie',
                                    user='rabbitmq')
                   or [])
    if uploads:
        restart()


@task
def setup_users():
    for username, password in blueprint.get('users', {}).items():
        ctl("add_user '{}' '{}'".format(username, password))
        ctl("add_vhost '{}'".format(username))
        ctl("set_permissions -p '{}' '{}' '.*' '.*' '.*'".format(username, username))


@task
def useradd():
    """
    Add a basic (R/W/A) user account on the default vhost.
    """
    username = prompt('Username:')
    password = prompt('Password:')

    if not username or not password:
        abort('Both username and password are required.')

    ctl("add_user '{}' '{}'".format(username, password))
    ctl("set_permissions '{}' '.*' '.*' '.*'".format(username))


@task
def ctl(command=None):
    """
    Run rabbitmqctl with given command
    :param command: Control command to execute
    """
    if not command:
        abort('No command given, $ fab rabbitmq.ctl:stop_app')

    with sudo():
        run('rabbitmqctl {}'.format(command))


@task
def reset():
    """
    Stop, reset and start app via rabbitmq ctl
    """
    ctl('stop_app')
    ctl('reset')
    ctl('start_app')
