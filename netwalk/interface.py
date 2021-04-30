"Define Interface object"

import logging
import re

from typing import List, Optional


class Interface():
    """
    Define an interface
    Can be initialised with any of the values or by passing
    an array containing each line of the interface configuration
    """

    def __init__(self, **kwargs):
        self.logger = logging.getLogger(__name__)
        self.name: str = kwargs.get('name', None)
        self.description: Optional[str] = kwargs.get('description', None)
        self.mode: str = kwargs.get('mode', 'access')
        self.channel_group: Optional[int] = kwargs.get('channel_group', None)
        self.channel_protocol: Optional[str] = kwargs.get(
            'channel_protocol', None)
        self.allowed_vlan: set = kwargs.get('allowed_vlan', None)
        self.native_vlan: int = kwargs.get('native_vlan', 1)
        self.voice_vlan: Optional[int] = kwargs.get('voice_vlan', None)
        self.switch = kwargs.get('switch', None)
        self.parent_interface = kwargs.get('parent_interface', None)
        self.is_up: bool = kwargs.get('is_up', True)
        self.is_enabled: bool = kwargs.get('is_enabled', True)
        self.config: List[str] = kwargs.get('config', None)
        self.unparsed_lines = kwargs.get('unparsed_lines', [])
        self.mac_count = 0
        self.type_edge = kwargs.get('type_edge', False)
        self.bpduguard = kwargs.get('bpduguard', False)
        self.routed_port = kwargs.get('routed_port', False)
        self.neighbors = kwargs.get('neighbors', [])

        if self.config is not None:
            self.parse_config()

    def parse_config(self):
        "Parse configuration from show run"
        if isinstance(self.config, str):
            self.config = self.config.split("\n")

        for line in self.config:
            cleanline = line.strip()
            # Port mode. Some switches have it first, some last, so check it first thing
            match = re.search(r"switchport mode (.*)$", cleanline)
            if match is not None:
                self.mode = match.groups()[0].strip()
                if self.mode == 'trunk' and self.allowed_vlan is None:
                    self.allowed_vlan = set([x for x in range(1, 4095)])
                continue

        for line in self.config:
            cleanline = line.strip()
            # Find interface name
            match = re.search(r"^interface ([A-Za-z\-]*(\/*\d*)+)", cleanline)
            if match is not None:
                self.name = match.groups()[0]
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
                self.channel_group = match.groups()[0]
                self.channel_protocol = match.groups()[1]
                continue


            # Native vlan
            match = re.search(r"switchport access vlan (.*)$", cleanline)
            if match is not None and self.mode == 'access':
                self.native_vlan = int(match.groups()[0])
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

            # Unknown, unparsable line
            if any([x in cleanline for x in ["vrf forwarding", "ip address"]]):
                self.routed_port = True

            self.unparsed_lines.append(cleanline)


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

        if self.description is not None:
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
            # TODO: output l3 info
            pass

        for line in self.unparsed_lines:
            fullconfig = fullconfig + line + "\n"

        if self.is_enabled:
            fullconfig = fullconfig + " no shutdown\n"
        else:
            fullconfig = fullconfig + " shutdown\n"

        fullconfig = fullconfig + "!\n"
        return fullconfig
