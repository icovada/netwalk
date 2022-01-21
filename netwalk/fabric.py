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

import ipaddress
from typing import Any, Dict
from datetime import datetime as dt
import logging
from socket import timeout as socket_timeout
import concurrent.futures
from netaddr import EUI
from netmiko.ssh_exception import NetMikoAuthenticationException
from napalm.base.exceptions import ConnectionException
from netwalk.switch import Device, Switch
from netwalk.interface import Interface


class Fabric():
    """Defines a fabric, i.e. a graph of connected Devices and their global 
    mac address table

    """
    logger: logging.Logger
    #: A dictionary of {hostname: Switch}
    switches: Dict[str, Switch]

    # TODO: Dict value can be either str or dt, fix
    #: Dictionary of {hostname: status} where status can be "Queued", "Failed" or a datetime of when the discovery was completed.
    #: It is set and used by init_from_seed_device()
    discovery_status: Dict[str, Any]

    #: Calculated global mac address table across all switches in the fabric.
    #: Generated by _recalculate_macs().
    #: Dictionary of {netaddr.EUI (mac address object): attribute_dictionary}. Contains pointer to Interface object where the mac is.
    mac_table: Dict[EUI, dict]

    def __init__(self):
        """Init module"""
        self.logger = logging.getLogger(__name__)
        self.switches = {}
        self.discovery_status = {}
        self.mac_table = {}

    def add_switch(self,
                   host,
                   credentials,
                   napalm_optional_args=[None],
                   **kwargs):
        """
        Try to connect to, and if successful add to fabric, a new switch

        :param host: IP or hostname of device to connect to
        :type host: str
        :param credentials: List of (username, password) tuples to try
        :type credentials: list(tuple(str,str))
        :param napalm_optional_args: Optional_args to pass to NAPALM, as many as you want
        :type napalm_optional_args: list(dict)
        """

        if type(host) == str:
            thisswitch = Switch(host,
                                hostname=host,
                                fabric=self,
                                discovery_status=kwargs.get('discovery_status', None))
        elif type(host) == Device:
            host.promote_to_switch()
            thisswitch = host

        self.logger.info("Creating switch %s", thisswitch.mgmt_address)
        connected = False
        for optional_arg in napalm_optional_args:
            if connected:
                break

            for cred in credentials:
                try:
                    thisswitch.retrieve_data(cred[0], cred[1],
                                             napalm_optional_args=optional_arg)
                    connected = True
                    self.logger.info(
                        "Connection to switch %s successful", thisswitch.mgmt_address)
                    break
                except (ConnectionException, NetMikoAuthenticationException, ConnectionRefusedError, socket_timeout):
                    self.logger.warning(
                        "Login failed, trying next method if available")
                    continue

        # Check if Switch is already in fabric.
        # Hostname is not enough because CDP stops at 40 characters and it might have been added
        # with a cut-off hostname
        if thisswitch.hostname[:40] not in self.switches:
            self.switches[thisswitch.hostname[:40]] = thisswitch

        if not connected:
            self.logger.error(
                "Could not login with any of the specified methods")
            raise ConnectionError(
                "Could not log in with any of the specified methods")

        self.logger.info("Finished discovery of switch %s",
                         thisswitch.hostname)

        return thisswitch

    def init_from_seed_device(self,
                              seed_hosts: str,
                              credentials: list,
                              napalm_optional_args=[None],
                              parallel_threads=10,
                              neigh_validator_callback=None):
        """
        Initialise entire fabric from a seed device.

        :param seed_hosts: List of IP or hostname of seed devices
        :type seed_hosts: str
        :param credentials: List of (username, password) tuples to try
        :type credentials: list
        :param napalm_optional_args: Optional_args to pass to NAPALM for telnet
        :type napalm_optional_args: list(dict(str, str)), optional
        :param neigh_validator_callback: Function accepting a Device object. Return True if device should be actively discovered
        :type neigh_validator_callback: function
        """

        # We can use a with statement to ensure threads are cleaned up promptly
        with concurrent.futures.ThreadPoolExecutor(max_workers=parallel_threads) as executor:
            # Start the load operations and mark each future with its URL
            self.logger.debug("Adding seed hosts to loop")
            future_switch_data = {executor.submit(
                self.add_switch,
                x,
                credentials,
                napalm_optional_args,
                discovery_status="Queued"): x for x in seed_hosts}

            while future_switch_data:
                self.logger.info(
                    "Connecting to switches, %d to go", len(future_switch_data))
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
                        #raise exc

                        # We do not have the switch because fut.result returned an error
                        # Find it looping the fabric
                        swobject = None
                        
                        for swname, swdata in self.switches.items():
                            try:
                                if ipaddress.ip_address(hostname) == swdata.mgmt_address:
                                    swobject = swdata
                                    break
                            except ValueError:
                                # In case hostname is not an IP
                                pass

                            if swdata.hostname == hostname:
                                swobject = swdata
                                break

                        self.logger.info(
                            "Demote %s back to Device from Switch", swobject.hostname)
                        swobject.__class__ = Device
                        swobject.discovery_status = dt.now()
                    else:
                        swobject.discovery_status = dt.now()
                        self.logger.info(
                            "Completed discovery of %s %s", swobject.facts['fqdn'], swobject.hostname)
                        # Check if it has cdp neighbors

                        for _, intdata in swobject.interfaces.items():
                            for nei in intdata.neighbors:
                                self.logger.debug(
                                    "Evaluating neighbour %s", nei.switch.hostname)
                                if type(nei.switch) == Device and nei.switch.discovery_status is None:
                                    scan = True
                                    if neigh_validator_callback is not None:
                                        self.logger.debug("Passing %s to callback function to check whther to scan", nei.switch.hostname)
                                        scan = neigh_validator_callback(nei.switch)
                                        self.logger.debug("Callback function returned %s", scan)
                                    
                                    if scan:
                                        self.logger.info(
                                            "Queueing discover for %s", nei.switch.hostname)
                                        nei.switch.discovery_status = "Queued"

                                        future_switch_data[executor.submit(self.add_switch,
                                                                        nei.switch,
                                                                        credentials,
                                                                        napalm_optional_args)] = nei.switch.hostname
                                    else:
                                        nei.switch.discovery_status = "Skipped"
                                        self.logger.info("Skipping %s, callback returned False", nei.switch.hostname)
                                else:
                                    self.logger.debug(
                                        "Skipping %s, already discovered", nei.switch.hostname)

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
        hostname_only_fabric = {}
        
        for k, v in self.switches.items():
            if v.facts is not None:
                hostname_only_fabric[v.facts['hostname']] =  v
            else:
                hostname_only_fabric[k] =  k

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
                            self.logger.debug("Found link between %s %s and %s %s", intfdata.name,
                                              intfdata.switch.facts['fqdn'], peer_device.name, peer_device.switch.facts['fqdn'])
                        except KeyError:
                            # Hostname over 40 char
                            try:
                                peer_device = short_fabric[switch[:40]
                                                           ].interfaces[port]
                                self.logger.debug("Found link between %s %s and %s %s", intfdata.name,
                                                  intfdata.switch.facts['fqdn'], peer_device.name, peer_device.switch.facts['fqdn'])
                                intfdata.neighbors[i] = peer_device
                                peer_device.neighbors[0] = intfdata
                            except KeyError:
                                try:
                                    peer_device = hostname_only_fabric[switch].interfaces[port]
                                    self.logger.debug("Found link between %s %s and %s %s", intfdata.name,
                                                      intfdata.switch.facts['fqdn'], peer_device.name, peer_device.switch.facts['fqdn'])
                                    intfdata.neighbors[i] = peer_device
                                    peer_device.neighbors[0] = intfdata
                                except KeyError:
                                    self.logger.debug("Could not find link between %s %s and %s %s",
                                                      intfdata.name, intfdata.switch.facts['fqdn'], port, switch)
                                    pass

    def _recalculate_macs(self):
        """
        Refresh count macs per interface.
        Tries to guess where mac addresses are by assigning them to the interface with the lowest total mac count
        """
        for swname, swdata in self.switches.items():
            if isinstance(swdata, Switch):
                for intname, intdata in swdata.interfaces.items():
                    intdata.mac_count = 0

                for _, data in swdata.mac_table.items():
                    try:
                        data['interface'].mac_count += 1
                    except KeyError:
                        pass

        for swname, swdata in self.switches.items():
            if isinstance(swdata, Switch):
                for mac, macdata in swdata.mac_table.items():
                    try:
                        if self.mac_table[mac]['interface'].mac_count > macdata['interface'].mac_count:
                            self.logger.debug("Found better interface %s %s for %s",
                                              macdata['interface'].name, macdata['interface'].switch.hostname, str(mac))
                            self.mac_table[mac] = macdata
                    except KeyError:
                        self.mac_table[mac] = macdata

    def find_paths(self, start_sw, end_sw):
        """
        Return a list of all interfaces from 'start' Switch to 'end' Switch

        :param start_sw: Switch to begin search from
        :type start_sw: netwalk.Switch
        :param end_sw: List of target switch or switches
        :type end_sw: netwalk.Switch
        """
        def _inside_recursive(start_int, end_sw, path=[]):
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
                                    newpaths = _inside_recursive(
                                        intdata, end_sw, this_path)
                                    for newpath in newpaths:
                                        paths.append(newpath)

            return paths

        all_possible_paths = []
        for intname, intdata in start_sw.interfaces.items():
            if hasattr(intdata, 'neighbors'):
                if len(intdata.neighbors) == 1:
                    if type(intdata.neighbors[0]) == Interface:
                        assert len(end_sw) > 0
                        thispath = _inside_recursive(
                            intdata, end_sw, path=[intdata])
                        for path in thispath:
                            all_possible_paths.append(path)

        return all_possible_paths
