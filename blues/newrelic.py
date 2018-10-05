"""
NewRelic Server Blueprint
=================

**Fabric environment:**

.. code-block:: yaml

    blueprints:
      - blues.newrelic

    settings:
      newrelic:
        newrelic_key: XXXXX
        infrastructure: false
        plugins:
          - elasticsearch
          - nginx
          - memcached
          - redis
          - rabbitmq
          - uwsgi
"""
from fabric.decorators import task
from fabric.utils import warn
from refabric.api import run, info

from refabric.context_managers import sudo
from refabric.contrib import blueprints

from . import debian, git, python, user

from functools import partial
import urllib2
import json

__all__ = ['start', 'stop', 'restart', 'setup', 'configure']


blueprint = blueprints.get(__name__)


def service(target=None, action=None):
    if blueprint.get('infrastructure', False):
        debian.service('newrelic-infra', action, check_status=False)

    if blueprint.get('sysmon', False):
        debian.service('newrelic-sysmond', action, check_status=False)

    if blueprint.get('plugins', None):
        debian.service('newrelic-plugin-agent', action, check_status=False)


start = task(partial(service, action='start'))
stop = task(partial(service, action='stop'))
restart = task(partial(service, action='restart'))

start.__doc__ = 'Start newrelic agent'
stop.__doc__ = 'Stop newrelic agent'
restart.__doc__ = 'Restart newrelic agent'


@task
def setup():
    """
    Install and configure newrelic server
    """
    install()
    configure()
    start()


def install():

    user.create_service_user('newrelic')
    debian.mkdir('/etc/newrelic/')
    debian.mkdir('/var/log/newrelic', owner='newrelic')
    debian.mkdir('/var/run/newrelic', owner='newrelic')

    if blueprint.get('infrastructure', False):
        install_infra()

    if blueprint.get('sysmon', False):
        install_agent()

    if blueprint.get('plugins', None):
        install_plugin_agent()


def install_infra():
    with sudo():
        info('Adding apt repository for Newrelic')
        codename = debian.lsb_codename()
        repo_addr = '[arch=amd64] http://download.newrelic.com/infrastructure_agent/linux/apt {} main'.format(codename)
        debian.add_apt_repository(repo_addr)

        info('Adding newrelic apt key')
        debian.add_apt_key('https://download.newrelic.com/infrastructure_agent/gpg/newrelic-infra.gpg')
        debian.apt_get('update')

        info('Installing newrelic-infra')
        debian.apt_get('install', 'newrelic-infra')


def install_agent():
    with sudo():
        info('Adding apt repository for Newrelic')
        debian.add_apt_repository(
            'http://apt.newrelic.com/debian/ newrelic non-free')
        info('Adding newrelic apt key')
        debian.add_apt_key('https://download.newrelic.com/548C16BF.gpg')
        debian.apt_get('update')
        info('Installing newrelic-sysmond')
        debian.apt_get('install', 'newrelic-sysmond')

        debian.chmod('/var/log/newrelic', owner='newrelic', recursive=True)


def install_plugin_agent():
    with sudo():
        python.install()
        python.pip('install', 'newrelic-plugin-agent')

        if debian.lsb_release() == '16.04':
            blueprint.upload('newrelic-plugin-agent.service',
                             '/etc/systemd/system/newrelic-plugin-agent.service')
        else:
            blueprint.upload('newrelic-plugin-agent.init',
                             '/etc/init.d/newrelic-plugin-agent')
            debian.chmod('/etc/init.d/newrelic-plugin-agent', '755')



@task
def configure():
    """
    Configure newrelic server
    """
    if blueprint.get('infrastructure', False):
        configure_infra()

    if blueprint.get('sysmon', False):
        configure_agent()

    if blueprint.get('plugins', None):
        configure_plugin_agent()


def configure_infra():
    with sudo():
        info('Adding license key to config')
        context = {"newrelic_key": blueprint.get('newrelic_key', None)}
        blueprint.upload('newrelic-infra.yml',
                         '/etc/newrelic-infra.yml',
                         context=context)


def configure_agent():
    with sudo():
        info('Adding license key to config')
        newrelic_key = blueprint.get('newrelic_key', None)
        run('nrsysmond-config --set license_key={}'.format(newrelic_key))


def configure_plugin_agent():
    enabled_plugins = blueprint.get('plugins', [])
    if len(enabled_plugins):
        with sudo():
            newrelic_key = blueprint.get('newrelic_key', None)

            context = {p: True for p in enabled_plugins}
            context["newrelic_key"] = newrelic_key

            blueprint.upload('newrelic-plugin-agent.cfg',
                             '/etc/newrelic/newrelic-plugin-agent.cfg',
                             context=context)


def deploy(revision, description, changes=None):
    """
    Sends deploy event to newrelic
    """
    event_key = blueprint.get('event_key', "")
    app_id = blueprint.get('app_id', "")

    if not app_id:
        # Not configured, abort silently.
        return False

    elif not event_key:
        warn('Not configured')
        return False

    info('Creating NewRelic deployment')

    deployer = git.get_local_commiter()
    payload = {
        'deployment': {
            'revision': revision,
            'description': description,
            'changelog': changes or '',
            'user': deployer
        }
    }

    url = 'https://api.newrelic.com/v2/applications/{}/deployments.json'.format(app_id)
    headers = {
        'x-api-key': event_key,
        'Content-Type': 'application/json'
    }

    try:
        request = urllib2.Request(url, headers=headers)
        urllib2.urlopen(request, data=json.dumps(payload))

    except Exception:
        warn('NewRelic deployment failed')
