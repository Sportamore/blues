"""
Google Cloud SDK Blueprint
===============

**Fabric environment:**

.. code-block:: yaml

    blueprints:
      - blues.gcloud

    settings:
      gcloud:
        linux-user: scs
        service-account-key: |
          {
            "type": "service_account",
            "project_id": "xxxxxxxxx",
            "private_key_id": "5834555xxxxxxxxxxxxxxxxxxxxxxxxxc2772439",
            "private_key": "-----BEGIN PRIVATE KEY-----\nMIxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx\n",
            "client_email": "xxxxxxxxxxx@xxxxxxxxxxxx.iam.gserviceaccount.com",
            "client_id": "xxxxxxxxxxxxxxxxxxxxxxx",
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
            "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/sxxxxxxxxxxxxxxxx%40xxxxxxxxxxxxx.iam.gserviceaccount.com"
          }

"""
from fabric.decorators import task
from refabric.api import info
from refabric.context_managers import sudo, silent, hide_prefix
from refabric.contrib import blueprints
from refabric.operations import run

from . import debian



__all__ = ['setup', 'activate_account']


blueprint = blueprints.get(__name__)

@task
def setup():
    """
    Install and configure Google Cloud SDK
    """
    install()
    activate_account()


def install():
    """
    Install Google Cloud SDK
    """
    with sudo():

        info('Installing prerequisites')
        debian.apt_get('install', 'apt-transport-https ca-certificates gnupg')
        
        info('Adding apt repository for gcloud-sdk')
        gcloud_repo = 'https://packages.cloud.google.com/apt cloud-sdk main'
        debian.add_apt_repository(gcloud_repo)

        gcloud_gpg_key = 'https://packages.cloud.google.com/apt/doc/apt-key.gpg'
        debian.add_apt_key(gcloud_gpg_key)

        debian.apt_get_update()

        info('Installing gcloud SDK')
        debian.apt_get('install', 'google-cloud-sdk')


@task
def activate_account():
    """
    Activate Google Cloud SDK Service Account
    """
    context = {
        'service_account_key': blueprint.get('service-account-key', ''),
    }

    blueprint.upload('gcloud-service-account.json', '/gcloud-service-account.json', context)
    debian.chmod('/gcloud-service-account.json', mode=600, owner=blueprint.get('linux-user', 'root'), group=blueprint.get('linux-user', 'root'))

    with sudo(user=blueprint.get('linux-user', None)):
        run('gcloud auth activate-service-account --key-file=/gcloud-service-account.json')

    debian.rm('/gcloud-service-account.json')
