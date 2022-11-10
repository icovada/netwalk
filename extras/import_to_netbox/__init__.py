"""
netwalk
Copyright (C) 2021 NTT Ltd

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""


import os
import pickle
import logging
import ipaddress
import argparse
from netaddr import EUI, mac_unix_expanded, mac_cisco
from netaddr.core import AddrFormatError
import pynetbox
from pynetbox.core.query import RequestError
from slugify import slugify
import netwalk

logger = logging.getLogger(__name__)
logger.setLevel(level=logging.DEBUG)

ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)

logger.addHandler(ch)


nwlogger = logging.getLogger('netwalk')
nwlogger.setLevel(level=logging.DEBUG)

nb = pynetbox.api(
    os.getenv("NETBOX_URL"),
    token=os.getenv("NETBOX_TOKEN")
)

nb.http_session.verify = True if os.getenv(
    'HTTPS_VERIFY', "").lower() == 'true' else False


class NetboxInterface(netwalk.Interface):
    _netbox_object = None

    @property
    def nb_interface(self):
        if self._netbox_object is None:
            self._netbox_object = nb.dcim.interfaces.get(name=self.name, device_id=self.device.nb_device.id)

        return self._netbox_object

    @nb_interface.setter
    def nb_interface(self, value):
        self._netbox_object = value

class NetboxDevice(netwalk.Device):
    _netbox_object = None

    @property
    def nb_device(self):
        if self._netbox_object is None:
            self._netbox_object = self.get_device_by_hostname_or_mac(
                os.getenv('SITE_SLUG'))

        return self._netbox_object

    @nb_device.setter
    def nb_device(self, value):
        self._netbox_object = value

    def get_device_by_hostname_or_mac(self, site=None):
        """
        Get devices either by hostname or mac of an interface
        Meraki APs advertise their mac as CDP hostname
        """

        if isinstance(self, netwalk.Device):
            if self.hostname == "":
                raise ValueError("Device has no hostname")
            hostname = self.hostname
        else:
            if self == "":
                raise ValueError("Device has no hostname")
            hostname = self

        try:
            ipaddress.ip_address(hostname)
        except ValueError:
            pass

        if site is None:
            nb_device = nb.dcim.devices.get(name=hostname)
        else:
            nb_device = nb.dcim.devices.get(name=hostname, site=site)

        if nb_device is not None:
            return nb_device

        mac_address = None
        try:
            mac_address = EUI(hostname)
            nb_interface = list(nb.dcim.interfaces.filter(mac_address=str(mac_address)))
            
            if len(nb_interface) == 1:
                nb_interface = nb_interface[0]
            else:
                raise AssertionError

            nb_device = nb_interface.device
            hostname = nb_device.name
            return nb_device

        except (AssertionError, RequestError, AddrFormatError):
            try:
                if site is None:
                    nb_device = nb.dcim.devices.get(name=hostname)
                else:
                    nb_device = nb.dcim.devices.get(name=hostname, site=site)

                if mac_address is not None:
                    # hostname is a mac, no need to continue any further
                    # either we get it or we don't
                    return nb_device

                if nb_device is None:
                    if site is None:
                        nb_device = nb.dcim.devices.filter(name__isw=hostname)
                    else:
                        nb_device = nb.dcim.devices.filter(
                            name__isw=hostname, site=site)

                    if nb_device is not None:
                        alldevs = list(nb_device)
                        if len(alldevs) > 1:
                            for dev in alldevs:
                                if len(dev.name) == 40:
                                    dev.delete()

                        nb_device = None

                    if nb_device is None:
                        if site is None:
                            nb_device = nb.dcim.devices.get(
                                name__isw=hostname[:40])
                        else:
                            nb_device = nb.dcim.devices.get(
                                name__isw=hostname[:40], site=site)

                        if nb_device is None:
                            domain_hierarchy = hostname.split(".")
                            subdomains = len(domain_hierarchy)-1
                            while nb_device is None and subdomains != 0:
                                smaller_name = ".".join(
                                    domain_hierarchy[:subdomains])
                                if site is None:
                                    nb_device = nb.dcim.devices.get(
                                        name=smaller_name)
                                else:
                                    nb_device = nb.dcim.devices.get(
                                        name=smaller_name, site=site)
                                subdomains -= 1

                return nb_device
            except (KeyError, IndexError):
                return None


class NetboxSwitch(NetboxDevice, netwalk.Switch):
    pass

class NetboxOTDevice(NetboxDevice):
    pass

def add_active_vlans():
    "Add active vlan list in config context data"
    done = []

    for swname, swdata in fabric.devices.items():
        if swdata in done:
            continue

        done.append(swdata)
        if isinstance(swdata, netwalk.Switch):
            if swdata.nb_device is None:
                continue

            active_vlans = swdata.get_active_vlans()
            for intname, intdata in swdata.interfaces.items():
                for neigh in intdata.neighbors:
                    if isinstance(neigh, NetboxDevice):
                        if "AP" in neigh.hostname:
                            active_vlans.add(214)
                            
            active_vlan_list = list(active_vlans)
            active_vlan_list.sort()

            if swdata.nb_device.local_context_data is None:
                swdata.nb_device.local_context_data = {}
            swdata.nb_device.local_context_data.update(
                {'active_vlans': active_vlan_list})

            if swdata.nb_device.save():
                logger.info("Updated config context for  %s", swdata.hostname)
                swdata.nb_device.full_details()


def create_devices_and_interfaces(nb_site, delete):
    "Create devices and interfaces"
    site_vlans = nb.ipam.vlans.filter(site_id=nb_site.id)
    vlans_dict = {x.vid: x for x in site_vlans}

    done = []
    unknown_device_type = nb.dcim.device_types.get(
        model="Unknown")

    for swname, swdata in fabric.devices.items():
        if swdata in done:
            continue

        done.append(swdata)

        nb_device_type = unknown_device_type

        if isinstance(swdata, netwalk.Switch):
            logger.info("Switch %s", swdata.hostname)
            if swdata.facts is not None:
                nb_device_type = nb.dcim.device_types.get(
                    model=swdata.facts['model'])

            if nb_device_type is None:
                nb_manufacturer = nb.dcim.manufacturers.get(
                    slug=slugify(swdata.facts['vendor']))
                if nb_manufacturer is None:
                    nb_manufacturer = nb.dcim.manufacturers.create(name=swdata.facts['vendor'],
                                                                   slug=slugify(swdata.facts['vendor']))

                nb_device_type = nb.dcim.device_types.create(model=swdata.facts['model'],
                                                             manufacturer=nb_manufacturer.id,
                                                             slug=slugify(swdata.facts['model']))

            if swdata.nb_device is None:
                data = {'name': swdata.hostname,
                        'device_role': nb_access_role.id,
                        'device_type': nb_device_type.id,
                        'site': nb_site.id}

                if swdata.facts is not None:
                    data['serial'] = swdata.facts['serial_number'].split(",")[
                        0]

                swdata.nb_device = nb.dcim.devices.create(**data)
            else:
                try:
                    assert swdata.nb_device.device_type.model == swdata.facts['model']
                    assert swdata.nb_device.serial == swdata.facts['serial_number']
                except AssertionError:
                    logger.warning("Switch %s changed model from %s to %s",
                                   swdata.hostname, swdata.nb_device.device_type.display, swdata.facts['model'])
                    swdata.nb_device.device_type = nb_device_type.id
                    swdata.nb_device.serial = swdata.facts['serial_number'][:50]
                except TypeError:
                    # most likelky no facts
                    logger.warning("Switch %s has no data, skipping",
                                   swdata.hostname)

            if swdata.nb_device.name != swdata.hostname:
                swdata.nb_device.name = swdata.hostname

            if swdata.nb_device.save():
                swdata.nb_device.full_details()

        elif isinstance(swdata, NetboxOTDevice):
            logger.info("Device %s", swdata.hostname)
            if swdata.nb_device is None:
                swdata.nb_device = nb.dcim.devices.create(name=swdata.hostname,
                                                          device_role=nb_ot_role.id,
                                                          device_type=nb_device_type.id,
                                                          site=nb_site.id)
        else:
            logger.info("Device %s", swdata.hostname)
            if swdata.nb_device is None:
                swdata.nb_device = nb.dcim.devices.create(name=swdata.hostname,
                                                          device_role=nb_access_role.id,
                                                          device_type=nb_device_type.id,
                                                          site=nb_site.id)

        # Create new interfaces
        for intname, intdata in swdata.interfaces.items():
            if intdata.nb_interface is None:
                intproperties = {'custom_fields': {}}
                if intdata.mac_address != '':
                    intproperties['mac_address'] = intdata.mac_address
                logger.info("Interface %s on switch %s",
                            intname, swdata.hostname)
                if isinstance(swdata, netwalk.Switch):
                    if "Fast" in intname:
                        int_type = "100base-tx"
                    elif "App" in intname:
                        int_type = 'virtual'
                    elif "Te" in intname:
                        int_type = "10gbase-x-sfpp"
                    elif "TwentyFive" in intname:
                        int_type = "25gbase-x-sfp28"
                    elif "Hundred" in intname:
                        int_type = "100gbase-x-qsfp28"
                    elif "Gigabit" in intname:
                        int_type = "1000base-t"
                    elif "Vlan" in intname:
                        int_type = "virtual"
                    elif "channel" in intname:
                        int_type = "lag"
                    else:
                        int_type = 'virtual'

                else:
                    int_type = "1000base-t"

                if isinstance(intdata.device, netwalk.Switch):
                    if intdata.description is not None:
                        intproperties['description'] = intdata.description

                    if intdata.mode == "trunk":
                        if len(intdata.allowed_vlan) == 4094:
                            intproperties['mode'] = "tagged-all"
                        else:
                            intproperties['mode'] = "tagged"
                            intproperties['tagged_vlans'] = []
                            for x in intdata.allowed_vlan:
                                try:
                                    intproperties['tagged_vlans'].append(
                                        vlans_dict[x].id)
                                except KeyError:
                                    logger.warning(
                                        "VLAN %s not found for switch %s interface %s", x, swname, intname)
                    else:
                        intproperties['mode'] = "access"

                    if "vlan" in intname.lower():
                        vlanid = int(intname.lower().replace("vlan", ""))
                        intproperties['untagged_vlan'] = vlans_dict[vlanid].id
                    else:
                        intproperties['untagged_vlan'] = vlans_dict[intdata.native_vlan].id

                    intproperties['enabled'] = intdata.is_enabled
                    intproperties['custom_fields']['bpduguard'] = intdata.bpduguard
                    intproperties['custom_fields']['type_edge'] = intdata.type_edge
                    intproperties['custom_fields']['mac_count'] = intdata.mac_count

                    if intdata.unparsed_lines is not None:
                        if len(intdata.unparsed_lines) > 0:
                            intproperties['custom_fields']['unparsed_lines'] = intdata.unparsed_lines

                if isinstance(intdata.device, NetboxOTDevice):
                    if "switch" in str(swdata.nb_device.device_role).lower():
                        # This is a switch masquerading as OT device
                        logger.warning("Nevermind, %s is a switch", swdata.hostname)
                        continue

                intdata.nb_interface = nb.dcim.interfaces.create(device=swdata.nb_device.id,
                                                                 name=intname,
                                                                 type=int_type,
                                                                 **intproperties)

                # If this is a port channel, tag child interfaces, if they exist
                if "Port-channel" in intname:
                    for childintdata in intdata.child_interfaces:
                        child = nb.dcim.interfaces.get(
                            device_id=swdata.nb_device.id, name=childintdata.name)
                        if child is not None and child.lag is not None:
                            if child.lag.id != intdata.nb_interface.id:
                                logger.info("Adding %s under %s",
                                            intname, intdata.nb_interface.name)
                                child.update({'lag': intdata.nb_interface.id})

            else:
                if delete:
                    if len(intdata.neighbors) == 0:
                        if intdata.nb_interface.cable is not None:
                            logger.info(
                                "Deleting old cable on %s", intdata.name)
                            intdata.nb_interface.cable.delete()

                if isinstance(intdata.device, netwalk.Switch):
                    if intdata.mac_address is None:
                        intdata.nb_interface.mac_address = None
                    elif intdata.mac_address == "":
                        intdata.nb_interface.mac_address = None
                    else:
                        intdata.nb_interface.mac_address = str(EUI(intdata.mac_address, dialect=mac_unix_expanded)).upper()
                    intdata.nb_interface.description = intdata.nb_interface.description

                    if intdata.mode == 'trunk':
                        if len(intdata.allowed_vlan) == 4094:
                            intdata.nb_interface.mode = 'tagged-all'
                        else:
                            intdata.nb_interface.mode = 'tagged'

                            sorted_nb_tagged_vlans = [
                                x.id for x in intdata.nb_interface.tagged_vlans]
                            sorted_intdata_allowed_vlans = []
                            for x in intdata.allowed_vlan:
                                try:
                                    sorted_intdata_allowed_vlans.append(
                                        vlans_dict[x].id)
                                except KeyError:
                                    logger.warning(
                                        "VLAN %s not found for switch %s interface %s", x, swname, intname)

                            sorted_nb_tagged_vlans.sort()
                            sorted_intdata_allowed_vlans.sort()

                            if sorted_nb_tagged_vlans != sorted_intdata_allowed_vlans:
                                intdata.nb_interface.tagged_vlans = sorted_intdata_allowed_vlans

                    elif intdata.mode == 'access':
                        intdata.nb_interface.mode = 'access'

                    try:
                        intdata.nb_interface.untagged_vlan = vlans_dict[intdata.native_vlan]
                    except KeyError:
                        logger.error("VLAN %s on interface %s %s does not exist",
                                     intdata.native_vlan, intdata.name, intdata.device.hostname)
                        continue

                    intdata.nb_interface.enabled = intdata.is_enabled

                    intdata.nb_interface.custom_fields.update({'bpduguard': intdata.bpduguard,
                                                               'type_edge': intdata.type_edge})

                    if intdata.unparsed_lines is not None:
                        if len(intdata.unparsed_lines) == 0:
                            intdata.unparsed_lines = None

                    intdata.nb_interface.custom_fields.update({'unparsed_lines': intdata.unparsed_lines})
                    
                    if intdata.nb_interface.custom_fields['mac_count'] is None:
                        intdata.nb_interface.custom_fields.update({'mac_count': 0})
                        
                    if intdata.nb_interface.custom_fields['mac_count'] < intdata.mac_count:
                        intdata.nb_interface.custom_fields.update({'mac_count': intdata.mac_count})

                    if "Port-channel" in intname:
                        for childint in intdata.child_interfaces:
                            if childint.nb_interface is not None:
                                if childint.nb_interface.lag is None:
                                    logger.info("Adding %s under %s",
                                                childint.name, intdata.nb_interface.name)
                                    childint.nb_interface.update({'lag': intdata.nb_interface.id})
                                elif childint.nb_interface.lag.id != intdata.nb_interface.id:
                                    logger.info("Adding %s under %s",
                                                childint.name, intdata.nb_interface.name)
                                    childint.nb_interface.update({'lag': intdata.nb_interface.id})

                    if intdata.nb_interface.save():
                        logger.info("Updated interface %s on %s with %s",
                                    intname, swdata.hostname, intdata.nb_interface.updates())
                        intdata.nb_interface.full_details()
                        
                if isinstance(intdata.device, NetboxOTDevice):
                    intdata.nb_interface.mac_address = str(EUI(intdata.device.hostname, dialect=mac_unix_expanded)).upper()
                    if intdata.nb_interface.save():
                        logger.info("Updated %s %s to %s", intdata.device.hostname, intdata.name, intdata.nb_interface.updates())
                        
        # Delete interfaces that no longer exist
        if delete:
            nb_all_interfaces = {
                x.name: x for x in nb.dcim.interfaces.filter(device=swdata.nb_device)}

            for k, v in nb_all_interfaces.items():
                if k not in swdata.interfaces:
                    logger.info("Deleting interface %s from %s",
                                k, swdata.hostname)
                    v.delete()


def add_ip_addresses(nb_site, delete):
    "Add IP address"
    done = []

    def add_ip_to_interface(nb_interface, address, addressdata):
        logger.info("Checking IP %s", str(address))
        all_device_addresses.append(address)
        
        if address == ipaddress.ip_address("1.1.1.1"):
            return

        if address not in nb_device_addresses:
            # We need to check how big the prefix is so we can create the IP with the appropriate subnet length
            logger.info("Checking prefix %s",
                        str(address))

            nb_prefix = None

            if isinstance(address, (ipaddress.IPv4Interface, ipaddress.IPv6Interface)):
                # It's a straight-up ip with netmask. We're done
                nb_prefix = nb.ipam.prefixes.get(prefix=str(address.network),
                                                 site_id=nb_site.id)
            else:
                # Get all prefixes, find the smallest
                nb_prefix_list = list(nb.ipam.prefixes.filter(q=str(address),
                                                              site_id=nb_site.id))
                if len(nb_prefix_list) > 0:
                    # Last should be smallest
                    nb_prefix = nb_prefix_list[-1]

            if nb_prefix is None:
                logger.info("Creating prefix %s",
                            str(address))
                if isinstance(address, (ipaddress.IPv4Interface, ipaddress.IPv6Interface)):
                    nb_prefix = nb.ipam.prefixes.create(prefix=str(address.network),
                                                        site=nb_site.id,
                                                        vlan=nb_interface.untagged_vlan.id)
                else:
                    logger.warning(
                        "Cannot create prefix for unknown length netmask")

            if isinstance(address, (ipaddress.IPv4Interface, ipaddress.IPv6Interface)):
                address_w_netmask = str(address)
                address_no_netmask = str(address.ip)
            else:
                if nb_prefix is not None:
                    prefix_length = nb_prefix.prefix.split("/")[1]
                else:
                    prefix_length = "32"

                address_w_netmask = str(address) + "/" + prefix_length
                address_no_netmask = str(address)

            logger.info("Checking IP %s", str(address_w_netmask))
            try:
                nb_address = nb.ipam.ip_addresses.get(address=str(address_no_netmask),
                                                      site_id=nb_site.id)
            except ValueError:
                logger.error("ERROR: Address %s is duplicate, removing them all",
                             address_w_netmask)
                for address in nb.ipam.ip_addresses.filter(address=str(address_no_netmask), site_id=nb_site.id):
                    if address.role is None:
                        address.delete()

                nb_address = None

            if nb_address is None:
                logger.info("Creating IP %s", str(address_w_netmask))
                nb_address = nb.ipam.ip_addresses.create(address=str(address_w_netmask),
                                                         site=nb_site.id)

            nb_device_addresses[address] = nb_address

        nb_address = nb_device_addresses[address]
        newdata = {}
        if nb_address.assigned_object_type != 'dcim.interface':
            newdata['assigned_object_type'] = 'dcim.interface'
        if nb_address.assigned_object_id != nb_interface.id:
            newdata['assigned_object_id'] = nb_interface.id

        role = None if addressdata['type'] == 'primary' else addressdata['type']

        if nb_address.role != role:
            newdata['role'] = role

        if len(newdata) > 0:
            logger.info("Updating address %s", address)
            try:
                nb_address.update(newdata)
            except RequestError as e:
                # The request failed with code 400 Bad Request: {'interface': ['IP address is primary for device SWBB-2-SI-24 but not assigned to it!']}
                if "Switch" in str(nb_address.assigned_object.device.device_role):
                    # This is a proper switch with parsed config, don't change
                    logger.warning("NOT overriding %s from %s to %s", str(nb_address), str(nb_address.assigned_object.device), (nb_interface.device))
                    pass
                else:
                    nb_address.delete()
                    logger.warning(
                        "%s", str(e))
                    nb_address = nb.ipam.ip_addresses.create(address=str(address_w_netmask),
                                                            site=nb_site.id)
                    nb_device_addresses[address] = nb_address
                    if nb_address.assigned_object_type != 'dcim.interface':
                        newdata['assigned_object_type'] = 'dcim.interface'
                    if nb_address.assigned_object_id != nb_interface.id:
                        newdata['assigned_object_id'] = nb_interface.id
                    role = None if addressdata['type'] == 'primary' else addressdata['type']

                    nb_address.update(newdata)
        
    for swname, swdata in fabric.devices.items():
        logger.info("Checking IP for device %s", swname)
        if swdata in done:
            continue

        done.append(swdata)

        if swdata.nb_device is None:
            continue

        nb_device_addresses = {ipaddress.ip_interface(
            x): x for x in nb.ipam.ip_addresses.filter(device_id=swdata.nb_device.id)}
        all_device_addresses = []
        
        if isinstance(swdata, NetboxSwitch):
            # Cycle through interfaces, see if the IPs on them are configured
            for intname, intdata in swdata.interfaces.items():
                try:
                    assert hasattr(intdata, 'address')
                    assert len(intdata.address) != 0
                    assert intdata.nb_interface is not None
                except AssertionError:
                    continue

                if 'ipv4' in intdata.address:
                    for address, addressdata in intdata.address['ipv4'].items():
                        add_ip_to_interface(intdata.nb_interface, address, addressdata)

                if 'hsrp' in intdata.address and 'groups' in intdata.address['hsrp']:
                    for hsrpgrp, hsrpdata in intdata.address['hsrp']['groups'].items():
                        try:
                            assert 'address' in hsrpdata
                        except AssertionError:
                            continue

                        logger.info("Checking HSRP address %s on %s %s",
                                    hsrpdata['address'], intdata.device.hostname, intdata.name)

                        # Lookup in 'normal' ips to find out address netmask

                        netmask = None

                        if 'ipv4' in intdata.address:
                            for normal_address, normal_adddressdata in intdata.address['ipv4'].items():
                                if hsrpdata['address'] in normal_address.network:
                                    netmask = normal_address.network

                        try:
                            assert netmask is not None, "Could not find netmask for HSRP address  " + \
                                str(hsrpdata['address'])
                        except AssertionError:
                            continue

                        logger.info("Checking address %s", hsrpdata['address'])
                        try:
                            hsrp_addr_obj = ipaddress.ip_interface(
                                str(hsrpdata['address'])+"/" + str(normal_address).split('/')[1])
                            all_device_addresses.append(hsrp_addr_obj)
                            assert hsrp_addr_obj in nb_device_addresses
                        except AssertionError:
                            logger.info("Creating HSRP address %s",
                                        hsrpdata['address'])
                            nb_hsrp_address = nb.ipam.ip_addresses.create(address=str(hsrp_addr_obj),
                                                                          assigned_object_id=intdata.nb_interface.id,
                                                                          assigned_object_type='dcim.interface',
                                                                          role='hsrp')
                            nb_device_addresses[hsrp_addr_obj] = nb_hsrp_address
        
        elif isinstance(swdata, NetboxOTDevice):
            try:
                nb_interface = nb.dcim.interfaces.get(name="Ethernet", device_id=swdata.nb_device.id)
                if nb_interface is not None:
                    add_ip_to_interface(nb_interface, swdata.mgmt_address, {'type': 'primary'})
                else:
                    continue
            except KeyError:
                # This is an OT device which is actually a switch
                continue
  
        elif isinstance(swdata, NetboxDevice):
            if swdata.mgmt_address is None:
                logger.warning("%s has no IP", swdata.hostname)
                continue
            
            if len(swdata.interfaces) > 1:
                logger.warning("Device %s has more than one interface", swname)
            
            try:
                nb_address = nb.ipam.ip_addresses.get(address=str(swdata.mgmt_address))
            except ValueError:
                for ip in nb.ipam.ip_addresses.filter(address=str(swdata.mgmt_address)):
                    logger.warning("Remove IP %s from %s because duplicate", str(ip), swname)
                    ip.delete()
                    
            try:
                if nb_address.assigned_object.device.id == swdata.nb_device.id:
                    logger.info("IP %s already assigned to %s", nb_address, swname)
                    continue
            except AttributeError:
                # nb_address has no assigned object
                for intname, intdata in swdata.interfaces.items():
                    add_ip_to_interface(intdata.nb_interface, swdata.mgmt_address, {'type': 'primary'})
                    logger.info("Assign IP %s to %s int %s", nb_address, swname, intname)
                    # only add to first and hope for the best
                    break
            except UnboundLocalError:
                # nb_address is None
                pass

            for intname, intdata in swdata.interfaces.items():
                add_ip_to_interface(intdata.nb_interface, swdata.mgmt_address, {
                                    'type': 'primary'})
        else:
            continue
        
        # Refresh, might have changed above
        nb_device_addresses = {ipaddress.ip_interface(
            x): x for x in nb.ipam.ip_addresses.filter(device_id=swdata.nb_device.id)}
        
        for k, v in nb_device_addresses.items():
            if k not in all_device_addresses:
                if delete:
                    logger.warning(
                        "Deleting old address %s from %s", k, swdata.hostname)
                    ip_to_remove = nb.ipam.ip_addresses.get(
                        q=str(k), device_id=swdata.nb_device.id)
                    ip_to_remove.delete()
            else:
                if swdata.nb_device.primary_ip4 != v:
                    if v.assigned_object is not None:
                        if ipaddress.ip_interface(v).ip == swdata.mgmt_address:
                            if v.role is None:
                                swdata.nb_device.primary_ip4 = v.id
                                if swdata.nb_device.save():
                                    logger.info(
                                        "Assign %s as primary ip for %s", v, swdata.hostname)
                                    swdata.nb_device.full_details()


def add_l2_vlans(nb_site, delete):
    "Add L2 VLANs"
    nb_all_vlans = [x for x in nb.ipam.vlans.filter(site_id=nb_site.id)]
    vlan_dict = {x.vid: x for x in nb_all_vlans}
    for swname, swdata in fabric.devices.items():
        if isinstance(swdata, netwalk.Switch):
            if swdata.vlans is None:
                continue

            for vlanid, vlandata in swdata.vlans.items():
                if int(vlanid) not in vlan_dict:
                    logger.info("Adding vlan %s", vlanid)
                    nb_vlan = nb.ipam.vlans.create(vid=vlanid,
                                                   name=vlandata['name'],
                                                   site=nb_site.id)
                    vlan_dict[int(vlanid)] = nb_vlan


def add_cables():
    """Add cables"""
    logger.info("Adding cables")
    done = []

    for swname, swdata in fabric.devices.items():
        if swdata in done:
            continue

        done.append(swdata)

        if swdata.nb_device is None:
            continue

        # if it's not a Switch it makes no sense to continue,
        # we get all data from the other side of the link anyway
        if not isinstance(swdata, NetboxSwitch):
            continue

        logger.info("Checking cables for device %s", swdata.hostname)

        for intname, intdata in swdata.interfaces.items():
            if "port-channel" in intname.lower():
                continue

            # Set to False, change to True if neighbor is valid
            skip = True
            for neigh in intdata.neighbors:
                if isinstance(neigh, netwalk.Interface):
                    nb_term_a = intdata.nb_interface
                    nb_term_b = neigh.nb_interface

                    skip = False
                    
                    if isinstance(neigh.device, NetboxOTDevice):
                        if nb_term_a.custom_fields['mac_count'] is None:
                            nb_term_a.custom_fields['mac_count'] = 0

                        if nb_term_a.custom_fields['mac_count'] > 1:
                            if str(nb_term_a.mode).lower() != "access":
                                # Device is "seen" on a trunk interface, skip
                                logger.warning("Device %s seen on %s %s which is trunk, skip", neigh.device.hostname, nb_term_a.device.name, nb_term_a.name)
                                continue

                            #Cannot connect to direct interface, disconnect
                            logger.warning("Device found on interface with more than one mac")
                            
                            neigh.device.nb_device.full_details()
                            if neigh.device.nb_device.local_context_data is None:
                                neigh.device.nb_device.local_context_data = {}
                            neigh.device.nb_device.local_context_data.update({'connected_to': {'device': nb_term_a.device.name,
                                                                                               'interface': nb_term_a.name}})
                            
                            if neigh.device.nb_device.save():
                                logger.info("Updated context data for %s to %s", swname, str(neigh.device.nb_device.updates()))
                                neigh.device.nb_device.full_details()

                            #Also delete attached cable
                            if nb_term_a.cable is not None:
                                logger.info("Deleting cable as well")
                                nb_term_a.cable.delete()
                                
                            # We are done here
                            skip = True
                    else:
                        if nb_term_a.cable is not None:
                            # We saw this neighbor through CDP, we _know_ it's there
                            nb_other_side=nb_term_a.connected_endpoint.device
                            nb_other_side.full_details()
                            if str(nb_other_side.device_type) == "OT":
                                logger.warning("Found OT device on CDP device port, removing cable %s between %s and %s",
                                            nb_term_a.cable, nb_term_a.cable.termination_a.device.name,
                                            nb_term_a.cable.termination_b.device.name)
                                nb_term_a.cable.delete()
                                nb_term_a.full_details()

                elif isinstance(neigh, dict):
                    logger.warning(
                        "Device %s was a dict, skipping", str(neigh))
                else:
                    pass

            if skip:
                continue

            try:
                for cable in nb.dcim.cables.filter(device_id=swdata.nb_device.id):
                    assert nb_term_a != cable.termination_a
                    assert nb_term_a != cable.termination_b
                    assert nb_term_b != cable.termination_a
                    assert nb_term_b != cable.termination_b
            except AssertionError:
                continue

            logger.info("Adding cable between %s %s and %s %s", nb_term_a.device.name, nb_term_a.name, nb_term_b.device.name, nb_term_b.name)
            if nb_term_a.cable is not None:
                logger.info("Deleting old cable between %s %s and %s %s", 
                            nb_term_a.cable.termination_a.device.name,
                            nb_term_a.cable.termination_a.name,
                            nb_term_a.cable.termination_b.device.name,
                            nb_term_a.cable.termination_b.name)
                nb_term_a.cable.delete()
                # Refresh because it might have been deleted from the other side too
                nb_term_b.full_details()
                nb_term_a.full_details()
                
            if nb_term_b.cable is not None:
                logger.info("Deleting old cable between %s %s and %s %s", 
                            nb_term_b.cable.termination_a.device.name,
                            nb_term_b.cable.termination_a.name,
                            nb_term_b.cable.termination_b.device.name,
                            nb_term_b.cable.termination_b.name)
                nb_term_b.cable.delete()
                nb_term_b.full_details()
                nb_term_a.full_details()
                
            
            nb_cable = nb.dcim.cables.create(termination_a_type='dcim.interface',
                                             termination_b_type='dcim.interface',
                                             termination_a_id=nb_term_a.id,
                                             termination_b_id=nb_term_b.id)
            
            

def add_software_versions():
    """Add software version"""
    done = []
    for swname, swdata in fabric.devices.items():
        if swdata in done:
            continue

        done.append(swdata)
        
        if not isinstance(swdata, netwalk.Switch):
            continue

        if swdata.nb_device is None:
            continue
        
        logger.debug("Looking up %s", swdata.hostname)

        if swdata.facts is None:
            continue

        swdata.nb_device.custom_fields.update(
            {'software_version': swdata.facts['os_version']})
        if swdata.nb_device.save():
            logger.info("Updating %s with version %s",
                        swdata.hostname, swdata.facts['os_version'])
            swdata.nb_device.full_details()


def add_inventory_items(delete):
    """Add inventory items"""
    
    done = []
    for swname, swdata in fabric.devices.items():
        if swdata in done:
            continue

        done.append(swdata)
        
        if not isinstance(swdata, netwalk.Switch):
            continue
        
        if isinstance(swdata, netwalk.Switch):
            logger.debug("Looking up %s", swdata.hostname)
            if swdata.nb_device is None:
                continue

            manufacturer = swdata.nb_device.device_type.manufacturer

            if not hasattr(swdata, "inventory"):
                continue

            for invname, invdata in swdata.inventory.items():
                nb_item = nb.dcim.inventory_items.get(
                    device_id=swdata.nb_device.id, name=invname[:64], serial=invdata['sn'])
                if nb_item is None:
                    logger.info("Creating item %s, serial %s on device %s",
                                invname, invdata['sn'], swdata.nb_device.name)
                    nb.dcim.inventory_items.create(device=swdata.nb_device.id,
                                                   manufacturer=manufacturer.id,
                                                   name=invname[:64],
                                                   part_id=invdata['pid'],
                                                   serial=invdata['sn'],
                                                   discovered=True)

                else:
                    if nb_item.serial != invdata['sn']:
                        logger.info("Updating %s from serial %s PID %s to %s %s", invname,
                                    nb_item.serial, nb_item.part_id, invdata['sn'], invdata['pid'])
                        nb_item.update({'serial': invdata['sn'],
                                        'part_id': invdata['pid']})

            all_inventory = nb.dcim.inventory_items.filter(
                device_id=swdata.nb_device.id)

            if delete:
                for nb_inv in all_inventory:
                    if nb_inv.name[:64] not in {k[:64]: v for k, v in swdata.inventory.items()}:
                        logger.info("Deleting %s on device %s",
                                    nb_inv.name, swdata.nb_device.name)
                        nb_inv.delete()

def create_ot_devices_from_macs():
    """Create OT devices from macs"""
    global_reverse_arp = {}
    for swname, swdata in fabric.devices.items():
        if isinstance(swdata, netwalk.Switch):
            for i in swdata.arp_table:
                global_reverse_arp[EUI(i['mac'])] = {
                    'ip': ipaddress.ip_address(i['ip'])}

    # global_reverse_arp = {
    #     EUI('98be.9401.b70c'): {'ip': ipaddress.ip_address('10.19.2.1')},
    #     EUI('98be.9401.a2cc'): {'ip': ipaddress.ip_address('10.19.2.2')},
    #     EUI('98be.9401.a470'): {'ip': ipaddress.ip_address('10.19.2.11')},
    # }

    for k, v in fabric.mac_table.items():
        if any(not isinstance(x, NetboxOTDevice) for x in v['interface'].neighbors):
            # interface has CDP neighbor, skip
            continue
        
        if v['vlan'] != 1:
            continue

        if "vlan" in v['interface'].name.lower():
            continue
        
        if any(k.bits().startswith(x) for x in ["00000000-00000000-00001100-00000111-10101100",
                                                "00000000-00000000-00001100-10011111-1111",
                                                "00000000-00000101-01110011-10100000-0000"]):
            #HSRP or VRRP, skip
            continue
        
        try:
            ip = global_reverse_arp[k]['ip']
        except KeyError:
            ip = ipaddress.ip_address("1.1.1.1")

        k.dialect = mac_cisco
        newdev = NetboxOTDevice(ip, hostname=str(k))
        newdevint = NetboxInterface(name="Ethernet")

        newdev.add_interface(newdevint)
        newdevint.add_neighbor(v['interface'])

        fabric.devices[newdev.hostname] = newdev

    print(fabric)

def load_fabric_object(delete=False):
    nb_site = nb.dcim.sites.get(slug=site_slug)
    newneighs = []
    done = []
    for swname, swdata in fabric.devices.items():
        if type(swdata) == netwalk.Device:
            swdata.__class__ = NetboxDevice
        elif type(swdata) == netwalk.Switch:
            swdata.__class__ = NetboxSwitch

        if swdata in done:
            continue

        done.append(swdata)
        for intname, intdata in swdata.interfaces.items():
            intdata.__class__ = NetboxInterface
            for neigh in intdata.neighbors:
                if isinstance(neigh, dict):
                    if neigh['hostname'] not in fabric.devices:
                        if neigh['ip'] == '':
                            neigh['ip'] = "1.1.1.1"
                        neighobj = NetboxDevice(
                            neigh['ip'], hostname=neigh['hostname'])
                        neighint = NetboxInterface(name=neigh['remote_int'])
                        neighobj.add_interface(neighint)
                        newneighs.append(neighobj)

    for neigh in newneighs:
        fabric.devices[neigh.hostname] = neigh
        logger.info("Add %s to fabric", neigh.hostname)

    #create_ot_devices_from_macs()
    add_l2_vlans(nb_site, delete)
    create_devices_and_interfaces(nb_site, delete)
    add_active_vlans()
    if os.getenv("ADD_IP_ADDRESSES", "false").lower() == "true":
        add_ip_addresses(nb_site, delete)
    if os.getenv("CABLES", "false").lower() == "true":
        add_cables()
    if os.getenv("INVENTORY", "false").lower() == "true":
        add_software_versions()
        add_inventory_items(delete)


if __name__ == '__main__':
    site_slug = os.getenv("SITE_SLUG")
    with open(site_slug+".bin", "rb") as bindata:
        fabric = pickle.load(bindata)

    nb_access_role = nb.dcim.device_roles.get(name="Access Switch")
    nb_ot_role = nb.dcim.device_roles.get(name="OT")

    load_fabric_object(False)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description="Load pickled fabric objects generated from netwalk"
    )
    parser.add_argument('file',
                        help="Pickled file name")
    parser.add_argument('site_slug',
                        help="Netbox site slug")
    parser.add_argument('netbox_url',
                        help='Netbox server url')
    parser.add_argument('netbox_api_key',
                        help="Netbox API key")
    args_namespace = parser.parse_args()
    args = vars(args_namespace)
    shell_run_setup(args)