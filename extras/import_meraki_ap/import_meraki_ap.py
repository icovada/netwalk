"""Kickstart netbox compilation from Meraki dashboard AP and CDP neighborship info"""

import ipaddress
import logging
import pynetbox
import meraki
from slugify import slugify

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# Console log handler
ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)

logger.addHandler(ch)

MERAKI_API = "fgsdgfdgfdgfdsgfdgfds"
MERAKI_ORG_ID = "ffdsfsfsdafdsfasf"

dashboard = meraki.DashboardAPI(MERAKI_API, suppress_logging=True)

nb = pynetbox.api(
    'http://localhost',
    token='aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'
)

nb_role = nb.dcim.device_roles.get(name="Access Point")
nb_role_network = nb.dcim.device_roles.get(name="Access Switch")


def create_sites():
    """Create site from Meraki Dashboard data"""

    meraki_networks = dashboard.organizations.getOrganizationNetworks(
        MERAKI_ORG_ID)

    for site in meraki_networks:
        logger.info('Getting site %s', site['name'])
        nb_site = nb.dcim.sites.get(name=site['name'])

        if nb_site is None:
            logger.info('Creating site %s', site['name'])
            nb_site = nb.dcim.sites.create(name=site['name'],
                                           slug=slugify(site['name']))

        custom_fields = {'meraki_dashboard': site['url'],
                         'meraki_network_id': site['id'],
                         'site_code': site['name'].split()[0]}

        if nb_site.custom_fields != custom_fields:
            logger.info("Updating custom fields for site %s", site['name'])
            nb_site.update({'custom_fields': custom_fields})

        # Get address from one device
        sitedevices = dashboard.networks.getNetworkDevices(site['id'])

        if len(sitedevices) > 0:
            device = sitedevices[0]

            longitude = round(float(device['lng']), 6)
            latitude = round(float(device['lat']), 6)

            try:
                assert nb_site.latitude == latitude
                assert nb_site.longitude == longitude
                assert nb_site.physical_address == device['address']
            except AssertionError:
                logger.info("Update geo data for site %s", site['name'])
                nb_site.latitude = latitude
                nb_site.longitude = longitude
                nb_site.physical_address = device['address']
                nb_site.save()


def create_ap(access_point, modeldict):
    """Create Access points"""

    nb_device = nb.dcim.devices.get(name=access_point['name'])
    nb_site = nb.dcim.sites.get(cf_meraki_network_id=access_point['networkId'])
    assert nb_site is not None

    if nb_device is None:
        try:
            nb_model = modeldict[access_point['model']]
        except KeyError:
            nb_model = nb.dcim.device_types.get(model=access_point['model'])
            assert nb_model is not None, f"Model {access_point['model']} not found, create by hand"
            modeldict[access_point['model']] = nb_model

        logger.info("Creating device %s", access_point['name'])
        nb_device = nb.dcim.devices.create(name=access_point['name'],
                                           device_type=modeldict[access_point['model']].id,
                                           site=nb_site.id,
                                           device_role=nb_role.id,
                                           serial=access_point['serial'])

    else:
        # Check serial number is the same otherwise could be a device with the same name
        try:
            assert nb_device.serial == access_point['serial']
        except AssertionError:
            try:
                nb_model = modeldict[access_point['model']]
            except KeyError:
                nb_model = nb.dcim.device_types.get(
                    model=access_point['model'])
                modeldict[access_point['model']] = nb_model

            nb_device = nb.dcim.devices.get(
                name=f"{access_point['name']}-{access_point['serial']}")
            if nb_device is None:
                logger.info("Creating device %s%s",
                            access_point['name'], access_point['serial'])
                nb_device = nb.dcim.devices.create(name=f"{access_point['name']}-{access_point['serial']}",
                                                   device_type=nb_model.id,
                                                   site=nb_site.id,
                                                   device_role=nb_role.id,
                                                   serial=access_point['serial'])

    return nb_device, nb_site


def create_mgmt_interface(access_point, nb_device, nb_site):
    """Create fake management interfaces for cdp neighbors"""

    logger.info('Get management interface data for %s', access_point['serial'])
    mgmt = dashboard.devices.getDeviceManagementInterface(
        access_point['serial'])

    nb_interface = nb.dcim.interfaces.get(device_id=nb_device.id)
    nb_interface.mac_address = access_point['mac']
    nb_interface.save()

    try:
        assert 'staticIp' in mgmt['wan1'], "AP in DHCP"
        ipadd = ipaddress.ip_interface(
            f"{mgmt['wan1']['staticIp']}/{mgmt['wan1']['staticSubnetMask']}")
    except (KeyError, AssertionError) as e:
        logger.warning("%s", e)
        raise e

    try:
        ip = nb.ipam.ip_addresses.create(address=str(ipadd),
                                         assigned_object_id=nb_interface.id,
                                         assigned_object_type="dcim.interface")

        logger.info("Created IP %s and assigned to interface %s",
                    mgmt['wan1']['staticIp'], nb_interface.name)
    except pynetbox.RequestError:
        ip = nb.ipam.ip_addresses.get(address=str(ipadd))

    # Check prefix esists
    if len(nb.ipam.prefixes.filter(q=ip.address)) == 0:
        print("Creating prefix "+str(ipadd.network))
        nb_prefix = nb.ipam.prefixes.create(prefix=str(ipadd.network),
                                            status="active",
                                            site=nb_site.id)

    dash_url = dashboard.devices.getDevice(access_point['serial'])['url']
    try:
        assert nb_device.primary_ip4 == ip
    except AssertionError:
        try:
            nb_device.primary_ip4 = ip
            nb_device.custom_fields.update({'management_page': dash_url})
            nb_device.save()
            logger.info("Added IP %s as primary for device %s",
                        ip, nb_device.name)
        except pynetbox.RequestError as err:
            logger.warning("%s", err)
            raise err

    return nb_interface


def create_cdp_nei(access_point, nb_site):
    """Create devices from cdp neighborship data"""

    neighdata = dashboard.devices.getDeviceLldpCdp(access_point['serial'])

    try:
        neigh = neighdata['ports']['wired0']['cdp']
    except KeyError as e:
        logger.warning("Device %s has no neighbors", access_point['name'])
        raise e

    neigh_port = nb.dcim.interfaces.get(name=neigh['portId'],
                                        device=neigh['deviceId'])

    neigh_sw = nb.dcim.devices.get(
        name=neigh['deviceId'])
    if neigh_port is None:
        if neigh_sw is None:
            print("Creating device "+neigh['deviceId'])
            neigh_sw = nb.dcim.devices.create(name=neigh['deviceId'],
                                              device_type=1,
                                              site=nb_site.id,
                                              device_role=nb_role_network.id,
                                              )

        prefix = nb.ipam.prefixes.get(q=neigh['address'])
        if prefix is None:
            prefix = "0.0.0.0/32"
        try:
            svi = nb.dcim.interfaces.get(device_id=neigh_sw.id)
        except ValueError:
            svi = list(nb.dcim.interfaces.filter(device_id=neigh_sw.id))[0]

        porttype = "100base-tx" if "Fast" in neigh['portId'] else "1000base-t"

        print("Creating port "+neigh['portId']+" on device "+neigh_sw.name)
        neigh_port = nb.dcim.interfaces.create(device=neigh_sw.id,
                                               name=neigh['portId'],
                                               type=porttype,
                                               )

        if svi is None:
            svi = neigh_port

    prefix = nb.ipam.prefixes.get(q=neigh['address'])

    try:
        svi = nb.dcim.interfaces.get(device_id=neigh_sw.id)
    except ValueError:
        svi = list(nb.dcim.interfaces.filter(device_id=neigh_sw.id))[0]

    if svi is None:
        svi = neigh_port

    if prefix is None:
        prefix = "0.0.0.0/32"

    nb_address = nb.ipam.ip_addresses.get(
        address=f"{neigh['address']}/{str(prefix).split('/')[1]}")

    neigh_sw = nb.dcim.devices.get(
        name=neigh['deviceId'])

    if nb_address is not None:
        assert nb_address.assigned_object.device == neigh_sw, "IP found on more than one device"
    else:
        nb_address = nb.ipam.ip_addresses.create(
            address=f"{neigh['address']}/{str(prefix).split('/')[1]}",
            assigned_object_id=svi.id,
            assigned_object_type="dcim.interface"
        )

    if neigh_sw.primary_ip4 != nb_address:
        neigh_sw.primary_ip4 = nb_address
        logger.info("Updating primary IP for device %s %s",
                    neigh_sw.name, nb_address)
        neigh_sw.save()

    return neigh_port


def create_devices():
    """Create devices from meraki dashboard information"""

    meraki_inventory = list(
        dashboard.organizations.getOrganizationInventoryDevices(MERAKI_ORG_ID, -1))

    modeldict = {}
    for pos, ap in enumerate(meraki_inventory):
        logger.info("Device %s out of %s", pos, len(meraki_inventory)-1)

        if ap['networkId'] is None:
            continue

        nb_device, nb_site = create_ap(ap, modeldict)

        try:
            nb_interface = create_mgmt_interface(ap, nb_device, nb_site)
        except (KeyError, pynetbox.RequestError, AssertionError) as e:
            continue

        try:
            neigh_port = create_cdp_nei(ap, nb_site)
        except KeyError:
            continue

        logger.info("Connecting AP %s to device %s on %s",
                    nb_interface.device.name, neigh_port.device.name, neigh_port.name)
        try:
            cable = nb.dcim.cables.create(termination_a_type="dcim.interface",
                                          termination_b_type="dcim.interface",
                                          termination_a_id=nb_interface.id,
                                          termination_b_id=neigh_port.id)
        except pynetbox.core.query.RequestError as e:
            logger.info("%s", e)
            continue


def main():
    """Main"""
    create_sites()
    create_devices()


if __name__ == '__main__':
    main()
