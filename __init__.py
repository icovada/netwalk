"Main file for library"

from .netwalk.interface import Interface
from .netwalk.switch import Switch
from .netwalk.fabric import Fabric

__all__ = ["Interface", "Switch", "Fabric"]


#Taken from requests library, check their documentation
import logging
from logging import NullHandler

logging.getLogger(__name__).addHandler(NullHandler())