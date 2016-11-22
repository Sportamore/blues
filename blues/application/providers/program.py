from refabric.contrib import blueprints
from .base import ManagedProvider

blueprint = blueprints.get('blues.app')


class ProgramProvider(ManagedProvider):
    name = 'program'
    default_manager = 'supervisor'

    def install(self):
        pass

    def start(self):
        self.manager.start(self.project)

    def stop(self):
        self.manager.stop(self.project)

    def status(self, name=None):
        self.manager.status(name or self.project)

    def reload(self):
        self.manager.reload(self.project)

    def get_context(self, role='worker'):
        context = super(ProgramProvider, self).get_context()
        context.update({
            'executable': blueprint.get('{}.executable'.format(role)),
        })

        return context

    def configure_web(self):
        return self.configure(role='web')

    def configure_worker(self):
        return self.configure(role='worker')

    def configure(self, role='worker'):
        return self.manager.configure_provider(self,
                                               self.get_context(role),
                                               program_name=self.project)
