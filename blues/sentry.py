"""
Sentry Blueprint
=================

**Fabric environment:**

.. code-block:: yaml

    blueprints:
      - blues.sentry

    settings:
      sentry:
        auth_token: XXXXX
        organization: some-org
        repository: some-repo
        environment: production
        projects:
          - proj-slug
          - other-slug

"""
from fabric.decorators import task
from fabric.utils import warn
from refabric.api import info

from refabric.contrib import blueprints

import urllib2
import json
from datetime import datetime

__all__ = ['notify']


blueprint = blueprints.get(__name__)


@task
def notify(version, from_revision, to_revision,
           date_start=None, date_stop=None):
    """
    Create a Sentry Release and immediately deploy it
    """
    create_release(version, from_revision, to_revision)
    create_deploy(version, date_start, date_stop)


def create_release(version, from_revision, to_revision):
    """
    Docs: https://docs.sentry.io/api/releases/post-organization-releases/
    """
    info('Creating Sentry release')

    repository = blueprint.get('repository', '')
    payload = {
        'version': version,
        'ref': to_revision,
        'refs': [{
            'repository': repository,
            'commit': to_revision,
            'previousCommit': from_revision
        }],
        'dateReleased': _api_datestamp(datetime.now())
    }

    projects = blueprint.get('projects', None)
    if projects:
        payload['projects'] = projects

    endpoint = 'releases/'
    _call_sentry_api(endpoint, payload)


def create_deploy(version, date_start, date_stop):
    """
    Docs: https://docs.sentry.io/api/releases/post-release-deploys/
    """
    info('Creating Sentry deployment')

    environment = blueprint.get('environment', 'unknown')
    payload = {
        'environment': environment,
        'dateStarted': _api_datestamp(date_start or datetime.now()),
        'dateFinished': _api_datestamp(date_start or datetime.now())
    }

    endpoint = 'releases/%s/deploys/' % version
    _call_sentry_api(endpoint, payload)


def _api_datestamp(datetime):
    """ Ensure datestimes conform to RFC3339 """
    return datetime.isoformat(sep='T')


def _call_sentry_api(endpoint, payload):
    token = blueprint.get('auth_token', '')
    organization = blueprint.get('organization', '')

    url = '/api/0/organizations/%s/%s' % (organization, endpoint)
    headers = {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer %s' % token
    }

    try:
        request = urllib2.Request(url, headers=headers)
        urllib2.urlopen(request, data=json.dumps(payload))

    except Exception:
        warn('Sentry API call failed')
