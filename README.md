# Netwalk

Netwalk is a Python library born out of a large remadiation project aimed at making network device discovery and management as fast and painless as possible.

## Installation
Can be installed via pip with `pip install netwalk`

### Extras
A collection of scripts with extra features and examples is stored in the `extras` folder

### Code quality
A lot of the code is covered by tests. More will be added in the future

## Fabric

This object type defines an entire switched network and can be manually populated, have switches added one by one or you can give it one or more seed devices and it will go and scan everything for you.

#### Auto scanning example:
```python
from netwalk import Fabric
sitename = Fabric()
sitename.init_from_seed_device(seed_hosts=["10.10.10.1"],
                               credentials=[("cisco","cisco"),("customer","password")]
                               napalm_optional_args=[{'secret': 'cisco'}, {'transport': 'telnet'}])
```

This code will start searching from device 10.10.10.1 and will try to log in via SSH with cisco/cisco and then customer/password.
Once connected to the switch it will pull and parse the running config, the mac address table and the cdp neighbours, then will start cycling through all neighbours recursively until the entire fabric has been discovered

Note: you may also pass a list of `napalm_optional_args`, check the [NAPALM optional args guide](https://napalm.readthedocs.io/en/latest/support/#optional-arguments) for explanation and examples

### Manual addition of switches
You can tell Fabric to discover another switch on its own or you can add a `Switch` object to `.switches`. WHichever way, do not forget to call `refresh_global_information` to recalculate neighborships and global mac address table

#### Example

```python
sitename.add_switch(host="10.10.10.1",
                    credentials=[("cisco","cisco"))
sitename.refresh_global_information()
```
Note: you may also pass a list of `napalm_optional_args`, check the [optional args guide](https://napalm.readthedocs.io/en/latest/support/#optional-arguments) for explanation and examples
### Structure

`sitename` will now contain two main attributes:
* `switches`, a dictionary of `{'hostname': Switch}`
* `mac_table`, another dictionary containing a list of all macs in the fabric, the interface closest to them


--------------

## Switch
This object defines a switch. It can be created in two ways:

#### Automatic connection
``` python
from netwalk import Switch
sw01 = Switch(hostname="10.10.10.1")
sw01.retrieve_data(username="cisco",
                   password="cisco"})
```
Note: you may also pass a list of `napalm_optional_args`, check the [optional args guide](https://napalm.readthedocs.io/en/latest/support/#optional-arguments) for explanation and examples

This will connect to the switch and pull all the data much like `add_switch()` does in `Fabric`

### Init from show run
You may also generate the Switch device from a show run you have extracted somewhere else. This will not give you mac address table or neighborship discovery but will generate all Interfaces in the switch

``` python
from netwalk import Switch

showrun = """
int gi 0/1
switchport mode access
...
int gi 0/24
switchport mode trunk
"""

sw01 = Switch(hostname="10.10.10.1", config=showrun)
```

### Structure
A `Switch` object has the following attributes:
* `hostname`: the IP or hostname to connect to
* `config`: string containing plain text show run
* `interfaces`: dictionary of `{'interface name', Interface}`}
* `mac_table`: a dictionary containing the switch's mac address table 


## Interface
An Interface object defines a switched interface ("switchport" in Cisco language) and can hold data about its configuration such as:

 * `name`
 * `description`
 * `mode`: either "access" or "trunk"
 * `allowed_vlan`: a `set()` of vlans to tag
 * `native_vlan`
 * `voice_vlan`
 * `switch`: pointer to parent Switch
 * `is_up`: if the interface is active 
 * `is_enabled`: shutdown ot not
 * `config`: its configuration
 * `mac_count`: number of MACs behind it
 * `type_edge`: also known as "portfast"
 * `bpduguard`

Printing an interface yelds its configuration based on its current attributes

## Trick

### Check a trunk filter is equal on both sides
```python
assert int.allowed_vlan == int.neighbors[0].allowed_vlan
```

### Check a particular host is in vlan 10
```python
from netaddr import EUI
host_mac = EUI('00:01:02:03:04:05')
assert fabric.mac_table[host_mac]['interface'].native_vlan == 10
```
