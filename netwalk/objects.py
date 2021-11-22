"contains root objects"

from typing import Dict
from netwalk.interface import Interface, Switch
import logging


class Device():
    hostname: str
    #: Dict of {name: Interface}
    interfaces: Dict[str, 'Interface']

    def __init__(self, hostname, **kwargs) -> None:
        self.logger = logging.getLogger(__name__ + hostname)
        self.hostname: str = hostname
        self.interfaces: Dict[str, 'Interface'] = {}

    def add_interface(self, intobject: Interface):
        """Add interface to device

        :param intobject: Interface to add
        :type intobject: netwalk.Interface
        """
        intobject.switch = self
        self.interfaces[intobject.name] = intobject

        if type(self) == Switch:
            for k, v in self.interfaces.items():
                v.parse_config()