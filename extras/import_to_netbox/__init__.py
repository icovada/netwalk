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

import argparse
import pickle
import logging
import ipaddress
from netaddr import EUI
from netaddr.core import AddrFormatError
from netwalk import Device
import pynetbox
from pynetbox.core.query import RequestError
from slugify import slugify
import netwalk
from qlient import Client, HTTPBackend, Fields
import requests

from netwalk.interface import Interface, Switch

logger = logging.getLogger(__name__)
logger.setLevel(level=logging.DEBUG)

ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)

logger.addHandler(ch)


nwlogger = logging.getLogger('netwalk')
nwlogger.setLevel(level=logging.DEBUG)
QLIENT = None
NB = None


def get_device_by_hostname_or_mac(swdata, site=None):
    """
    Get devices either by hostname or mac of an interface
    Meraki APs advertise their mac as CDP hostname
    """

    try:
        return swdata.nb_device
    except AttributeError:
        pass

    if isinstance(swdata, netwalk.Device):
        if swdata.hostname == "":
            raise ValueError("Device has no hostname")
        hostname = swdata.hostname
    else:
        if swdata == "":
            raise ValueError("Device has no hostname")
        hostname = swdata

    # Get device by name
    if site is None:
        nb_device = NB.dcim.devices.get(name=hostname)
    else:
        nb_device = NB.dcim.devices.get(name=hostname, site_id=site.id)
    if nb_device is not None:
        return nb_device

    try:
        # Get device by looking up its mac across interfaces
        mac_address = EUI(hostname)
        nb_interface = NB.dcim.interfaces.get(mac_address=mac_address)

        assert nb_interface is not None

        nb_device = nb_interface.device
        hostname = nb_device.name
        return nb_device

    except (AssertionError, RequestError, AddrFormatError):
        # Hostname is not a mac, lookup in other ways
        try:
            # Lookup by hostname starts with
            if site is None:
                nb_device = NB.dcim.devices.filter(name__isw=hostname)
            else:
                nb_device = NB.dcim.devices.filter(name__isw=hostname, site_id=site.id)

            if nb_device is not None:
                alldevs = list(nb_device)
                if len(alldevs) > 1:
                    # If there is more than one device and the hostname is exactly 40 chars
                    # it's probably a duplicate we got from CDP, remove it
                    for dev in alldevs:
                        if len(dev.name) == 40:
                            dev.delete()
                elif len(alldevs) == 0:
                    return alldevs[0]

                nb_device = None

            if nb_device is None:
                # Lookup by cutting up the hostname to 40 chars
                if len(hostname) > 40:
                    if site is None:
                        nb_device = NB.dcim.devices.get(
                            name__isw=hostname[:40])
                    else:
                        nb_device = NB.dcim.devices.get(
                            name__isw=hostname[:40], site_id=site.id)

                if nb_device is None:
                    # Last resort, cut hostname by subdomains
                    domain_hierarchy = hostname.split(".")
                    subdomains = len(domain_hierarchy)-1
                    while nb_device is None and subdomains != 0:
                        smaller_name = ".".join(
                            domain_hierarchy[:subdomains])
                        if site is None:
                            nb_device = NB.dcim.devices.get(
                                name__isw=smaller_name)
                        else:
                            nb_device = NB.dcim.devices.get(
                                name__isw=smaller_name, site_id=site.id)
                        subdomains -= 1

            return nb_device
        except (KeyError, IndexError):
            return None


def create_devices_and_interfaces(fabric, nb_access_role, nb_site, delete):
    "Create devices and interfaces"
    site_vlans = NB.ipam.vlans.filter(site_id=nb_site.id)
    vlans_dict = {x.vid: x for x in site_vlans}

    done = []

    for swname, swdata in fabric.switches.items():
        if swdata in done:
            continue

        done.append(swdata)
        if isinstance(swdata, netwalk.Switch):
            logger.info("Switch %s", swdata.hostname)
            if swdata.facts is None:
                nb_device_type = NB.dcim.device_types.get(
                    model="Unknown")
            else:
                nb_device_type = NB.dcim.device_types.get(
                    model=swdata.facts['model'])

            if nb_device_type is None:
                nb_manufacturer = NB.dcim.manufacturers.get(
                    slug=slugify(swdata.facts['vendor']))
                if nb_manufacturer is None:
                    nb_manufacturer = NB.dcim.manufacturers.create(name=swdata.facts['vendor'],
                                                                   slug=slugify(swdata.facts['vendor']))

                nb_device_type = NB.dcim.device_types.create(model=swdata.facts['model'],
                                                             manufacturer=nb_manufacturer.id,
                                                             slug=slugify(swdata.facts['model']))

            try:
                nb_device = get_device_by_hostname_or_mac(
                    swdata.hostname, nb_site)
            except ValueError:
                continue

            if nb_device is None:
                data = {'name': swdata.hostname,
                        'device_role': nb_access_role.id,
                        'device_type': nb_device_type.id,
                        'site': nb_site.id}

                if swdata.facts is not None:
                    data['serial'] = swdata.facts['serial_number'][:50]

                nb_device = NB.dcim.devices.create(**data)
            else:
                try:
                    assert nb_device.device_type.model == swdata.facts['model']
                    assert nb_device.serial == swdata.facts['serial_number']
                except AssertionError:
                    logger.warning("Switch %s changed model from %s to %s",
                                   swdata.hostname, nb_device.device_type.display, swdata.facts['model'])
                    nb_device.update({'device_type': nb_device_type.id,
                                      'serial': swdata.facts['serial_number'][:50]})
                except TypeError:
                    # most likelky no facts
                    logger.warning("Switch %s has no data, skipping",
                                   swdata.hostname)

            if nb_device.name != swdata.hostname:
                nb_device.update({'name': swdata.hostname})

        else:
            logger.info("Device %s", swdata.hostname)
            try:
                nb_device = get_device_by_hostname_or_mac(swdata, site=nb_site)
            except ValueError:
                continue

            nb_device_type = NB.dcim.device_types.get(model="Unknown")

            if nb_device is None:
                nb_device = NB.dcim.devices.create(name=swdata.hostname,
                                                   device_role=nb_access_role.id,
                                                   device_type=nb_device_type.id,
                                                   site=nb_site.id)

        fabric.switches[swname].nb_device = nb_device

        nb_all_interfaces = {
            x.name: x for x in NB.dcim.interfaces.filter(device_id=nb_device.id)}

        # Create new interfaces
        for intname, intdata in swdata.interfaces.items():
            intproperties = {}
            if intname not in nb_all_interfaces:
                if intdata.mac_address != '':
                    intproperties['mac_address'] = intdata.mac_address
                logger.info("Interface %s on switch %s",
                            intname, swdata.hostname)
                if isinstance(swdata, netwalk.Switch):
                    if "Fast" in intname:
                        int_type = "100base-tx"
                    elif "Te" in intname:
                        int_type = "10gbase-x-sfpp"
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

                if isinstance(intdata.switch, netwalk.Switch):
                    if intdata.description is not None:
                        intproperties['description'] = intdata.description

                    if intdata.mode == "trunk":
                        if len(intdata.allowed_vlan) == 4094:
                            intproperties['mode'] = "tagged-all"
                        else:
                            intproperties['mode'] = "tagged"
                            intproperties['tagged_vlans'] = [
                                vlans_dict[x].id for x in intdata.allowed_vlan]
                    else:
                        intproperties['mode'] = "access"

                    if "vlan" in intname.lower():
                        vlanid = int(intname.lower().replace("vlan", ""))
                        intproperties['untagged_vlan'] = vlans_dict[vlanid].id
                    else:
                        intproperties['untagged_vlan'] = vlans_dict[intdata.native_vlan].id

                    if hasattr(intproperties, 'unparsed_lines'):
                        if intproperties['unparsed_lines'] != intdata.unparsed_lines:
                            intproperties['unparsed_lines'] = intdata.unparsed_lines
                    else:
                        if len(intdata.unparsed_lines) > 0:
                            intproperties['unparsed_lines'] = intdata.unparsed_lines

                    intproperties['enabled'] = intdata.is_enabled
                    intproperties['custom_fields'] = {}
                    intproperties['custom_fields']['bpduguard'] = intdata.bpduguard
                    intproperties['custom_fields']['type_edge'] = intdata.type_edge
                    if intdata.mac_count > 1:
                        intproperties['custom_fields']['mac_count'] = intdata.mac_count

                nb_interface = NB.dcim.interfaces.create(device=nb_device.id,
                                                         name=intname,
                                                         type=int_type,
                                                         **intproperties)

                # If this is a port channel, tag child interfaces, if they exist
                if "Port-channel" in intname:
                    for childintdata in intdata.child_interfaces:
                        child = NB.dcim.interfaces.get(
                            device_id=nb_device.id, name=childintdata.name)
                        if child is not None and child.lag is not None:
                            if child.lag.id != nb_interface.id:
                                logger.info("Adding %s under %s",
                                            intname, nb_interface.name)
                                child.update({'lag': nb_interface.id})

            else:
                nb_interface = nb_all_interfaces[intname]

                if delete:
                    if len(intdata.neighbors) == 0:
                        if nb_interface.cable is not None:
                            logger.info(
                                "Deleting old cable on %s", intdata.name)
                            nb_interface.cable.delete()

                if isinstance(intdata.switch, netwalk.Switch):
                    if intdata.mac_address != '':
                        if nb_interface.mac_address is None:
                            intproperties['mac_address'] = intdata.mac_address
                        elif EUI(intdata.mac_address) != EUI(nb_interface.mac_address):
                            intproperties['mac_address'] = intdata.mac_address

                    if intdata.description != nb_interface.description:
                        intproperties['description'] = intdata.description if intdata.description is not None else ""

                    if intdata.mode == 'trunk':
                        if len(intdata.allowed_vlan) == 4094:
                            try:
                                assert nb_interface.mode.value == 'tagged-all'
                            except (AssertionError, AttributeError):
                                intproperties['mode'] = 'tagged-all'
                        else:
                            try:
                                assert nb_interface.mode.value == 'tagged'
                            except (AssertionError, AttributeError):
                                intproperties['mode'] = 'tagged'

                    elif intdata.mode == 'access':
                        try:
                            assert nb_interface.mode.value == 'access'
                        except (AssertionError, AttributeError):
                            intproperties['mode'] = 'access'

                    try:
                        assert nb_interface.untagged_vlan == vlans_dict[intdata.native_vlan]
                    except AssertionError:
                        intproperties['untagged_vlan'] = vlans_dict[intdata.native_vlan]
                    except KeyError:
                        logger.error("VLAN %s on interface %s %s does not exist",
                                     intdata.native_vlan, intdata.name, intdata.switch.hostname)
                        continue

                    if intdata.is_enabled != nb_interface.enabled:
                        intproperties['enabled'] = intdata.is_enabled

                    if nb_interface.custom_fields['bpduguard'] != intdata.bpduguard or nb_interface.custom_fields['type_edge'] != intdata.type_edge:
                        intproperties['custom_fields'] = {'bpduguard': intdata.bpduguard,
                                                          'type_edge': intdata.type_edge}

                    if len(intdata.neighbors) == 0:
                        if intdata.mac_count > 1:
                            if nb_interface.custom_fields['mac_count'] != intdata.mac_count:
                                if 'custom_fields' not in intproperties:
                                    intproperties['custom_fields'] = {}

                                intproperties['custom_fields']['mac_count'] = intdata.mac_count

                    if "Port-channel" in intname:
                        for childint in intdata.child_interfaces:
                            child = NB.dcim.interfaces.get(
                                device_id=nb_device.id, name=childint.name)
                            if child is not None:
                                if child.lag is None:
                                    logger.info("Adding %s under %s",
                                                childint.name, nb_interface.name)
                                    child.update({'lag': nb_interface.id})
                                elif child.lag.id != nb_interface.id:
                                    logger.info("Adding %s under %s",
                                                childint.name, nb_interface.name)
                                    child.update({'lag': nb_interface.id})

                    if len(intproperties) > 0:
                        logger.info("Updating interface %s on %s",
                                    intname, swdata.hostname)
                        nb_interface.update(intproperties)

        # Delete interfaces that no longer exist
        if delete:
            if isinstance(swdata, netwalk.Switch):
                for k, v in nb_all_interfaces.items():
                    if k not in swdata.interfaces:
                        logger.info("Deleting interface %s from %s",
                                    k, swdata.hostname)
                        v.delete()


def add_ip_addresses(fabric, nb_site, delete):
    "Add IP address"
    done = []

    for swname, swdata in fabric.switches.items():
        if swdata in done:
            continue

        done.append(swdata)
        if isinstance(swdata, netwalk.Switch):
            try:
                nb_device = get_device_by_hostname_or_mac(swdata, site=nb_site)
            except ValueError:
                continue

            nb_device_addresses = {ipaddress.ip_interface(
                x): x for x in NB.ipam.ip_addresses.filter(device_id=nb_device.id)}
            nb_device_interfaces = {
                x.name: x for x in NB.dcim.interfaces.filter(device_id=nb_device.id)}
            all_device_addresses = []

            # Cycle through interfaces, see if the IPs on them are configured
            for intname, intdata in swdata.interfaces.items():
                try:
                    assert hasattr(intdata, 'address')
                    assert len(intdata.address) != 0
                except AssertionError:
                    continue

                nb_interface = nb_device_interfaces[intname]

                if 'ipv4' in intdata.address:
                    for address, addressdata in intdata.address['ipv4'].items():
                        logger.info("Checking IP %s", str(address))
                        all_device_addresses.append(address)

                        if address not in nb_device_addresses:
                            logger.info("Checking prefix %s",
                                        str(address.network))
                            nb_prefix = NB.ipam.prefixes.get(prefix=str(address.network),
                                                             site_id=nb_site.id)

                            if nb_prefix is None:
                                logger.info("Creating prefix %s",
                                            str(address.network))
                                try:
                                    nb_prefix = NB.ipam.prefixes.create(prefix=str(address.network),
                                                                        site=nb_site.id,
                                                                        vlan=nb_interface.untagged_vlan.id)
                                except:
                                    pass

                            logger.info("Checking IP %s", str(address))
                            try:
                                nb_address = NB.ipam.ip_addresses.get(address=str(address),
                                                                      site_id=nb_site.id)
                            except ValueError:
                                nb_address = None

                            if nb_address is None:
                                logger.info("Creating IP %s", str(address))
                                nb_address = NB.ipam.ip_addresses.create(address=str(address),
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
                            except RequestError:
                                # The request failed with code 400 Bad Request: {'interface': ['IP address is primary for device SWBB-2-SI-24 but not assigned to it!']}
                                nb_address.delete()
                                logger.warning(
                                    "IP %s deleted because is primary for device %s but not assigned to it, recreating it", nb_address, nb_device.name)
                                nb_address = NB.ipam.ip_addresses.create(address=str(address),
                                                                         site=nb_site.id)
                                nb_device_addresses[address] = nb_address
                                if nb_address.assigned_object_type != 'dcim.interface':
                                    newdata['assigned_object_type'] = 'dcim.interface'
                                if nb_address.assigned_object_id != nb_interface.id:
                                    newdata['assigned_object_id'] = nb_interface.id
                                role = None if addressdata['type'] == 'primary' else addressdata['type']

                                nb_address.update(newdata)

                if 'hsrp' in intdata.address and 'groups' in intdata.address['hsrp']:
                    for hsrpgrp, hsrpdata in intdata.address['hsrp']['groups'].items():
                        try:
                            assert 'address' in hsrpdata
                        except AssertionError:
                            continue

                        logger.info("Checking HSRP address %s on %s %s",
                                    hsrpdata['address'], intdata.switch.hostname, intdata.name)

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
                            nb_hsrp_address = NB.ipam.ip_addresses.create(address=str(hsrp_addr_obj),
                                                                          assigned_object_id=nb_interface.id,
                                                                          assigned_object_type='dcim.interface',
                                                                          role='hsrp')
                            nb_device_addresses[hsrp_addr_obj] = nb_hsrp_address

            for k, v in nb_device_addresses.items():
                if k not in all_device_addresses:
                    if delete:
                        logger.warning(
                            "Deleting old address %s from %s", k, swdata.hostname)
                        ip_to_remove = NB.ipam.ip_addresses.get(
                            q=str(k), device_id=nb_device.id)
                        ip_to_remove.delete()
                else:
                    if nb_device.primary_ip4 != v:
                        if v.assigned_object is not None:
                            if ipaddress.ip_interface(v).ip == swdata.mgmt_address:
                                if v.role is None:
                                    logger.info(
                                        "Assign %s as primary ip for %s", v, swdata.hostname)
                                    nb_device.update({'primary_ip4': v.id})


def add_neighbor_ip_addresses(fabric, nb_site, delete):
    """Add neighbor IP address"""
    done = []
    for swname, swdata in fabric.switches.items():
        if swdata in done:
            continue

        done.append(swdata)

        if type(swdata) == netwalk.switch.Device:
            logger.info("Checking Device %s", swdata.hostname)
            if swdata.mgmt_address == ipaddress.ip_address("1.1.1.1"):
                continue

            try:
                nb_neigh_device = get_device_by_hostname_or_mac(
                    swdata, nb_site)
            except ValueError:
                continue

            for intname, intdata in swdata.interfaces.items():
                nb_neigh_interface = NB.dcim.interfaces.get(name=intdata.name,
                                                            device_id=nb_neigh_device.id)

                # Search IP
                logger.debug("Searching IP %s for %s",
                             swdata.mgmt_address, swdata.hostname)
                nb_neigh_ips = [x for x in NB.ipam.ip_addresses.filter(
                    device_id=nb_neigh_device.id)]

                if any([x.assigned_object_id != nb_neigh_interface.id for x in nb_neigh_ips]):
                    logger.error(
                        "Error, neighbor device %s has IPs on more interfaces than discovered, is this an error?", swdata.hostname)
                    continue

                if len(nb_neigh_ips) == 0:
                    # No ip found, figure out smallest prefix configured that contains the IP
                    logger.debug(
                        "IP %s not found, looking for prefixes", swdata.mgmt_address)
                    nb_prefixes = NB.ipam.prefixes.filter(
                        q=swdata.mgmt_address)
                    if len(nb_prefixes) > 0:
                        # Search smallest prefix
                        prefixlen = 0
                        smallestprefix = None
                        for prefix in nb_prefixes:
                            logger.debug(
                                "Checking prefix %s, longest prefix found so far: %s", prefix['prefix'], smallestprefix)
                            thispref = ipaddress.ip_network(prefix['prefix'])
                            if thispref.prefixlen > prefixlen:
                                prefixlen = thispref.prefixlen
                                logger.debug(
                                    "Found longest prefix %s", thispref)
                                smallestprefix = thispref

                        assert smallestprefix is not None

                    # Now we have the smallest prefix length we can create the ip address

                        finalip = f"{swdata.mgmt_address}/{smallestprefix.prefixlen}"
                    else:
                        finalip = f"{swdata.mgmt_address}/32"
                    logger.debug("Creating IP %s", finalip)
                    nb_neigh_ips.append(
                        NB.ipam.ip_addresses.create(address=finalip))

                for nb_neigh_ip in nb_neigh_ips:
                    if ipaddress.ip_interface(nb_neigh_ip.address).ip != swdata.mgmt_address:
                        logger.warning("Deleting old IP %s from %s",
                                       nb_neigh_ip.address, swdata.hostname)
                        nb_neigh_device.update({'primary_ip4': None})
                        nb_neigh_ip.update({'assigned_object_type': None,
                                            'assigned_object_id': None})

                    if nb_neigh_ip.assigned_object_id != nb_neigh_interface.id:
                        logger.debug("Associating IP %s to interface %s",
                                     nb_neigh_ip.address, nb_neigh_interface.name)
                        nb_neigh_ip.update({'assigned_object_type': 'dcim.interface',
                                            'assigned_object_id': nb_neigh_interface.id})

                        nb_neigh_device.update({'primary_ip4': nb_neigh_ip.id})


def add_l2_vlans(fabric, nb_site, delete):
    "Add L2 VLANs"
    nb_all_vlans = [x for x in NB.ipam.vlans.filter(site_id=nb_site.id)]
    vlan_dict = {x.vid: x for x in nb_all_vlans}
    for swname, swdata in fabric.switches.items():
        if isinstance(swdata, netwalk.Switch):
            if swdata.vlans is None:
                continue

            for vlanid, vlandata in swdata.vlans.items():
                if int(vlanid) not in vlan_dict:
                    logger.info("Adding vlan %s", vlanid)
                    nb_vlan = NB.ipam.vlans.create(vid=vlanid,
                                                   name=vlandata['name'],
                                                   site=nb_site.id)
                    vlan_dict[int(vlanid)] = nb_vlan


def add_cables(fabric, nb_site):
    """Add cables"""
    logger.info("Adding cables")
    all_nb_devices = {
        x.name: x for x in NB.dcim.devices.filter(site_id=nb_site.id)}

    done = []
    for swname, swdata in fabric.switches.items():
        if swdata in done:
            continue

        done.append(swdata)
        try:
            swdata.nb_device = get_device_by_hostname_or_mac(
                swdata, site=nb_site)
        except ValueError:
            continue

    done = []
    for swname, swdata in fabric.switches.items():
        if swdata in done:
            continue

        if not hasattr(swdata, 'nb_device'):
            continue

        done.append(swdata)
        logger.info("Checking cables for device %s", swdata.hostname)
        for intname, intdata in swdata.interfaces.items():
            try:
                if isinstance(intdata.neighbors[0], netwalk.Interface):
                    try:
                        assert hasattr(intdata, 'nb_interface')
                    except AssertionError:
                        intdata.nb_interface = NB.dcim.interfaces.get(
                            device_id=swdata.nb_device.id, name=intname)

                    try:
                        assert hasattr(intdata.neighbors[0], 'nb_interface')
                    except AssertionError:
                        try:
                            intdata.neighbors[0].nb_interface = NB.dcim.interfaces.get(
                                device_id=intdata.neighbors[0].switch.nb_device.id, name=intdata.neighbors[0].name)
                        except AttributeError:
                            try:
                                neigh_obj = get_device_by_hostname_or_mac(
                                    intdata.neighbors[0].switch, site=nb_site)
                            except ValueError:
                                continue

                            neighbor_nb_device = NB.dcim.devices.get(
                                name=neigh_obj.name)
                            intdata.neighbors[0].nb_interface = NB.dcim.interfaces.get(
                                device_id=neighbor_nb_device.id, name=intdata.neighbors[0].name)

                    nb_term_a = intdata.nb_interface
                    nb_term_b = intdata.neighbors[0].nb_interface

                elif isinstance(intdata.neighbors[0], dict):
                    try:
                        assert hasattr(intdata, 'nb_interface')
                    except AssertionError:
                        intdata.nb_interface = NB.dcim.interfaces.get(
                            device_id=swdata.nb_device.id, name=intname)

                    try:
                        assert hasattr(intdata.neighbors[0], 'nb_device')
                    except AssertionError:
                        try:
                            intdata.neighbors[0]['nb_device'] = all_nb_devices[intdata.neighbors[0]['hostname']]
                        except KeyError:
                            try:
                                intdata.neighbors[0]['nb_device'] = get_device_by_hostname_or_mac(
                                    intdata.neighbors[0]['hostname'], nb_site)
                            except ValueError:
                                continue

                    try:
                        assert intdata.neighbors[0]['nb_device'] is not None
                    except AssertionError:
                        intdata.neighbors[0]['nb_interface'] = NB.dcim.interfaces.get(
                            mac_address=intdata.neighbors[0]['name'])
                        assert intdata.neighbors[0]['nb_interface'] is not None
                        intdata.neighbors[0]['nb_device'] = NB.dcim.devices.get(
                            id=intdata.neighbors[0]['nb_interface'].device.id)

                    try:
                        assert hasattr(intdata.neighbors[0], 'nb_interface')
                    except AssertionError:
                        intdata.neighbors[0]['nb_interface'] = NB.dcim.interfaces.get(
                            device_id=intdata.neighbors[0]['nb_device'].id, name=intdata.neighbors[0]['remote_int'])

                    try:
                        assert intdata.neighbors[0]['nb_interface'] is not None
                    except AssertionError:
                        # Interface does not exist. Create it.
                        intdata.neighbors[0]['nb_interface'] = NB.dcim.interfaces.create(name=intdata.neighbors[0]['remote_int'],
                                                                                         device=intdata.neighbors[
                                                                                             0]['nb_device'].id,
                                                                                         type='1000base-t')

                    nb_term_a = intdata.nb_interface
                    nb_term_b = intdata.neighbors[0]['nb_interface']
                else:
                    continue

                sw_cables = [x for x in NB.dcim.cables.filter(
                    device_id=nb_term_a.device.id)]
                try:
                    for cable in sw_cables:
                        assert nb_term_a != cable.termination_a
                        assert nb_term_a != cable.termination_b
                        assert nb_term_b != cable.termination_a
                        assert nb_term_b != cable.termination_b
                except AssertionError:
                    continue

                sw_cables = [x for x in NB.dcim.cables.filter(
                    device_id=nb_term_b.device.id)]
                try:
                    for cable in sw_cables:
                        assert nb_term_a != cable.termination_a
                        assert nb_term_a != cable.termination_b
                        assert nb_term_b != cable.termination_a
                        assert nb_term_b != cable.termination_b
                except AssertionError:
                    continue

                try:
                    assert nb_term_a.name != "wlan-ap0"
                    assert nb_term_b.name != "wlan-ap0"
                except AssertionError:
                    continue

                logger.info("Adding cable")
                nb_cable = NB.dcim.cables.create(termination_a_type='dcim.interface',
                                                 termination_b_type='dcim.interface',
                                                 termination_a_id=nb_term_a.id,
                                                 termination_b_id=nb_term_b.id)
            except IndexError:
                pass


def add_software_versions(fabric, nb_site, delete):
    """Add software version"""
    done = []
    for swname, swdata in fabric.switches.items():
        if swdata in done:
            continue

        if swdata.facts is None:
            continue

        done.append(swdata)
        try:
            thisdev = get_device_by_hostname_or_mac(swdata, nb_site)
        except ValueError:
            continue

        assert thisdev is not None

        if thisdev['custom_fields']['software_version'] != swdata.facts['os_version']:
            logger.info("Updating %s with version %s",
                        swdata.hostname, swdata.facts['os_version'])
            thisdev.update(
                {'custom_fields': {'software_version': swdata.facts['os_version']}})
        else:
            logger.info("%s already has correct software version",
                        swdata.hostname)


def add_inventory_items(fabric, nb_site, delete):
    """Add inventory items"""
    done = []
    for swname, swdata in fabric.switches.items():
        if swdata in done:
            continue

        done.append(swdata)
        if isinstance(swdata, netwalk.Switch):
            logger.debug("Looking up %s", swdata.hostname)
            try:
                thisdev = get_device_by_hostname_or_mac(swdata, nb_site)
            except ValueError:
                continue

            assert thisdev is not None
            manufacturer = thisdev.device_type.manufacturer

            if not hasattr(swdata, "inventory"):
                continue

            for invname, invdata in swdata.inventory.items():
                nb_item = NB.dcim.inventory_items.get(
                    device_id=thisdev.id, name=invname[:64], serial=invdata['sn'])
                if nb_item is None:
                    logger.info("Creating item %s, serial %s on device %s",
                                invname, invdata['sn'], thisdev.name)
                    NB.dcim.inventory_items.create(device=thisdev.id,
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

            all_inventory = NB.dcim.inventory_items.filter(
                device_id=thisdev.id)

            if delete:
                for nb_inv in all_inventory:
                    if nb_inv.name[:64] not in {k[:64]: v for k, v in swdata.inventory.items()}:
                        logger.info("Deleting %s on device %s",
                                    nb_inv.name, thisdev.name)
                        nb_inv.delete()


def load_fabric_object(fabric: netwalk.Fabric, access_role, site_slug, delete=False):
    nb_access_role = NB.dcim.device_roles.get(name=access_role)
    nb_site = NB.dcim.sites.get(slug=site_slug)
    # add_l2_vlans(NB, fabric, nb_site, delete)
    newneighs = []
    done = []
    for swname, swdata in fabric.switches.items():
        if swdata in done:
            continue

        done.append(swdata)
        for intname, intdata in swdata.interfaces.items():
            for neigh in intdata.neighbors:
                if isinstance(neigh, dict):
                    if neigh['hostname'] not in fabric.switches:
                        if neigh['ip'] == '':
                            neigh['ip'] = "1.1.1.1"
                        neighobj = Device(
                            neigh['ip'], hostname=neigh['hostname'])
                        neighint = Interface(name=neigh['remote_int'])
                        neighobj.add_interface(neighint)
                        newneighs.append(neighobj)

    for neigh in newneighs:
        fabric.switches[neigh.hostname] = neigh
        logger.info("Add %s to fabric", neigh.hostname)

    create_devices_and_interfaces(
        fabric, nb_access_role, nb_site, delete)
    add_ip_addresses(fabric, nb_site, delete)
    add_neighbor_ip_addresses(fabric, nb_site, delete)
    add_cables(fabric, nb_site)
    add_software_versions(fabric, nb_site, delete)
    add_inventory_items(fabric, nb_site, delete)


def shell_run_setup(filename, site_slug, netbox_url, netbox_api_key):
    global QLIENT
    global NB

    logger.info("Opening %s", filename)
    with open(filename, "rb") as bindata:
        fabric = pickle.load(bindata)

    session = requests.Session()
    session.headers.update({'Authorization': "Token "+netbox_api_key})
    authenticated_backend = HTTPBackend(
        endpoint=netbox_url+"/graphql/", session=session)

    QLIENT = Client(authenticated_backend)

    NB = pynetbox.api(
        netbox_url,
        token=netbox_api_key
    )

    load_fabric_object(fabric, "Access Switch", site_slug, True)


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
