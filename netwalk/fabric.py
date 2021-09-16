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

"Define Fabric object"

import logging

import concurrent.futures
from napalm.base.exceptions import ConnectionException
from netmiko.ssh_exception import NetMikoAuthenticationException
from netaddr import EUI

from datetime import datetime as dt

from typing import Any

from .switch import Switch
from .interface import Interface

class Fabric():
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.switches: dict[str, Switch] = {}
        self.discovery_status: dict[str, Any[dt, str]] = {}
        self.mac_table: dict[EUI, dict] = {}

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

        self.logger.info("Creating switch %s", host)
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
                    self.logger.info("Connection to switch %s successful", host)
                    break
                except (ConnectionException, NetMikoAuthenticationException, ConnectionRefusedError):
                    self.logger.warning("Login failed, trying next method if available")
                    continue

        if not connected:
            self.logger.error("Could not login with any of the specified methods")
            raise ConnectionError("Could not log in with any of the specified methods")

        clean_fqdn = thisswitch.facts['fqdn'].replace(".not set", "")
        if clean_fqdn == "Unknown":
            clean_fqdn = thisswitch.facts['hostname']
        self.logger.info("Finished discovery of switch %s", clean_fqdn)
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
                self.logger.info("Connecting to switches, %d to go", len(future_switch_data))
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
                        self.discovery_status[hostname] = dt.now()
                        self.logger.info("Completed discovery of %s %s", swobject.facts['fqdn'], swobject.hostname)
                        # Check if it has cdp neighbors

                        for _, intdata in swobject.interfaces.items():
                            if hasattr(intdata, "neighbors"):
                                for nei in intdata.neighbors:
                                    if not isinstance(nei, Interface):
                                        self.logger.debug("Evaluating neighbour %s", nei['hostname'])
                                        if nei['hostname'] not in self.switches and nei['ip'] not in self.discovery_status:
                                            try:
                                                assert "AIR" not in nei['platform']
                                                assert "CAP" not in nei['platform']
                                                assert "N77" not in nei['platform']
                                                assert "axis" not in nei['hostname']
                                            except AssertionError:
                                                self.logger.debug("Skipping %s, %s", nei['hostname'], nei['platform'])
                                                continue

                                            self.logger.info("Queueing discover for %s", nei['hostname'])
                                            self.discovery_status[nei['ip']] = "Queued"

                                            future_switch_data[executor.submit(self.add_switch,
                                                                               nei['ip'],
                                                                               credentials,
                                                                               napalm_optional_args)] = nei['ip']
                                        else:
                                            self.logger.debug("Skipping %s, already discovered", nei['hostname'])

        self.logger.info("Discovery complete, crunching data")
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
        hostname_only_fabric = {v.facts['hostname']: v for k, v in self.switches.items()}

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
                            if len(peer_device.neighbors) == 0:
                                peer_device.neighbors.append(intfdata)
                            else:
                                peer_device.neighbors[0] = intfdata
                            self.logger.debug("Found link between %s %s and %s %s", intfdata.name, intfdata.switch.facts['fqdn'], peer_device.name, peer_device.switch.facts['fqdn'])
                        except KeyError:
                            # Hostname over 40 char
                            try:
                                peer_device = short_fabric[switch[:40]
                                                           ].interfaces[port]
                                self.logger.debug("Found link between %s %s and %s %s", intfdata.name, intfdata.switch.facts['fqdn'], peer_device.name, peer_device.switch.facts['fqdn'])
                                intfdata.neighbors[i] = peer_device
                                peer_device.neighbors[0] = intfdata
                            except KeyError:
                                try:
                                    peer_device = hostname_only_fabric[switch].interfaces[port]
                                    self.logger.debug("Found link between %s %s and %s %s", intfdata.name, intfdata.switch.facts['fqdn'], peer_device.name, peer_device.switch.facts['fqdn'])
                                    intfdata.neighbors[i] = peer_device
                                    peer_device.neighbors[0] = intfdata
                                except KeyError:
                                    self.logger.debug("Could not find link between %s %s and %s %s", intfdata.name, intfdata.switch.facts['fqdn'], port, switch)
                                    pass

    def _recalculate_macs(self):
        # Refresh count macs per interface
        for swname, swdata in self.switches.items():
            for intname, intdata in swdata.interfaces.items():
                intdata.mac_count = 0
                
            for _, data in swdata.mac_table.items():
                try:
                    data['interface'].mac_count += 1
                except KeyError:
                    pass


        for swname, swdata in self.switches.items():
            for mac, macdata in swdata.mac_table.items():
                try:
                    if self.mac_table[mac]['interface'].mac_count > macdata['interface'].mac_count:
                        self.logger.debug("Found better interface %s %s for %s", macdata['interface'], macdata['interface'].switch.facts['fqdn'], str(mac))
                        self.mac_table[mac] = macdata
                except KeyError:
                    self.mac_table[mac] = macdata

    def find_paths(self, start_sw, end_sw):
        """
        Return a list of all interfaces from 'start' Switch to 'end' Switch

        start_sw: Switch
        end_sw: list[Switch]
        """
        def _inside_recursive(start_int, end_sw, path = []):
            switch = start_int.neighbors[0].switch
            path = path + [start_int.neighbors[0]]
            if switch in end_sw:
                return [path]
            paths = []
            for _, intdata in switch.interfaces.items():
                if hasattr(intdata, 'neighbors'):
                    if len(intdata.neighbors) == 1:
                        if type(intdata.neighbors[0]) == Interface:
                            neigh_int = intdata.neighbors[0]
                            if type(neigh_int) == Interface:
                                if intdata not in path:
                                    this_path = path + [intdata]
                                    newpaths = _inside_recursive(intdata, end_sw, this_path)
                                    for newpath in newpaths:
                                        paths.append(newpath)

            return paths


        all_possible_paths = []
        for intname, intdata in start_sw.interfaces.items():
            if hasattr(intdata, 'neighbors'):
                if len(intdata.neighbors) == 1:
                    if type(intdata.neighbors[0]) == Interface:
                        assert len(end_sw) > 0
                        thispath = _inside_recursive(intdata, end_sw, path=[intdata])
                        for path in thispath:
                            all_possible_paths.append(path)
        
        return all_possible_paths
