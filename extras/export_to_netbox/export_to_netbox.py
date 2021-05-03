import pickle
import pynetbox
import netwalk
from slugify import slugify
import logging
import ipaddress

logger = logging.getLogger(__name__)
logger.setLevel(level=logging.DEBUG)

nb = pynetbox.api(
    'http://localhost',
    token='d25885197f8a04fabf92aea757fb9f7a896f0b6c'
)

def create_devices_and_interfaces(fabric):
    # Create devices and interfaces
    site_vlans = nb.ipam.vlans.filter(site_id=nb_site.id)

    vlans_dict = {x['vid']: x for x in site_vlans.response}
    for swname, swdata in fabric.switches.items():
        logging.info("Switch %s", swname)
        nb_device_type = nb.dcim.device_types.get(model=swdata.facts['model'])
        if nb_device_type is None:
            nb_manufacturer = nb.dcim.manufacturers.get(name=swdata.facts['vendor'])
            if nb_manufacturer is None:
                nb_manufacturer = nb.dcim.manufacturers.create(name=swdata.facts['vendor'],
                                                           slug=slugify(swdata.facts['vendor']))
            
            nb_device_type = nb.dcim.device_types.create(model=swdata.facts['model'],
                                                         manufacturer=nb_manufacturer.id,
                                                         slug=slugify(swdata.facts['model']))

        nb_device = nb.dcim.devices.get(name=swdata.facts['hostname'])
        if nb_device is None:
            nb_device = nb.dcim.devices.create(name=swdata.facts['hostname'],
                                               device_role=nb_role.id,
                                               device_type=nb_device_type.id,
                                               site=nb_site.id,
                                               serial_number=swdata.facts['serial_number'])

        for interface in swdata.facts['interface_list']:
            intproperties = {}
            logger.info("Interface %s on switch %s", interface, swname)
            if "Fast" in interface:
                int_type = "100base-tx"
            elif "Ten" in interface:
                int_type = "10gbase-x-sfpp"
            elif "Gigabit" in interface:
                int_type = "1000base-t"
            elif "Vlan" in interface:
                int_type = "virtual"
            elif "channel" in interface:
                int_type = "lag"

            try:

                thisint = swdata.interfaces[interface]
                if thisint.description is not None:
                    intproperties['description'] = thisint.description

                if thisint.mode == "trunk":
                    if len(thisint.allowed_vlan) == 4094:
                        intproperties['mode'] = "tagged-all"
                    else:
                        intproperties['mode'] = "tagged"
                        intproperties['tagged_vlans'] = [vlans_dict[x]['id'] for x in thisint.allowed_vlan]
                else:
                    intproperties['mode'] = "access"

                intproperties['untagged_vlan'] = vlans_dict[thisint.native_vlan]['id']
            except:
                pass


            nb_interface = nb.dcim.interfaces.get(device_id=nb_device.id,
                                                  name=interface, **intproperties)

            if nb_interface is None:
                nb_interface = nb.dcim.interfaces.create(device=nb_device.id,
                                                         name=interface,
                                                         type=int_type,
                                                         **intproperties)
            else:
                nb_interface.update(intproperties)

def add_ip_addresses(fabric):
    for swname, swdata in fabric.switches.items():
        nb_device = nb.dcim.devices.get(name=swdata.facts['hostname'])
        for intname, intdata in swdata.interfaces_ip.items():
            nb_interface = nb.dcim.interfaces.get(device_id=nb_device.id,
                                                  name=intname)

            for protocol, addresses in intdata.items():
                for address, properties in addresses.items():
                    ip = ipaddress.ip_interface(f"{address}/{properties['prefix_length']}")
                    nb_prefix = nb.ipam.prefixes.get(prefix=str(ip.network),
                                                     site_id=nb_site.id)
                    logger.info("Checking prefix %s", str(ip.network))
                    if nb_prefix is None:
                        nb_prefix = nb.ipam.prefixes.create(prefix=str(ip.network),
                                                            site=nb_site.id)

                    nb_address = nb.ipam.ip_addresses.get(address=str(ip),
                                                          site_id=nb_site.id)
                    logger.info("Checking IP %s", str(ip))
                    if nb_address is None:
                        nb_address = nb.ipam.ip_addresses.create(address=str(ip),
                                                                 site=nb_site.id)

                    nb_address.update({'assigned_object_type': 'dcim.interface',
                                       'assigned_object_id': nb_interface.id})


def add_l2_vlans(fabric):
    for swname, swdata in fabric.switches.items():
        for vlanid, vlandata in swdata.vlans.items():
            nb_vlan = nb.ipam.vlans.get(vid=vlanid,
                                        site_id=nb_site.id)
            if nb_vlan is None:
                nb_vlan = nb.ipam.vlans.create(vid=vlanid,
                                               name=vlandata['name'],
                                               site=nb_site.id)


def main():
    add_l2_vlans(fabric)
    create_devices_and_interfaces(fabric)
    add_ip_addresses(fabric)


if __name__ == '__main__':
    with open('fabric_data.bin', 'rb') as fabricfile:
        fabric = pickle.load(fabricfile)

    nb_role = nb.dcim.device_roles.get(name="Access Switch")
    nb_site = nb.dcim.sites.get(name="Magreta")
    main()