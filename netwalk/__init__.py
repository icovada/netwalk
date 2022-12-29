"Main file for library"

#pylint: disable=wrong-import-order
from .device import Device, Switch
from .fabric import Fabric
from .interface import Interface

__all__ = ["Interface", "Switch", "Fabric", "Device"]


# Taken from requests library, check their documentation
import logging
from logging import NullHandler

logging.getLogger(__name__).addHandler(NullHandler())
