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
        plugins:
          - elasticsearch
          - nginx
          - memcached
          - redis
          - rabbitmq
          - uwsgi
"""
from fabric.decorators import task
from refabric.api import run, info

from refabric.context_managers import sudo
from refabric.contrib import blueprints
from .application.project import python_path


from . import debian, git, python

from functools import partial
import urllib2
import urllib
import json

__all__ = ['start', 'stop', 'restart', 'setup', 'configure']


blueprint = blueprints.get(__name__)


def service(target=None, action=None):
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

        if blueprint.get('plugins', None):
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
    enabled_plugins = blueprint.get('plugins', [])

    with sudo():
        info('Adding license key to config')
        newrelic_key = blueprint.get('newrelic_key', None)
        run('nrsysmond-config --set license_key={}'.format(newrelic_key))

        if len(enabled_plugins):
            context = {p: True for p in enabled_plugins}
            context["newrelic_key"] = newrelic_key
            blueprint.upload('newrelic-plugin-agent.cfg',
                             '/etc/newrelic/newrelic-plugin-agent.cfg',
                             context=context)


def send_deploy_event(payload=None):
    """
    Sends deploy event to newrelic
    payload = json.dumps({ 'deployment': {
            'description': new_tag,
            'revision': commit_hash,
            'changelog': changes,
            'user': deployer,
            }
    })
    :param payload: payload is a json dict with newrelic api info
    :return:
    """
    newrelic_key = blueprint.get('newrelic_event_key', None)
    app_id = blueprint.get('app_id', None)

    if all([newrelic_key, app_id]):
        url = 'https://api.newrelic.com/v2/applications/{}/deployments.json' \
              ''.format(app_id)
        headers = {
            'x-api-key': newrelic_key,
            'Content-Type': 'application/json'
        }

    if all([newrelic_key, app_id]):
        url = 'https://api.newrelic.com/v2/applications/{}/deployments.json'.format(app_id)
        headers = {
            'x-api-key': newrelic_key,
            'Content-Type': 'application/json'
        }

        if not payload:
            path = python_path()
            commit_hash = git.get_commit(path, short=True)
            new_tag, old_tag = git.get_two_most_recent_tags(path)
            changes = git.log_between_tags(path, old_tag, new_tag)
            deployer = git.get_local_commiter()

            payload = json.dumps({
                'deployment': {
                    'description': new_tag,
                    'revision': commit_hash,
                    'changelog': changes,
                    'user': deployer,
                }
            })

        request = urllib2.Request(url, headers=headers)
        urllib2.urlopen(request, data=payload)
        info('Deploy event sent')
    else:
        for i in ['app_id', 'newrelic_key']:
             if not locals().get(i, None):
                 info('missing key: {}'.format(i))
        for i in ['app_id', 'newrelic_event_key']:
             if not locals().get(i, None):
                 info('missing key: {}'.format(i))