"""
Supervisor Blueprint
====================

Can be used as a provider to the application blueprint,
or used standalone by adding program templates under a `programs-available`
and enable them manually with the `programs` setting.

**Fabric environment:**

.. code-block:: yaml

    blueprints:
      - blues.supervisor

    settings:
      supervisor:
        version: 3.1.3                 # Version of supervisor to install (Required)
        # programs:                    # List of programs/templates in `programs-available` folder to enable (Optional)
        #   - foo                      # Template name, with or without .conf extension
        #   - bar
        # auto_disable_programs: true  # Auto disable programs not specified in `programs` setting (Default: true)

"""
from functools import partial
import os

from fabric.context_managers import cd
from fabric.contrib import files
from fabric.decorators import task
from fabric.utils import puts, warn

from refabric.api import run, info
from refabric.context_managers import sudo, silent
from refabric.contrib import blueprints

from . import debian
from . import python

__all__ = ['start', 'stop', 'restart', 'reload', 'setup', 'configure',
           'enable', 'disable', 'ctl', 'status']


blueprint = blueprints.get(__name__)

supervisord_root = '/etc/supervisord'
programs_available_path = os.path.join(supervisord_root, 'programs-available')
programs_enabled_path = os.path.join(supervisord_root, 'programs-enabled')
log_path = '/var/log/supervisord'
tmpfs_path = '/run/supervisord'


@task
def setup():
    """
    Install Supervisor and enable/disable configured programs
    """
    install()
    configure()
    debian.add_rc_service('supervisor')


def install():
    with sudo():
        # Ensure python (pip) is installed
        python.install()

        # PIP install system wide Supervisor
        package = 'supervisor'
        version = blueprint.get('version')

        if version:
            package += '=={}'.format(version)

        info('Installing: {} ({})', 'Supervisor', (version
                                                   if version
                                                   else 'latest'))

        # Revent versions of uwsgi depends on a modern version of pip ( >=9 )
        python.update_pip(quiet=True)
        python.pip('install', package, bin='pip2', quiet=True)

        # Create group
        debian.groupadd('app-data', gid_min=10000)

        # Create directories
        for d in (programs_available_path,
                  programs_enabled_path,
                  log_path,
                  tmpfs_path):
            debian.mkdir(d, owner='root', group='app-data', mode=1775)


@task
def configure():
    """
    Enable/disable configured programs
    """
    with sudo():
        # Upload service templates
        if debian.lsb_release() == '14.04':
            uploads = blueprint.upload('init/supervisor.conf', '/etc/init/supervisor.conf')
            blueprint.upload('init.d/supervisor','/etc/init.d/supervisor')
            debian.chmod('/etc/init.d/supervisor',mode=755)
        else:
            uploads = blueprint.upload('systemd/supervisor.service', '/etc/systemd/system/supervisor.service')
            uploads = blueprint.upload('tmpfiles.d/supervisor.conf', '/etc/tmpfiles.d/supervisor.conf')
            debian.systemd_daemon_reload()

        uploads.extend(blueprint.upload('supervisord.conf', '/etc/') or [])
        uploads.extend(blueprint.upload('programs-available/',
                                        programs_available_path + '/') or [])

        # Disable previously enabled programs not configured programs-enabled
        changes = []
        programs = blueprint.get('programs') or []
        auto_disable = blueprint.get('auto_disable_programs', True)
        if auto_disable:
            with silent():
                enabled_program_links = run(
                    'ls {}'.format(programs_enabled_path)).split()

            for link in enabled_program_links:
                link_name = os.path.splitext(link)[0]  # Without extension
                if link not in programs and link_name not in programs:
                    changed = disable(link, do_reload=False)
                    changes.append(changed)

        # Enable programs from settings
        for program in programs:
            changed = enable(program, do_reload=False)
            changes.append(changed)

        # Reload supervisor if new templates or any program has been
        # enabled/disabled.
        if uploads or any(changes):
            reload()


@task
def disable(program, do_reload=True):
    """
    Disable program.

    :param program: Program to disable
    :param do_reload: Reload supervisor
    :return: Got disabled?
    """
    disabled = False

    if not (program.endswith('.conf') or program == 'default'):
        program = '{}.conf'.format(program)

    with sudo(), cd(programs_enabled_path):
        if files.is_link(program):
            info('Disabling program: {}', program)
            with silent():
                debian.rm(program)
                disabled = True
            if do_reload:
                reload()
        else:
            warn('Invalid program: {}'.format(program))

    return disabled


@task
def enable(program, do_reload=True):
    """
    Enable program.

    :param program: Program to enable
    :param do_reload: Reload supervisor
    :return: Got enabled?
    """
    enabled = False

    if not (program.endswith('.conf') or program == 'default'):
        program = '{}.conf'.format(program)

    with sudo():
        available_program = os.path.join(programs_available_path, program)
        if not files.exists(available_program):
            warn('Invalid program: {}'.format(program))
        else:
            with cd(programs_enabled_path):
                if not files.exists(program):
                    info('Enabling program: {}', program)
                    with silent():
                        debian.ln(available_program, program)
                        enabled = True
                    if do_reload:
                        reload()

    return enabled


def supervisorctl(command, program=''):
    with sudo():
        return run('supervisorctl {} {}'.format(command, program or ''))


def service(command, program=None):
    if not program:
        debian.service('supervisor', command)
    else:
        supervisorctl(command, program)


@task
def reload(program=None):
    """
    Reload supervisor or restart programs

    :param program: The program to start (all|exact|pattern). If not given,
        the supervisor service will reload.
    """
    info('Reloading {}', program or 'supervisord')
    if not program:
        service('reload')

    else:
        service('restart', program=program)


@task
def ctl(command, program=''):
    """
    Run supervisorctl :[command],[program]

    :param command: The command to run
    :param program: The program to run command against
    """
    with silent():
        puts('supervisorctl {} {}'.format(command, program))
        output = supervisorctl(command, program=program)
        for line in output.split('\n'):
            info(line)


@task
def status(program=''):
    """
    Show program(s) status, shortcut to supervisorctl status

    :param program: Optional program to query status
    """
    ctl('status', program=program)


start = task(partial(service, 'start'))
stop = task(partial(service, 'stop'))
restart = task(partial(service, 'restart'))

start.__doc__ = 'Start supervisor or start program(s)'
stop.__doc__ = 'Stop supervisor or stop program(s)'
restart.__doc__ = 'Stop supervisor or restart program(s)'
