Data model overview
===================

Netwalk defines three objects: Fabric, Switch and Interface.

Fabric
------

A *Fabric* describes a network of interconnected *Switches*. It can be created without parameters

.. code-block:: python

    from netwalk import Fabric
    f = Fabric()




A *Switch* represents a network device (and indeed should be renamed as *Device*, maybe next release?).
Its
