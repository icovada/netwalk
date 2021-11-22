"contains root objects"

from typing import Dict
from netwalk.interface import Interface
import logging


class Device():
    hostname: str
    #: Dict of {name: Interface}
    interfaces: Dict[str, 'Interface']

    def __init__(self, hostname, **kwargs) -> None:
        self.logger = logging.getLogger(__name__ + hostname)
        self.hostname: str = hostname
        self.interfaces: Dict[str, 'Interface'] = {}