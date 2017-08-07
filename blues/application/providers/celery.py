import os

from fabric.state import env
from fabric.context_managers import settings

from .base import ManagedProvider
from ..managers.supervisor import SupervisorManager
from ..project import *

from ... import debian
from ...app import blueprint


class CeleryProvider(ManagedProvider):
    name = 'celery'
    default_manager = 'supervisor'

    def install(self):
        pass

    def configure_web(self):
        raise NotImplementedError('celery cannot be configured as a web '
                                  'provider')

    def get_context(self):
        context = super(CeleryProvider, self).get_context()
        context.update({
            'workers': blueprint.get('worker.workers', debian.nproc()),
            'extensions': self.get_extensions(),
        })

        # Override context defaults with blueprint settings
        context.update(blueprint.get('worker'))

        context['celery_group'] = (
            context.get('queues', {}).keys() + context.get('extensions', []))

        return context

    def reload(self):
        self.manager.reload('celery:*')
        for extension in self.get_extensions():
            self.manager.reload(extension)

    def start(self):
        self.manager.start('celery:*')
        for extension in self.get_extensions():
            self.manager.start(extension)

    def stop(self):
        self.manager.stop('celery:*')
        for extension in self.get_extensions():
            self.manager.stop(extension)

    def status(self, project=None):
        self.manager.status('celery:*')
        for extension in self.get_extensions():
            self.manager.status(extension)

    @staticmethod
    def get_extensions():
        # Filter program extensions by host
        enabled_extensions = []

        extensions = blueprint.get('worker.celery.extensions')
        if isinstance(extensions, list):
            # Filter or bad values
            extensions = [extension for extension in extensions if extension]
            for extension in extensions:
                enabled_extensions.append(extension)
        elif isinstance(extensions, dict):
            for extension, extension_host in extensions.items():
                if extension_host in ('*', env.host_string):
                    enabled_extensions.append(extension)

        return enabled_extensions

    def configure_worker(self):
        """
        Render and upload worker program(s) to projects Supervisor home dir.

        :return: Updated programs
        """
        return self.configure()

    def configure(self):
        context = self.get_context()

        template = 'supervisor/default/celery.conf'
        if not hasattr(self.manager, '_upload_provider_template'):
            raise Exception('the celery provider only works with the '
                            'supervisor manager as of now.')

        self.updates.extend(
            self.manager._upload_provider_template(
                template,
                context,
                'celery.conf'))

        return self.updates
