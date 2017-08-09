from .base import ManagedProvider

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

        context['fallback'] = fallback = 'queues' not in context

        context['celery_group'] = (
            # queues or fallback worker + extensions
            ('worker' if fallback else context.get('queues', {}).keys()) +
            context.get('extensions', [])
        )

        return context

    def reload(self):
        self.manager.reload('celery:*')

    def start(self):
        self.manager.start('celery:*')

    def stop(self):
        self.manager.stop('celery:*')

    def status(self, project=None):
        self.manager.status('celery:*')

    @staticmethod
    def get_extensions():
        # Filter or bad values
        return [
            extension
            for extension in blueprint.get('worker.celery.extensions', [])
            if extension in {'beat', 'flower'}
        ]

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
