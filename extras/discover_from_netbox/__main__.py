import pickle
import logging
import secrets
import pynetbox
import netwalk
from .. import import_to_netbox as nbimp

logger = logging.getLogger(__name__)
logger.setLevel(level=logging.DEBUG)

ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)

logger.addHandler(ch)

logging.getLogger('netwalk').setLevel(logging.INFO)
logging.getLogger('netwalk').addHandler(ch)

nb = pynetbox.api(
    secrets.NB_HOST,
    token=secrets.NB_API
)

def no_ap(nei: dict):
    if "ap" in nei['hostname'][4:6].lower():
        return False
    elif "axis" in nei['hostname'].lower():
        return False
    else:
        return True



#discovered_tag = nb.extras.tags.get(name="Discovered")
sites = [x for x in nb.dcim.sites.all()]

for site in sites:
    sitename = site.slug

    logger.info("Connecting to %s", sitename)
    fabric = netwalk.Fabric()
    nb_devices = [x for x in nb.dcim.devices.filter(site_id=site.id, has_primary_ip=True)]
    #devices = [x for x in nb.dcim.devices.filter(site_id=site.id)]
    devices = []
    for i in nb_devices:
        if "switch" in i.device_role.name.lower():
            deviceipcidr = i.primary_ip.display
            deviceip = deviceipcidr[:deviceipcidr.index("/")]
            switch_object = netwalk.Device(deviceip, hostname=i.name)
            devices.append(switch_object)

    password = secrets.DATA[site.name]['password']

    fabric.init_from_seed_device(devices, [(secrets.USERNAME, password)], [{'secret': password, "transport": "telnet"}, {"secret": password}], 10, no_ap, scan_options={'blacklist': ['lldp_neighbors']})

    with open("bindata/"+site.slug+".bin", "wb") as outfile:
        pickle.dump(fabric, outfile)

    try:
        with open("bindata/"+site.slug+".bin", "rb") as infile:
            print(site.slug)
            fabric = pickle.load(infile)
    except:
        continue

    # try:
    #nbimp.load_fabric_object(nb, fabric, "Access Switch", sitename, True)
    # except Exception as e:
    #     print(e)
    #     pass

    #site.tags.append(discovered_tag)
    site.save()
