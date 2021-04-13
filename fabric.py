"Define Fabric object"

import logging

import concurrent.futures
from napalm.base.exceptions import ConnectionException
from netmiko.ssh_exception import NetMikoAuthenticationException

from .switch import Switch
from .interface import Interface

class Fabric():
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.switches = {}
        self.discovery_status = {}
        self.mac_table = {}

    def add_switch(self,
                   host,
                   credentials,
                   napalm_optional_args=[None]):

        """
        Try to connect to, and if successful add to fabric, a new switch

        host: str,                        IP or hostname of device to connect to
        credentials: list(tuple(str,str)) List of (username, password) tuples to try
        napalm_optional_args: list(dict)  optional_args to pass to NAPALM, as many as you want
        """

        thisswitch = Switch(host)
        connected = False
        for optional_arg in napalm_optional_args:
            if connected:
                break

            for cred in credentials:
                try:
                    thisswitch.retrieve_data(cred[0], cred[1],
                                             napalm_optional_args=optional_arg)
                    connected = True
                    break
                except (ConnectionException, NetMikoAuthenticationException, ConnectionRefusedError):
                    continue

        if not connected:
            raise ConnectionError("Could not log in with any of the specified methods")

        clean_fqdn = thisswitch.facts['fqdn'].replace(".not set", "")
        self.switches[clean_fqdn] = thisswitch

        return thisswitch

    def init_from_seed_device(self,
                              seed_hosts: str,
                              credentials: list,
                              napalm_optional_args=[None],
                              parallel_threads=10):
        """
        Initialise entire fabric from a seed device.

        seed_hosts: str              List of IP or hostname of seed devices
        credentials: list            List of (username, password) tuples to try
        napalm_optional_args_telnet  optional_args to pass to NAPALM for telnet
        napalm_optional_args_ssh     optional_args to pass to NAPALM for ssh
        """

        # We can use a with statement to ensure threads are cleaned up promptly
        with concurrent.futures.ThreadPoolExecutor(max_workers=parallel_threads) as executor:
            # Start the load operations and mark each future with its URL
            for x in seed_hosts:
                self.discovery_status[x] = "Queued"

            self.logger.debug("Adding seed hosts to loop")
            future_switch_data = {executor.submit(
                self.add_switch,
                x,
                credentials,
                napalm_optional_args): x for x in seed_hosts}

            while future_switch_data:
                self.logger.debug("Waiting for data from loop")
                done, _ = concurrent.futures.wait(future_switch_data,
                                                  return_when=concurrent.futures.FIRST_COMPLETED)

                for fut in done:
                    hostname = future_switch_data.pop(fut)
                    self.logger.debug("Got data for %s", hostname)


                    try:
                        swobject = fut.result()
                    except Exception as exc:
                        self.logger.error('%r generated an exception: %s' %
                              (hostname, exc))
                        self.discovery_status[hostname] = "Failed"
                    else:
                        fqdn = swobject.facts['fqdn'].replace(".not set", "")
                        print("Done", fqdn)
                        self.discovery_status[hostname] = "Completed"
                        self.logger.info("Completed discovery of %s %s", swobject.facts['fqdn'], swobject.hostname)
                        # Check if it has cdp neighbors

                        for _, intdata in swobject.interfaces.items():
                            if hasattr(intdata, "neighbors"):
                                for nei in intdata.neighbors:
                                    if not isinstance(nei, Interface):
                                        if nei['hostname'] not in self.switches and nei['ip'] not in self.discovery_status:
                                            try:
                                                assert "AIR" not in nei['platform']
                                                assert "CAP" not in nei['platform']
                                                assert "N77" not in nei['platform']
                                                assert "axis" not in nei['hostname']
                                            except AssertionError:
                                                logging.debug("Skipping %s, %s", nei['hostname'], nei['platform'])
                                                continue

                                            self.discovery_status[nei['ip']
                                                                  ] = "Queued"

                                            self.logger.info("Queueing discover for %s", nei['hostname'])

                                            future_switch_data[executor.submit(self.add_switch,
                                                                               nei['ip'],
                                                                               credentials,
                                                                               napalm_optional_args)] = nei['ip']
                                        else:
                                            self.logger.debug("Skipping %s, already discovered", nei['hostname'])

        self.refresh_global_information()

    def refresh_global_information(self):
        """
        Update global information such as mac address position
        and cdp neighbor adjacency
        """
        self.logger.debug("Refreshing information")
        self._recalculate_macs()
        self._find_links()

    def _find_links(self):
        """
        Join switches by CDP neighborship
        """
        short_fabric = {k[:40]: v for k, v in self.switches.items()}

        for sw, swdata in self.switches.items():
            for intf, intfdata in swdata.interfaces.items():
                if hasattr(intfdata, "neighbors"):
                    for i in range(0, len(intfdata.neighbors)):
                        if isinstance(intfdata.neighbors[i], Interface):
                            continue

                        switch = intfdata.neighbors[i]['hostname']
                        port = intfdata.neighbors[i]['remote_int']

                        try:
                            peer_device = self.switches[switch].interfaces[port]
                            intfdata.neighbors[i] = peer_device
                        except KeyError:
                            # Hostname over 40 char
                            try:
                                peer_device = short_fabric[switch[:40]
                                                           ].interfaces[port]
                                self.logger.debug("Found link between %s %s and %s %s", intfdata.name, intfdata.switch.facts['fqdn'], peer_device.name, peer_device.switch.facts['fqdn'])
                                intfdata.neighbors[i] = peer_device
                            except KeyError:
                                pass

    def _recalculate_macs(self):
        for swname, swdata in self.switches.items():
            for mac, macdata in swdata.mac_table.items():
                try:
                    if self.mac_table[mac]['interface'].mac_count > macdata['interface'].mac_count:
                        self.logger.debug("Found better interface %s %s for %s", macdata['interface'], macdata['interface'].switch.facts['fqdn'], str(mac))
                        self.mac_table[mac] = macdata
                except KeyError:
                    self.mac_table[mac] = macdata
