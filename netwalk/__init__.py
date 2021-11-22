"Main file for library"

from .interface import Interface
from .switch import Device, Switch
from .fabric import Fabric

__all__ = ["Interface", "Switch", "Fabric", "Device"]


#Taken from requests library, check their documentation
import logging
from logging import NullHandler

logging.getLogger(__name__).addHandler(NullHandler())