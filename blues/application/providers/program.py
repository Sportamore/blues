from refabric.contrib import blueprints
from .base import ManagedProvider
from refabric.api import run, info

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

    def configure_web(self):
        return self.configure()

    def configure_worker(self):
        return self.configure()

    def configure(self):
        return self.manager.configure_provider(self,
                                               self.get_context(),
                                               program_name=self.project)
