import pickle
import pynetbox
import netwalk
from slugify import slugify
import logging
import ipaddress

logger = logging.getLogger(__name__)
logger.setLevel(level=logging.DEBUG)

ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)

logger.addHandler(ch)

nb = pynetbox.api(
    'http://localhost',
    token='95db86f3b2fe48482bdeee0686051e4451f36665'
)

def create_devices_and_interfaces(fabric):
    # Create devices and interfaces
    site_vlans = nb.ipam.vlans.filter(site_id=nb_site.id)

    vlans_dict = {x['vid']: x for x in site_vlans.response}
    for swname, swdata in fabric.switches.items():
        logger.info("Switch %s", swname)
        nb_device_type = nb.dcim.device_types.get(model=swdata.facts['model'])
        if nb_device_type is None:
            nb_manufacturer = nb.dcim.manufacturers.get(slug=slugify(swdata.facts['vendor']))
            if nb_manufacturer is None:
                nb_manufacturer = nb.dcim.manufacturers.create(name=swdata.facts['vendor'],
                                                           slug=slugify(swdata.facts['vendor']))
            
            nb_device_type = nb.dcim.device_types.create(model=swdata.facts['model'],
                                                         manufacturer=nb_manufacturer.id,
                                                         slug=slugify(swdata.facts['model']))

        nb_device = nb.dcim.devices.get(name=swdata.facts['hostname'])
        if nb_device is None:
            role = nb_core_role if swdata in fabric.cores else nb_access_role
            nb_device = nb.dcim.devices.create(name=swdata.facts['hostname'],
                                               device_role=role.id,
                                               device_type=nb_device_type.id,
                                               site=nb_site.id,
                                               serial_number=swdata.facts['serial_number'])

        for interface in swdata.facts['interface_list']:
            intproperties = {}
            logger.info("Interface %s on switch %s", interface, swname)
            if "Fast" in interface:
                int_type = "100base-tx"
            elif "Te" in interface:
                interface = interface.replace("Te", "TenGigabitEthernet")
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
                intproperties['enabled'] = thisint.is_enabled
            except:
                pass


            nb_interface = nb.dcim.interfaces.get(device_id=nb_device.id,
                                                  name=interface)

            if nb_interface is None:
                nb_interface = nb.dcim.interfaces.create(device=nb_device.id,
                                                         name=interface,
                                                         type=int_type,
                                                         **intproperties)
            else:
                nb_interface.update(intproperties)

            # Create undiscovered CDP neighbors
            try:
                neighbor = swdata.interfaces[interface].neighbors[0]
                assert isinstance(neighbor, dict)
                #assert "AIR" in neighbor['platform']
                logger.debug("Parsing neighbor %s on %s ip %s platform %s", neighbor['hostname'], neighbor['remote_int'], neighbor['ip'], neighbor['platform'])

                try:
                    vendor, model = neighbor['platform'].split()
                except ValueError:
                    model = neighbor['platform']
                    vendor = "Unknown"
                nb_manufacturer = nb.dcim.manufacturers.get(slug=slugify(vendor))

                if nb_manufacturer is None:
                    nb_manufacturer = nb.dcim.manufacturers.create(name=vendor, slug=slugify(vendor))

                nb_device_ap = nb.dcim.devices.get(name=neighbor['hostname'])

                if nb_device_ap is None:
                    nb_device_type = nb.dcim.device_types.get(slug=slugify(model))
                    if nb_device_type is None:
                        nb_device_type = nb.dcim.device_types.create(model=model,
                                                                     manufacturer=nb_manufacturer.id,
                                                                     slug=slugify(model))

                        logger.warning("Created device type " +vendor + " " +model)

                    logger.info("Creating neighbor %s", neighbor['hostname'])
                    nb_device_ap = nb.dcim.devices.create(name=neighbor['hostname'],
                                                          device_role=nb_neigh_role.id,
                                                          device_type=nb_device_type.id,
                                                          site=nb_site.id,
                                                          )

                    logger.info("Creating interface %s on neighbor %s", neighbor['remote_int'], neighbor['hostname'])
                    nb_interface = nb.dcim.interfaces.create(device=nb_device_ap.id,
                                                             name=neighbor['remote_int'],
                                                             type="1000base-t")


                neighbor['nb_device'] = nb_device_ap
                print(neighbor)


            except (AssertionError, KeyError, IndexError):
                pass

def add_ip_addresses(fabric):
    for swname, swdata in fabric.switches.items():
        nb_device = nb.dcim.devices.get(name=swdata.facts['hostname'])
        for intname, intdata in swdata.interfaces.items():
            if len(intdata.address) == 0:
                continue
            nb_interface = nb.dcim.interfaces.get(device_id=nb_device.id,
                                                  name=intname)

            if 'ipv4' in intdata.address:
                for address, addressdata in intdata.address['ipv4'].items():
                    nb_prefix = nb.ipam.prefixes.get(prefix=str(address.network),
                                                    site_id=nb_site.id)

                    logger.info("Checking prefix %s", str(address.network))
                    if nb_prefix is None:
                        logger.info("Creating prefix %s", str(address.network))
                        nb_prefix = nb.ipam.prefixes.create(prefix=str(address.network),
                                                            site=nb_site.id)

                    logger.info("Checking IP %s", str(address))
                    nb_address = nb.ipam.ip_addresses.get(address=str(address),
                                                        site_id=nb_site.id)
                    if nb_address is None:
                        logger.info("Creating IP %s", str(address))
                        nb_address = nb.ipam.ip_addresses.create(address=str(address),
                                                                site=nb_site.id)

                    address_properties = {'assigned_object_type': 'dcim.interface',
                                        'assigned_object_id': nb_interface.id}

                    if addressdata['type'] == 'secondary':
                        address_properties['role'] = 'secondary'

                    nb_address.update(address_properties)

                    if intname == "Vlan901":
                        nb_device.update({'primary_ip4': nb_address.id})
                    elif len(swdata.interfaces_ip.items()) == 1:
                        nb_device.update({'primary_ip4': nb_address.id})

            if 'hsrp' in intdata.address:
                for hsrpgrp, hsrpdata in intdata.address['hsrp'].items():
                    logger.info("Checking HSRP address %s on %s %s", hsrpdata['address'], intdata.switch.facts['hostname'], intdata.name)

                    #Lookup in 'normal' ips to find out address netmask

                    netmask = None
                    for normal_address, normal_adddressdata in intdata.address['ipv4'].items():
                        if hsrpdata['address'] in normal_address.network:
                            netmask = normal_address.network
                    
                    assert netmask is not None, "Could not find netmask for HSRP address" + str(hsrpdata['address'])

                    logger.info("Checking address %s",hsrpdata['address'])
                    nb_hsrp_address = nb.ipam.ip_addresses.get(address=f"{str(hsrpdata['address'])}/{str(normal_address).split('/')[1]}",
                                                               interface_id=nb_interface.id)
                    
                    if nb_hsrp_address is None:
                        logger.info("Creating HSRP address %s", hsrpdata['address'])
                        nb_hsrp_address = nb.ipam.ip_addresses.create(address=f"{str(hsrpdata['address'])}/{str(normal_address).split('/')[1]}",
                                                                     assigned_object_id=nb_interface.id,
                                                                     assigned_object_type='dcim.interface',
                                                                     role='hsrp')


def add_neighbor_ip_addresses(fabric):
    for swname, swdata in fabric.switches.items():
        for intname, intdata in swdata.interfaces.items():
            try:
                neighbor = swdata.interfaces[intname].neighbors[0]
                assert isinstance(neighbor, dict)
            except (AssertionError, KeyError, IndexError):
                continue

            nb_neigh_device = neighbor['nb_device']
            nb_neigh_interface = nb.dcim.interfaces.get(name=neighbor['remote_int'],
                                                        device_id=nb_neigh_device.id)

            try:            
                assert nb_neigh_interface is not None
            except AssertionError:
                nb_neigh_interface = nb.dcim.interfaces.create(device=nb_neigh_device.id,
                                                               name=neighbor['remote_int'],
                                                               type="1000base-t")

                logger.info("Creating interface %s for AP %s, model %s", neighbor['remote_int'], neighbor['hostname'], neighbor['platform'])

            # Search IP
            logger.debug("Searching IP %s", neighbor['ip'])
            nb_neigh_ip = nb.ipam.ip_addresses.get(address=neighbor['ip'])
            if nb_neigh_ip is None:
                # No ip found, figure out smallest prefix configured that contains the IP
                logger.debug("IP %s not found, looking for prefixes", neighbor['ip'])
                nb_prefixes = nb.ipam.prefixes.filter(q=neighbor['ip'])
                if len(nb_prefixes) > 0:
                    # Search smallest prefix
                    prefixlen = 0
                    smallestprefix = None
                    for prefix in nb_prefixes:
                        logger.debug("Checking prefix %s, longest prefix found so far: %s", prefix['prefix'], smallestprefix)
                        thispref = ipaddress.ip_network(prefix['prefix'])
                        if thispref.prefixlen > prefixlen:
                            prefixlen = thispref.prefixlen
                            logger.debug("Found longest prefix found %s", thispref)
                            smallestprefix = thispref

                    assert smallestprefix is not None

                # Now we have the smallest prefix length we can create the ip address

                    finalip = f"{neighbor['ip']}/{smallestprefix.prefixlen}"
                else:
                    finalip = neighbor['ip'] + "/32"
                logger.debug("Creating IP %s", finalip)
                nb_neigh_ip = nb.ipam.ip_addresses.create(address=finalip)

            logger.debug("Associating IP %s to interface %s", nb_neigh_ip.address, nb_neigh_interface.name)
            nb_neigh_ip.update({'assigned_object_type': 'dcim.interface',
                                'assigned_object_id': nb_neigh_interface.id})

            nb_neigh_device.update({'primary_ip4': nb_neigh_ip.id})


def add_l2_vlans(fabric):
    for swname, swdata in fabric.switches.items():
        for vlanid, vlandata in swdata.vlans.items():
            nb_vlan = nb.ipam.vlans.get(vid=vlanid,
                                        site_id=nb_site.id)
            if nb_vlan is None:
                logger.info("Adding vlan %s", vlanid)
                nb_vlan = nb.ipam.vlans.create(vid=vlanid,
                                               name=vlandata['name'],
                                               site=nb_site.id)

        break

def add_cables(fabric):
    for swname, swdata in fabric.switches.items():
        swdata.nb_device = nb.dcim.devices.get(name=swdata.facts['hostname'])
        assert swdata.nb_device is not None

    for swname, swdata in fabric.switches.items():
        sw_cables = [x for x in nb.dcim.cables.filter(device_id=swdata.nb_device.id)]
        for intname, intdata in swdata.interfaces.items():
            try:
                if isinstance(intdata.neighbors[0], netwalk.Interface):
                    nb_term_a = nb.dcim.interfaces.get(device_id=swdata.nb_device.id, name=intname)
                    nb_term_b = nb.dcim.interfaces.get(device_id=intdata.neighbors[0].switch.nb_device.id, name=intdata.neighbors[0].name)

                elif isinstance(intdata.neighbors[0], dict):
                    nb_term_a = nb.dcim.interfaces.get(device_id=swdata.nb_device.id, name=intname)
                    nb_term_b = nb.dcim.interfaces.get(device_id=intdata.neighbors[0]['nb_device'].id, name=intdata.neighbors[0]['remote_int'])
                
                try:
                    for cable in sw_cables:
                        assert nb_term_a != cable.termination_a
                        assert nb_term_a != cable.termination_b
                        assert nb_term_b != cable.termination_a
                        assert nb_term_b != cable.termination_b
                except AssertionError:
                    continue

                logger.info("Adding cable")
                nb_cable = nb.dcim.cables.create(termination_a_type='dcim.interface',
                                                 termination_b_type='dcim.interface',
                                                 termination_a_id=nb_term_a.id,
                                                 termination_b_id=nb_term_b.id)
            except IndexError:
                pass




def main():
    add_l2_vlans(fabric)
    create_devices_and_interfaces(fabric)
    add_ip_addresses(fabric)
    add_neighbor_ip_addresses(fabric)
    add_cables(fabric)


if __name__ == '__main__':
    with open('fabric_data.bin', 'rb') as fabricfile:
        fabric = pickle.load(fabricfile)

    nb_access_role = nb.dcim.device_roles.get(name="Access Switch")
    nb_core_role = nb.dcim.device_roles.get(name="Core Switch")
    nb_neigh_role = nb.dcim.device_roles.get(name="Access Point")
    nb_site = nb.dcim.sites.get(name="Caselle")
    main()
