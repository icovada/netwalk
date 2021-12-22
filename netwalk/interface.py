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
from netaddr import EUI

from typing import ForwardRef, List, Optional, Any

Switch = ForwardRef('Switch')
Interface = ForwardRef('Interface')

class Interface():
    """
    Define an interface
    Can be initialised with any of the values or by passing
    an array containing each line of the interface configuration.

    Converted to str it outputs the corresponding show running configuration.
    All unparsed lines go to "unparsed_lines" and are returned when converted to str
    """

    logger: logging.Logger
    name: str
    description: Optional[str]
    #: data from show interface
    abort: Optional[str]
    address: dict
    allowed_vlan: set
    #: data from show interface
    bandwidth: Optional[str]
    #: data from show interface
    bia: Optional[str]
    bpduguard: bool
    channel_group: Optional[int]
    channel_protocol: Optional[str]
    child_interfaces: List[Interface]
    config: List[str]
    counters: Optional[dict]
    #: data from show interface
    crc: Optional[str]
    #: data from show interface
    delay: Optional[str]
    device: Optional[Switch]
    #: data from show interface
    duplex: Optional[str]
    encapsulation: Optional[str]
    #: data from show interface
    hardware_type: Optional[str]
    #: data from show interface
    input_errors: Optional[str]
    #: data from show interface
    input_packets: Optional[str]
    #: data from show interface
    input_rate: Optional[str]
    is_enabled: bool
    is_up: bool
    #: data from show interface
    last_clearing: Optional[datetime]
    #: data from show interface
    last_in: Optional[datetime]
    #: data from show interface
    last_out_hang: Optional[datetime]
    #: data from show interface
    last_out: Optional[datetime]
    mac_address: Optional[EUI]
    #: Total number of mac addresses behind this interface
    mac_count: int = 0
    #: data from show interface
    media_type: Optional[str]
    mode: str
    #: data from show interface
    mtu: Optional[int]
    native_vlan: int
    # TODO: can be a list of either dict or Interface
    #: List of neighbors connected to the interface. List because CDP might show more than one.
    #: If the neighbour is another Switch, it's turned into the other end's Interface object
    #: otherwise remains a dict containing all the parsed data.
    neighbors: List[Any]
    #: data from show interface
    output_errors: Optional[str]
    #: data from show interface
    output_packets: Optional[str]
    #: data from show interface
    output_rate: Optional[str]
    parent_interface: Optional[Interface]
    protocol_status: Optional[str]
    #: data from show interface
    queue_strategy: Optional[str]
    routed_port: bool
    sort_order: Optional[int]
    #: data from show interface
    speed: Optional[str]
    #: pointer to parent's Switch object
    switch: Optional[Switch]
    type_edge: bool
    unparsed_lines: List[str]
    voice_vlan: Optional[int]
    vrf: str

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
        self.child_interfaces: List[Interface] = kwargs.get('child_interfaces', [])
        self.config: List[str] = kwargs.get('config', [])
        self.counters: Optional[dict] = kwargs.get('counters', None)
        self.crc: Optional[str] = kwargs.get('crc', None)
        self.delay: Optional[str] = kwargs.get('delay', None)
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
        self.mac_address: Optional[EUI] = kwargs.get('mac_address', None)
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
            

    def parse_config(self, second_pass=False):
        "Parse configuration from show run"
        if isinstance(self.config, str):
            self.config = self.config.split("\n")

        if not second_pass:
            # Pass values to unparsed_lines as value not reference
            self.unparsed_lines = self.config[:]

        # Parse port mode first. Some switches have it first, some last, so check it first thing
        for line in self.unparsed_lines:
            cleanline = line.strip()
            match = re.search(r"switchport mode (.*)$", cleanline)
            if match is not None:
                self.mode = match.groups()[0].strip()
                if self.mode == 'trunk' and self.allowed_vlan is None:
                    self.allowed_vlan = set([x for x in range(1, 4095)])
                self.unparsed_lines.remove(line)
                continue

        # Cycle through lines, make second array so we don't modify data we are looping over
        for line in [x for x in self.unparsed_lines]:
            cleanline = line.strip()
            
            # L2 data
            # Find interface name
            match = re.search(r"^interface ([A-Za-z\-]*(\/*\d*)+\.?\d*)", cleanline)
            if match is not None:
                self.name = match.groups()[0]
                if "vlan" in self.name.lower():
                    self.routed_port = True
                    self.mode = 'access'
                    self.native_vlan = int(self.name.lower().replace("vlan",""))

                self.unparsed_lines.remove(line)
                continue

            # Find description
            match = re.search(r"description (.*)$", cleanline)
            if match is not None:
                self.description = match.groups()[0]
                self.unparsed_lines.remove(line)
                continue

            # Port channel ownership
            match = re.search(r"channel\-group (\d+) mode (\w+)", cleanline)
            if match is not None:
                po_id, mode = match.groups()
                if self.switch is not None:
                    parent_po = self.switch.interfaces.get(f'Port-channel{str(po_id)}', None)
                    if parent_po is not None:
                        parent_po.add_child_interface(self)
                        self.unparsed_lines.remove(line)
                
                self.channel_group = po_id
                self.channel_protocol = mode
                continue

            # Native vlan
            match = re.search(r"switchport access vlan (.*)$", cleanline)
            if match is not None and self.mode != 'trunk':
                self.native_vlan = int(match.groups()[0])
                self.unparsed_lines.remove(line)
                continue

            # Voice native vlan
            match = re.search(r"switchport voice vlan (.*)$", cleanline)
            if match is not None and self.mode == 'access':
                self.voice_vlan = int(match.groups()[0])
                self.unparsed_lines.remove(line)
                continue

            # Trunk native vlan
            match = re.search(r"switchport trunk native vlan (.*)$", cleanline)
            if match is not None and self.mode == 'trunk':
                self.native_vlan = int(match.groups()[0])
                self.unparsed_lines.remove(line)
                continue

            # Trunk allowed vlan
            match = re.search(
                r"switchport trunk allowed vlan ([0-9\-\,]*)$", cleanline)
            if match is not None:
                self.allowed_vlan = self._allowed_vlan_to_list(
                    match.groups()[0])
                self.unparsed_lines.remove(line)
                continue

            # Trunk allowed vlan add
            match = re.search(
                r"switchport trunk allowed vlan add ([0-9\-\,]*)$", cleanline)
            if match is not None:
                new_vlans = self._allowed_vlan_to_list(match.groups()[0])
                self.allowed_vlan.update(list(new_vlans))
                self.unparsed_lines.remove(line)
                continue

            # Tagged routed interface
            match = re.search(
                r"encapsulation dot1q?Q? (\d*)( native)?$", cleanline)
            if match is not None:
                self.mode = "access"
                self.native_vlan = int(match.groups()[0])
                self.unparsed_lines.remove(line)
                continue

            # Portfast
            match = re.search(
                r"spanning-tree portfast", cleanline)
            if match is not None:
                if "trunk" in cleanline and self.mode == "trunk":
                    self.type_edge = True
                elif "trunk" not in cleanline and self.mode == "access":
                    self.type_edge = True
                
                self.unparsed_lines.remove(line)
                continue

            match = re.search(
                r"spanning-tree bpduguard", cleanline)
            if match is not None:
                self.bpduguard = True
                self.unparsed_lines.remove(line)
                continue

            if "no shutdown" in line:
                self.is_enabled = True
                self.unparsed_lines.remove(line)
                continue
            elif "shutdown" in line:
                self.is_enabled = False
                self.unparsed_lines.remove(line)
                continue

            # Legacy syntax, ignore
            if "switchport trunk encapsulation" in line:
                self.unparsed_lines.remove(line)
                continue

            # L3 parsing
            # Parse VRF
            match = re.search(
                r'vrf forwarding (.*)', cleanline)
            if match is not None:
                self.vrf = match.groups()[0]
                self.unparsed_lines.remove(line)
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
                self.unparsed_lines.remove(line)
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
                    self.unparsed_lines.remove(line)
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

                self.unparsed_lines.remove(line)
                continue

            if cleanline == '' or cleanline == '!':
                self.unparsed_lines.remove(line)

    def add_child_interface(self, child_interface) -> None:
        """Method to add interface to child interfaces and assign it a parent"""
        self.child_interfaces.append(child_interface)
        child_interface.parent_interface = self

    def add_neighbor(self, neigh_int: Interface) -> None:
        "Method to add bidirectional neighborship to an interface"
        # Add bidirectional link
        self.neighbors.append(neigh_int) if neigh_int not in self.neighbors else None
        neigh_int.neighbors.append(self) if self not in neigh_int.neighbors else None

    def _calculate_sort_order(self) -> None:
        """Generate unique sorting number from port id to sort interfaces meaningfully"""
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

            if "." in port_number[-1]:
                last_port, subint = port_number[-1].split(".")
            else:
                last_port = port_number[-1]
                subint = 0
            for i in port_number[0:-1]:
                sortid += str(i).zfill(3)

            sortid += str(last_port).zfill(3)
            sortid += str(subint).zfill(4)

            self.sort_order = int(sortid)

    def _allowed_vlan_to_list(self, vlanlist: str) -> set:
        """
        Expands vlan ranges

        :param vlanlist: String of vlans from config, i.e. 1,2,3-5
        :type vlanlist: str

        :return: Set of vlans
        :rtype: set
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
        """Generate show run from self data"""
        if self.name is None:
            raise KeyError("Must define at least a name")

        fullconfig = f"interface {self.name}\n"

        if self.description != "":
            fullconfig = fullconfig + f" description {self.description}\n"
        
        if isinstance(self.parent_interface, Interface):
            if "Port-channel" in self.parent_interface.name:
                fullconfig += f" channel-group {self.channel_group} mode {self.channel_protocol}\n"

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
