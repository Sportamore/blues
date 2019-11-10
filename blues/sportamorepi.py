# coding=utf-8
"""
Sportamore-pi Blueprint
=================

**Fabric environment:**

.. code-block:: yaml

    settings:
      sportamorepi:
        endpoint: EEEE
        user: XXXXX
        password: YYYY

"""
import requests
from refabric.contrib import blueprints
from fabric.utils import warn
from refabric.api import info


__all__ = ['toggle_blender']


blueprint = blueprints.get(__name__)


TIMEOUT = 3


def toggle_blender():
    config = blueprint.get('')

    if not config:
        info('No config for Sportamore blender')
        return

    endpoint = config.get('endpoint')
    user = config.get('endpoint')
    password = config.get('password')

    info('Toggling Sportamore blender')
    try:
        requests.post(endpoint, timeout=TIMEOUT, auth=(user, password))
    except Exception as e:
        warn('Toggling Sportamore blender failed ({})', e)
