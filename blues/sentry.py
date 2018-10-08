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
        environment: production
        projects:
          - proj-slug
          - other-slug

"""
import urllib2
import json
from datetime import datetime

from fabric.decorators import task
from fabric.utils import warn
from refabric.api import info

from refabric.contrib import blueprints

from .application.project import github_repo, github_link


__all__ = ['deploy', 'create_release', 'create_deployment']


blueprint = blueprints.get(__name__)


@task
def deploy(revision, version, date_start=None, date_stop=None):
    """
    Create a Sentry Release and immediately deploy it
    """
    projects = blueprint.get('projects', None)
    if not projects:
        # Not configured, abort silently.
        return False

    create_release(revision, version, projects)
    create_deployment(version, date_start, date_stop)


def create_release(revision, version, projects):
    """
    Docs: https://docs.sentry.io/api/releases/post-organization-releases/
    """
    info('Creating Sentry release: {}', version)

    payload = {
        'version': version,
        'projects': projects,
        'url': github_link() + '/releases',
        'refs': [{
            'repository': github_repo(),
            'commit': revision,
        }]
    }

    endpoint = 'releases/'
    _call_sentry_api(endpoint, payload)


def create_deployment(version, date_start, date_stop):
    """
    Docs: https://docs.sentry.io/api/releases/post-release-deploys/
    """
    environment = blueprint.get('environment', 'unknown')
    info('Deploying sentry release: {} to: {}', version, environment)

    payload = {
        'environment': environment,
        'dateStarted': _api_datestamp(date_start or datetime.now()),
        'dateFinished': _api_datestamp(date_stop or datetime.now())
    }

    endpoint = 'releases/%s/deploys/' % version
    _call_sentry_api(endpoint, payload)


def _api_datestamp(datetime):
    """ Ensure datestimes conform to RFC3339 """
    return datetime.isoformat(sep='T')


def _call_sentry_api(endpoint, payload):
    token = blueprint.get('auth_token', '')
    organization = blueprint.get('organization', '')

    url = 'https://sentry.io/api/0/organizations/%s/%s' % (organization, endpoint)
    headers = {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer %s' % token
    }

    try:
        request = urllib2.Request(url, headers=headers)
        urllib2.urlopen(request, data=json.dumps(payload))

    except Exception:
        warn('Sentry API call failed')
