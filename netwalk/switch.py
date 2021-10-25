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

"Define Switch object"

import ipaddress
import logging
import os
from io import StringIO
import datetime as dt
from typing import Dict, Optional, List
from netaddr import EUI

import napalm
import ciscoconfparse
import textfsm
from .interface import Interface


class Switch():
    """
    Switch object to hold data
    Initialize with name and hostname, call retrieve_data
    to connect to device and retrieve automaticlly or
    pass config as string to parse locally
    """

    INTERFACE_TYPES = r"([Pp]ort-channel|\w*Ethernet|Vlan|Loopback)."
    INTERFACE_FILTER = r"^interface " + INTERFACE_TYPES

    def __init__(self,
                 hostname: str,
                 **kwargs):

        self.logger = logging.getLogger(__name__ + hostname)
        self.hostname: str = hostname
        self.interfaces: Dict[str, Interface] = {}
        self.config: Optional[str] = kwargs.get('config', None)
        self.timeout = 30
        self.napalm_optional_args = kwargs.get('napalm_optional_args', None)
        self.init_time = dt.datetime.now()
        self.mac_table: Dict[EUI, dict] = {}
        self.vtp: Optional[str] = None
        self.arp_table: Dict[ipaddress.IPv4Interface, dict] = {}
        self.interfaces_ip = {}
        self.vlans: Optional[Dict[int, dict]] = None
        self.vlans_set = {x for x in range(1,4095)} # VLANs configured on the switch
        self.local_admins: Optional[Dict[str, dict]] = None
        self.facts: dict = kwargs.get('facts', None)

        if self.config is not None:
            self._parse_config()

    def retrieve_data(self,
                      username: str,
                      password: str,
                      napalm_optional_args: dict = {},
                      scan_options: dict={}):

        """
        One-stop function to get data from switch.
        
        Args:
        - username (str)
        - password (str)
        - napalm_optional_args (dict): check Napalm documentation
        - scan_options (dict): Valid keys are 'whitelist' and 'blacklist'. Value must
                               be a list of options to pass to _get_switch_data
        """

        self.napalm_optional_args = napalm_optional_args

        self.connect(username, password, napalm_optional_args)

        self._get_switch_data(**scan_options)
        self.session.close()

    def connect(self, username: str, password: str, napalm_optional_args: dict = None) -> None:
        driver = napalm.get_network_driver('ios')

        if napalm_optional_args is not None:
            self.napalm_optional_args = napalm_optional_args

        self.session = driver(self.hostname,
                              username=username,
                              password=password,
                              timeout=self.timeout,
                              optional_args=self.napalm_optional_args)

        self.logger.info("Connecting to %s", self.hostname)
        self.session.open()

    def get_active_vlans(self):
        vlans = set([1])
        for _, intdata in self.interfaces.items():
            vlans.add(intdata.native_vlan)
            try:
                if len(intdata.allowed_vlan) != 4094:
                    vlans = vlans.union(intdata.allowed_vlan)
            except (AttributeError, TypeError):
                continue

        # Find trunk interfaces with no neighbors
        noneightrunks = []
        for intname, intdata in self.interfaces.items():
            if intdata.mode == "trunk":
                try:
                    assert not isinstance(intdata.neighbors[0], Interface)
                except (IndexError, AssertionError, AttributeError):
                    # Interface has explicit neighbor, exclude
                    continue

                noneightrunks.append(intdata)

                # Find if interface has mac addresses
                activevlans = set()
                for mac, macdata in self.mac_table.items():
                    if macdata['interface'] == intdata:
                        activevlans.add(macdata['vlan'])

                vlans = vlans.union(activevlans)

        # Add vlans with layer3 configured
        for intname, intdata in self.interfaces.items():
            if "vlan" in intdata.name.lower():
                if intdata.is_enabled:
                    vlanid = int(intdata.name.lower().replace("vlan", ""))
                    vlans.add(vlanid)

        # Remove vlans not explicitly configured
        vlans.intersection_update(self.vlans_set)
        return vlans

    def add_interface(self, intobject: Interface):
        intobject.device = self
        self.interfaces[intobject.name] = intobject

    def _parse_config(self):
        if isinstance(self.config, str):
            running = StringIO()
            running.write(self.config)

            # Be kind rewind
            running.seek(0)

            # Get show run an interface access/trunk status
            self.parsed_conf = ciscoconfparse.CiscoConfParse(running)
            interface_config_list: list = self.parsed_conf.find_objects(
                self.INTERFACE_FILTER)

            for intf in interface_config_list:
                thisint = Interface(config=intf.ioscfg)
                self.add_interface(thisint)
        else:
            TypeError("No interface loaded, cannot parse")

    def _get_switch_data(self,
                         whitelist: Optional[List[str]] = None,
                         blacklist: Optional[List[str]] = None):
        
        """
        Get data from switch.
        If no argument is passed, scan all modules

        Args: 
        - whitelist (list[str]): List of modules to scan
        - blacklisst (list[str]): List of modules to exclude from scan

        Either whitelist or blacklist can be passed.
        If both are passed, whitelist takes precedence over blacklist.
        
        Valid values are:
        - 'mac_address'
        - 'interface_status'
        - 'cdp_neighbors'
        - 'vtp'
        - 'vlans'
        - 'l3_int'
        - 'local_admins'

        Running config is ALWAYS returned
        """

        allscans = ['mac_address', 'interface_status', 'cdp_neighbors', 'vtp', 'vlans', 'l3_int', 'local_admins',]
        scan_to_perform = []

        if whitelist is not None:
            for i in whitelist:
                assert i in allscans, "Parameter not recognised in scan list. has to be any of ['mac_address', 'interface_status', 'cdp_neighbors', 'vtp', 'vlans', 'l3_int', 'local_admins',]"

            scan_to_perform = whitelist

        elif blacklist is not None:
            scan_to_perform = allscans
            for i in blacklist:
                assert i in allscans, "Parameter not recognised in scan list. has to be any of ['mac_address', 'interface_status', 'cdp_neighbors', 'vtp', 'vlans', 'l3_int', 'local_admins',]"
                scan_to_perform.remove(i)

        else:
            scan_to_perform = allscans

        self.facts = self.session.get_facts()

        self.init_time = dt.datetime.now()

        self.session.device.write_channel("show run")
        self.session.device.write_channel("\n")
        self.session.device.timeout = 30  # Could take ages...
        self.config = self.session.device.read_until_pattern(
            "end\r\n", max_loops=3000)
        #print("Parsing config")

        self._parse_config()

        if 'mac_address' in scan_to_perform:
            # Get mac address table
            self.mac_table = {} # Clear before adding new data
            mactable = self.session.get_mac_address_table()

            macdict = {EUI(x['mac']): x for x in mactable}

            for k, v in macdict.items():
                if v['interface'] == '':
                    continue

                v['interface'] = v['interface'].replace(
                    "Fa", "FastEthernet").replace("Gi", "GigabitEthernet").replace("Po", "Port-channel")

                v.pop('mac')
                v.pop('static')
                v.pop('moves')
                v.pop('last_move')
                v.pop('active')

                try:
                    v['interface'] = self.interfaces[v['interface']]
                    self.mac_table[k] = v
                except KeyError:
                    #print("Interface {} not found".format(v['interface']))
                    continue

            # Count macs per interface
            for _, data in self.mac_table.items():
                try:
                    data['interface'].mac_count += 1
                except KeyError:
                    pass

        if 'interface_status' in scan_to_perform:
            # Get interface status
            self._parse_show_interface()

        if 'cdp_neighbors' in scan_to_perform:
            self._parse_cdp_neighbors()

        if 'vtp' in scan_to_perform:
            # Get VTP status
            command = "show vtp status"
            result = self.session.cli([command])

            self.vtp = result[command]

        if 'vlans' in scan_to_perform:
            # Get VLANs
            self.vlans = self.session.get_vlans()
            self.vlans_set = set([int(k) for k, v in self.vlans.items()])

        if 'l3_int' in scan_to_perform:
            # Get l3 interfaces
            self.interfaces_ip = self.session.get_interfaces_ip()
            self.arp_table = self.session.get_arp_table()

        if 'local_admins' in scan_to_perform:
            # Get local admins
            self.local_admins = self.session.get_users()


    def _parse_show_interface(self):
        """Parse output of show inteface with greater data collection than napalm"""
        self.session.device.write_channel("show interface")
        self.session.device.write_channel("\n")
        self.session.device.timeout = 30  # Could take ages...
        showint = self.session.device.read_until_prompt(max_loops=3000)
        fsmpath = os.path.dirname(os.path.realpath(__file__)) + "/textfsm_templates/show_interface.textfsm"
        with open(fsmpath, 'r') as fsmfile:
            re_table = textfsm.TextFSM(fsmfile)
            fsm_results = re_table.ParseTextToDicts(showint)

        for intf in fsm_results:
            for k, v in intf.items():
                if k in ('last_in', 'last_out', 'last_out_hang', 'last_clearing'):
                    setattr(self.interfaces[intf['name']], k, self._cisco_time_to_dt(v))
                elif k == 'is_enabled':
                    val = True if 'up' in v else False
                    setattr(self.interfaces[intf['name']], k, val)
                elif k == 'is_up':
                    val = True if 'up' in v else False
                    setattr(self.interfaces[intf['name']], k, val)
                    setattr(self.interfaces[intf['name']], 'protocol_status', v)
                else:
                    setattr(self.interfaces[intf['name']], k, v)

    def _parse_cdp_neighbors(self):
        # Return parsed cdp neighbours
        # [[empty, hostname, ip, platform, local interface, remote interface, version]]
        # [['', 'SMba03_1_Piking', '10.19.6.15', 'cisco WS-C3560G-48TS', 'GigabitEthernet0/49', 'GigabitEthernet0/2', 'Cisco IOS Software, C3560 Software (C3560-IPBASE-M), Version 12.2(35)SE5, RELEASE SOFTWARE (fc1)']]
        self.session.device.write_channel("show cdp neigh detail")
        self.session.device.write_channel("\n")
        self.session.device.timeout = 30  # Could take ages...
        neighdetail = self.session.device.read_until_prompt(max_loops=3000)
        fsmpath = os.path.dirname(os.path.realpath(__file__)) + "/textfsm_templates/show_cdp_neigh_detail.textfsm"
        with open(fsmpath, 'r') as fsmfile:
            re_table = textfsm.TextFSM(fsmfile)
            fsm_results = re_table.ParseText(neighdetail)

        for result in fsm_results:
            self.logger.debug("Found CDP neighbor %s IP %s local int %s, remote int %s", result[1], result[2], result[5], result[4])

        for intname, intdata in self.interfaces.items():
            intdata.neighbors = [] # Clear before adding new data

        for nei in fsm_results:
            neigh_data = {'hostname': nei[1],
                          'ip': nei[2],
                          'platform': nei[3],
                          'remote_int': nei[4]
                          }

            self.interfaces[nei[5]].neighbors.append(neigh_data)

    def _cisco_time_to_dt(self, time: str) -> dt.datetime:
        weeks = 0
        days = 0
        hours = 0
        minutes = 0
        seconds = 0

        if time == 'never':
            # TODO: return uptime
            return dt.datetime(1970, 1, 1, 0, 0, 0)

        if ':' in time:
            hours, minutes, seconds = time.split(':')
            hours = int(hours)
            minutes = int(minutes)
            seconds = int(seconds)

        elif 'y' in time:
            # 2y34w
            years, weeks = time.split('y')
            weeks = weeks.replace('w', '')
            years = int(years)
            weeks = int(weeks)

            weeks = years*54 + weeks

        elif 'h' in time:
            # 3d05h
            days, hours = time.split('d')
            hours = hours.replace('h', '')

            days = int(days)
            hours = int(hours)

        else:
            # 24w2d
            weeks, days = time.split('w')
            days = days.replace('d', '')

            weeks = int(weeks)
            days = int(days)

        delta = dt.timedelta(weeks=weeks, days=days, hours=hours,
                             minutes=minutes, seconds=seconds)

        return self.init_time - delta

    def __str__(self):
        showrun = f"! {self.hostname}"

        try:
            showrun = showrun + f" {self.facts['hostname']}\n"
        except (AttributeError, KeyError):
            showrun = showrun + "\n"

        showrun = showrun + "!\n"

        for intname, intdata in self.interfaces.items():
            showrun = showrun + str(intdata)

        return showrun
