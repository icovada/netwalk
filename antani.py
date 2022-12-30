import netwalk

fabric = netwalk.Fabric()

fabric.init_from_seed_device("")
c93 = netwalk.Switch("10.210.65.3.33")

c93.retrieve_data("cisco", "cisco")
