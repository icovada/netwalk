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

discovered_tag = nb.extras.tags.get(name="Discovered")
sites = [x for x in nb.dcim.sites.all()]

for site in sites:
    if site.slug != "deposito-rivalta":
        continue
    
    if discovered_tag in site.tags:
        logger.info("Skip site %s because already discovered", site.name)
        continue

    sitename = site.slug
    logger.info("Connecting to %s", sitename)
    fabric = netwalk.Fabric()
    devices = [x for x in nb.dcim.devices.filter(site_id=site.id)]
    primaryip = []
    for device in devices:
        if 'switch' in device.device_role.slug:
            if device.primary_ip is not None:
                
                deviceipcidr = device.primary_ip.display
                deviceip = deviceipcidr[:deviceipcidr.index("/")]
                primaryip.append(deviceip)
                
        
    fabric.init_from_seed_device(primaryip, [(secrets.USERNAME, secrets.PASSWORD), (secrets.TELECOMUSER, secrets.TELECOMPASS)], [{}, {"transport": "telnet"}], parallel_threads=10)

    with open("bindata/"+site.slug+".bin", "wb") as outfile:
        pickle.dump(fabric, outfile)

    nbimp.load_fabric_object(nb, fabric, "Access Switch", sitename)
    
    site.tags.append(discovered_tag)
    site.save()
