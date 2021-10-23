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

"Define Interface object"

from datetime import datetime
import logging
import re
import ipaddress

from typing import List, Optional, Any


class Interface():
    """
    Define an interface
    Can be initialised with any of the values or by passing
    an array containing each line of the interface configuration
    """

    def __init__(self, **kwargs):
        from netwalk.switch import Switch
        self.logger = logging.getLogger(__name__)
        self.name: str = kwargs.get('name', None)
        self.description: Optional[str] = kwargs.get('description', "")

        self.abort: Optional[str] = kwargs.get('abort', None)
        self.address: dict = kwargs.get('address', {})
        self.allowed_vlan: set = kwargs.get('allowed_vlan', None)
        self.bandwidth: Optional[str] = kwargs.get('bandwidth', None)
        self.bia: Optional[str] = kwargs.get('bia', None)
        self.bpduguard: bool = kwargs.get('bpduguard', False)
        self.channel_group: Optional[int] = kwargs.get('channel_group', None)
        self.channel_protocol: Optional[str] = kwargs.get('channel_protocol', None)
        self.config: List[str] = kwargs.get('config', None)
        self.counters: Optional[dict] = kwargs.get('counters', None)
        self.crc: Optional[str] = kwargs.get('crc', None)
        self.delay: Optional[str] = kwargs.get('delay', None)
        self.device: Optional[Switch] = kwargs.get('switch', None)
        self.duplex: Optional[str] = kwargs.get('duplex', None)
        self.encapsulation: Optional[str] = kwargs.get('encapsulation', None)
        self.hardware_type: Optional[str] = kwargs.get('hardware_type', None)
        self.input_errors: Optional[str] = kwargs.get('input_errors', None)
        self.input_packets: Optional[str] = kwargs.get('input_packets', None)
        self.input_rate: Optional[str] = kwargs.get('input_rate', None)
        self.is_enabled: bool = kwargs.get('is_enabled', True)
        self.is_up: bool = kwargs.get('is_up', True)
        self.last_clearing: Optional[datetime] = kwargs.get('last_clear', None)
        self.last_in: Optional[datetime] = kwargs.get('last_in', None)
        self.last_out_hang: Optional[datetime] = kwargs.get('last_out_hang', None)
        self.last_out: Optional[datetime] = kwargs.get('last_out', None)
        self.mac_count: int = 0
        self.media_type: Optional[str] = kwargs.get('media_type', None)
        self.mode: str = kwargs.get('mode', 'access')
        self.mtu: Optional[int] = kwargs.get('mtu', None)
        self.native_vlan: int = kwargs.get('native_vlan', 1)
        self.neighbors: List[Any[Interface, dict]] = kwargs.get('neighbors', [])
        self.output_errors: Optional[str] = kwargs.get('output_errors', None)
        self.output_packets: Optional[str] = kwargs.get('output_packets', None)
        self.output_rate: Optional[str] = kwargs.get('output_rate', None)
        self.parent_interface: Optional[Interface] = kwargs.get('parent_interface', None)
        self.protocol_status: Optional[str] = kwargs.get('protocol_status', None)
        self.queue_strategy: Optional[str] = kwargs.get('queue_strategy', None)
        self.routed_port: bool = kwargs.get('routed_port', False)
        self.sort_order: Optional[int] = kwargs.get('sort_order', None)
        self.speed: Optional[int] = kwargs.get('speed', None)
        self.speed: Optional[str] = kwargs.get('speed', None)
        self.switch: Optional[Switch] = kwargs.get('switch', None)
        self.type_edge: bool = kwargs.get('type_edge', False)
        self.unparsed_lines: List[str] = kwargs.get('unparsed_lines', [])
        self.voice_vlan: Optional[int] = kwargs.get('voice_vlan', None)
        self.vrf: str = kwargs.get('vrf', "default")

        if self.config is not None:
            self.parse_config()

        if self.name is not None:
            self._calculate_sort_order()
            

    def parse_config(self):
        "Parse configuration from show run"
        if isinstance(self.config, str):
            self.config = self.config.split("\n")
        
        # Parse port mode first. Some switches have it first, some last, so check it first thing
        for line in self.config:
            cleanline = line.strip()
            match = re.search(r"switchport mode (.*)$", cleanline)
            if match is not None:
                self.mode = match.groups()[0].strip()
                if self.mode == 'trunk' and self.allowed_vlan is None:
                    self.allowed_vlan = set([x for x in range(1, 4095)])
                continue

        for line in self.config:
            cleanline = line.strip()
            
            # L2 data
            # Find interface name
            match = re.search(r"^interface ([A-Za-z\-]*(\/*\d*)+)", cleanline)
            if match is not None:
                self.name = match.groups()[0]
                if "vlan" in self.name.lower():
                    self.routed_port = True
                    self.mode = 'access'
                    self.native_vlan = int(self.name.lower().replace("vlan",""))
                continue

            # Port mode. Already parsed, skip and do not add to unparsed lines
            match = re.search(r"switchport mode (.*)$", cleanline)
            if match is not None:
                continue

            # Find description
            match = re.search(r"description (.*)$", cleanline)
            if match is not None:
                self.description = match.groups()[0]
                continue

            # Find port-channel properties
            match = re.search(r"channel-group (\d*) mode (\w*)", cleanline)
            if match is not None:
                self.channel_group = int(match.groups()[0])
                self.channel_protocol = match.groups()[1]
                continue

            # Native vlan
            match = re.search(r"switchport access vlan (.*)$", cleanline)
            if match is not None and self.mode != 'trunk':
                self.native_vlan = int(match.groups()[0])
                continue

            # Voice native vlan
            match = re.search(r"switchport voice vlan (.*)$", cleanline)
            if match is not None and self.mode == 'access':
                self.voice_vlan = int(match.groups()[0])
                continue

            # Trunk native vlan
            match = re.search(r"switchport trunk native vlan (.*)$", cleanline)
            if match is not None and self.mode == 'trunk':
                self.native_vlan = int(match.groups()[0])
                continue

            # Trunk allowed vlan
            match = re.search(
                r"switchport trunk allowed vlan ([0-9\-\,]*)$", cleanline)
            if match is not None:
                self.allowed_vlan = self._allowed_vlan_to_list(
                    match.groups()[0])
                continue

            # Trunk allowed vlan add
            match = re.search(
                r"switchport trunk allowed vlan add ([0-9\-\,]*)$", cleanline)
            if match is not None:
                new_vlans = self._allowed_vlan_to_list(match.groups()[0])
                self.allowed_vlan.update(list(new_vlans))
                continue

            # Portfast
            match = re.search(
                r"spanning-tree portfast", cleanline)
            if match is not None:
                if "trunk" in cleanline and self.mode == "trunk":
                    self.type_edge = True
                elif "trunk" not in cleanline and self.mode == "access":
                    self.type_edge = True
                
                continue

            match = re.search(
                r"spanning-tree bpduguard", cleanline)
            if match is not None:
                self.bpduguard = True
                continue

            if "no shutdown" in line:
                self.is_enabled = True
                continue
            elif "shutdown" in line:
                self.is_enabled = False
                continue

            # Legacy syntax, ignore
            if "switchport trunk encapsulation" in line:
                continue

            # L3 parsing
            # Parse VRF
            match = re.search(
                r'vrf forwarding (.*)', cleanline)
            if match is not None:
                self.vrf = match.groups()[0]
                continue

            # Parse 'normal' ipv4 address
            match = re.search(
                r'ip address (\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}) (\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\s?(secondary)?', cleanline)
            if match is not None:
                address, netmask, secondary = match.groups()
                addrobj = ipaddress.ip_interface(f"{address}/{netmask}")

                addr_type = 'primary' if secondary is None else 'secondary'

                try:
                    assert 'ipv4' in self.address
                except AssertionError:
                    self.address['ipv4'] = {}
                
                self.address['ipv4'][addrobj] = {'type': addr_type}
                self.routed_port = True
                continue

            # Parse HSRP addresses
            match = re.search(
                r"standby (\d{1,3})?\s?(ip|priority|preempt|version)\s?(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}|\d*)?\s?(secondary)?", cleanline)
            if match is not None:
                grpid, command, argument, secondary = match.groups()
                if grpid is None:
                    grpid = 0
                else:
                    grpid = int(grpid)

                try:
                    assert 'hsrp' in self.address
                except AssertionError:
                    self.address['hsrp'] = {'version': 1, 'groups': {}}

                if command == 'version':
                    self.address['hsrp']['version'] = int(argument)
                    continue

                try:
                    assert grpid in self.address['hsrp']['groups']
                except AssertionError:
                    self.address['hsrp']['groups'][grpid] = {'priority': 100, 'preempt': False, 'secondary': []}

                if command == 'ip':
                    if secondary is not None:
                        self.address['hsrp']['groups'][grpid]['secondary'].append(ipaddress.ip_address(argument))
                    else:
                        self.address['hsrp']['groups'][grpid]['address'] = ipaddress.ip_address(argument)
                elif command == 'priority':
                    self.address['hsrp']['groups'][grpid]['priority'] = int(argument)
                elif command == 'preempt':
                    self.address['hsrp']['groups'][grpid]['preempt'] = True
                continue

            if cleanline != '' and cleanline != '!':
                self.unparsed_lines.append(cleanline)


    def _calculate_sort_order(self) -> None:
        if 'Port-channel' in self.name:
            id = self.name.replace('Port-channel', '')
            self.sort_order = int(id) + 1000000

        elif 'Ethernet' in self.name:
            try:
                portid = self.name.split('Ethernet')[1]
            except IndexError:
                self.sort_order = 0
                
            sortid = ""
            port_number = portid.split('/')
            for i in port_number:
                sortid = sortid + str(i).zfill(3)

            self.sort_order = int(sortid)

    def _allowed_vlan_to_list(self, vlanlist: str) -> set:
        """
        Expands vlan ranges

        Args:
          - vlanlist (str): String of vlans from config, i.e. 1,2,3-5

        Returns:
          - set
        """

        split = vlanlist.split(",")
        out = set()
        for vlan in split:
            if "-" in vlan:
                begin, end = vlan.split("-")
                out.update(range(int(begin), int(end)+1))
            else:
                out.add(int(vlan))

        return out

    def __str__(self) -> str:
        if self.name is None:
            raise KeyError("Must define at least a name")

        fullconfig = f"interface {self.name}\n"

        if self.description != "":
            fullconfig = fullconfig + f" description {self.description}\n"

        if not self.routed_port:
            fullconfig = fullconfig + f" switchport mode {self.mode}\n"

            if self.mode == "access":
                fullconfig = fullconfig + f" switchport access vlan {self.native_vlan}\n"

            elif self.mode== "trunk":
                fullconfig = fullconfig + f" switchport trunk native vlan {self.native_vlan}\n"
                if self.allowed_vlan is None:
                    fullconfig = fullconfig + " switchport trunk allowed vlan all\n"
                elif len(self.allowed_vlan) != 4094:
                    sorted_allowed_vlan = list(self.allowed_vlan)
                    sorted_allowed_vlan.sort()
                    vlan_str = ",".join(map(str, sorted_allowed_vlan))
                    fullconfig = fullconfig + f" switchport trunk allowed vlan {vlan_str}\n"
                else:
                    fullconfig = fullconfig + " switchport trunk allowed vlan all\n"
            else:
                self.logger.warning("Port %s mode %s", self.name, self.mode)


            if self.mode == "access" and self.voice_vlan is not None:
                fullconfig = fullconfig + f" switchport voice vlan {self.voice_vlan}\n"

            if self.type_edge:
                fullconfig = fullconfig + " spanning-tree portfast"

                if self.mode == "trunk":
                    fullconfig = fullconfig + " trunk\n"
                else:
                    fullconfig = fullconfig + "\n"

            if self.bpduguard:
                fullconfig = fullconfig + " spanning-tree bpduguard enable\n"

        else:
            if self.vrf != 'default':
                fullconfig = fullconfig + " vrf forwarding " + self.vrf + "\n"

            if 'ipv4' in self.address:
                for k, v in self.address['ipv4'].items():
                    fullconfig = fullconfig + f" ip address {k.ip} {k.netmask}"
                    if v['type'] == 'secondary':
                        fullconfig = fullconfig + " secondary\n"
                    elif v['type'] == 'primary':
                        fullconfig = fullconfig + "\n"

            if 'hsrp' in self.address:
                if self.address['hsrp']['version'] != 1:
                    fullconfig = fullconfig + " standby version " + str(self.address['hsrp']['version']) + "\n"
                for k, v in self.address['hsrp']['groups'].items():
                    line_begin = f" standby {k} " if k != 0 else " standby "
                    fullconfig = fullconfig + line_begin + "ip " + str(v['address']) + "\n"
                    for secaddr in v['secondary']:
                        fullconfig = fullconfig + line_begin + "ip " + str(secaddr) + " secondary\n"
                    if v['priority'] != 100:
                        fullconfig = fullconfig + line_begin + "priority " + str(v['priority']) + "\n"
                    if v['preempt']:
                        fullconfig = fullconfig + line_begin + "preempt\n"

        for line in self.unparsed_lines:
            fullconfig = fullconfig + line + "\n"

        if self.is_enabled:
            fullconfig = fullconfig + " no shutdown\n"
        else:
            fullconfig = fullconfig + " shutdown\n"

        fullconfig = fullconfig + "!\n"
        return fullconfig
