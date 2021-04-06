# Netwalk

Netwalk is a Python library born out of a large remadiation project aimed at making network device discovery and management as fast and painless as possible.
It is completely object-based and is made out of three parts


## Fabric

This object type defines an entire switched network and can be manually populated, have switches added one by one or you can give it one or more seed devices and it will go and scan everything for you.

#### Auto scanning example:
```python
from netwalk import Fabric
sitename = Fabric()
sitename.init_from_seed_device(seed_hosts=["10.10.10.1"],
                               credentials=[("cisco","cisco"),("customer","password")]
```

This code will start searching from device 10.10.10.1 and will try to log in via SSH with cisco/cisco and then customer/password.
Once connected to the switch it will pull and parse the running config, the mac address table and the cdp neighbours, then will start cycling through all neighbours recursively until the entire fabric has been discovered

### Manual addition of switches
You can tell Fabric to discover another switch on its own or you can add a `Switch` object to `.switches`. WHichever way, do not forget to call `refresh_global_information` to recalculate neighborships and global mac address table

#### Example

```python
sitename.add_switch(seed_hosts=["10.10.10.1"],
                    credentials=[("cisco","cisco"))
sitename.refresh_global_information()
```

### Result

`sitename` will now contain two main attributes:
* `switches`, a dictionary of `{'hostname': Switch}` where Switch an object defined in the next paragraph
* `mac_table`, another dictionary containing a list of all macs in the fabric, the interface closest to them


--------------

## Switch
This object defines a switch. 