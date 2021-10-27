.. Netwalk documentation master file, created by
   sphinx-quickstart on Tue Oct 26 11:24:15 2021.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

Netwalk
=======

Netwalk is a Python library born out of a large remadiation project aimed at making network device discovery and management as fast and as painless as possible.

Usage is quite straightforward:

.. code-block:: python

   from netwalk import Fabric
   sitename = Fabric()
   sitename.init_from_seed_device(seed_hosts=["10.10.10.1"],
                                 credentials=[("cisco","cisco"),("customer","password")]
                                 napalm_optional_args=[{}, {'transport': 'telnet'}])


This code will start searching from device 10.10.10.1 and will try to log in via SSH with cisco/cisco and then customer/password, first via SSH then Telnet.
Once connected to the switch it will pull and parse the running config, the mac address table and the cdp neighbours, then will start cycling through all neighbours recursively until the entire fabric has been discovered



Installation
------------
You can install napalm with pip:

.. code-block:: bash

    pip install netwalk

Extras
------
A collection of scripts with extra features and examples is stored in the `extras` folder

Code quality
------------
A lot of the code is covered by tests, which also function as examples and self-explanatory documentation on usage.
Check them out on the Github repo.


Documentation
=============


.. toctree::
   :maxdepth: 2

   netwalk
   extras/index
