import pickle
import pynetbox
import netwalk
from slugify import slugify

def main():
    with open('fabric_data.bin', 'rb') as fabricfile:
        fabric = pickle.load(fabricfile)

    nb = pynetbox.api(
        'http://localhost',
        token='d25885197f8a04fabf92aea757fb9f7a896f0b6c'
    )

    nb_role = nb.dcim.device_roles.get(name="Access Switch")
    nb_site = nb.dcim.sites.get(name="San Martino Buon Albergo")

    for swname, swdata in fabric.switches.items():
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

            nb_interface = nb.dcim.interfaces.get(device_id=nb_device.id,
                                                  name=interface)

            if nb_interface is None:
                nb_interface = nb.dcim.interfaces.create(device=nb_device.id,
                                                         name=interface,
                                                         type=int_type)


if __name__ == '__main__':
    main()