import concurrent.futures
import datetime as dt
import re
from io import StringIO
from typing import List, Optional

import ciscoconfparse
import napalm
import textfsm
from napalm.base.exceptions import ConnectionException
from netmiko.ssh_exception import NetMikoAuthenticationException
from netaddr import EUI


class Fabric():
    def __init__(self):
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
            for cred in credentials:
                try:
                    thisswitch.retrieve_data(cred[0], cred[1],
                                             napalm_optional_args=optional_arg)
                    connected = True
                except (ConnectionException, NetMikoAuthenticationException):
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

            future_switch_data = {executor.submit(
                self.add_switch,
                x,
                credentials,
                napalm_optional_args): x for x in seed_hosts}

            while future_switch_data:
                done, _ = concurrent.futures.wait(future_switch_data,
                                                  return_when=concurrent.futures.FIRST_COMPLETED)

                for fut in done:
                    hostname = future_switch_data.pop(fut)

                    try:
                        swobject = fut.result()
                    except Exception as exc:
                        print('%r generated an exception: %s' %
                              (hostname, exc))
                        self.discovery_status[hostname] = "Failed"
                    else:
                        fqdn = swobject.facts['fqdn'].replace(".not set", "")
                        print("Done", fqdn)
                        self.discovery_status[hostname] = "Completed"
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
                                                assert "NX" not in nei['hostname']
                                                assert "axis" not in nei['hostname']
                                                assert "DATACENTER" not in nei['hostname']
                                            except AssertionError:
                                                continue

                                            self.discovery_status[nei['ip']
                                                                  ] = "Queued"
                                            print(
                                                "Queueing discover for " + nei['hostname'])
                                            future_switch_data[executor.submit(self.add_switch,
                                                                               nei['ip'],
                                                                               credentials,
                                                                               napalm_optional_args)] = nei['ip']

        self.refresh_global_information()

    def refresh_global_information(self):
        """
        Update global information such as mac address position
        and cdp neighbor adjacency
        """
        self._recalculate_macs()
        self._cdp_neigh_parse()

    def _cdp_neigh_parse(self):
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
                                intfdata.neighbors[i] = peer_device
                            except KeyError:
                                pass

    def _recalculate_macs(self):
        for swname, swdata in self.switches.items():
            for mac, macdata in swdata.mac_table.items():
                try:
                    if self.mac_table[mac]['interface'].mac_count > macdata['interface'].mac_count:
                        self.mac_table[mac] = macdata
                except KeyError:
                    self.mac_table[mac] = macdata


class Switch():
    """
    Switch object to hold data
    Initialize with name and hostname, call retrieve_data
    to connect to device and retrieve automaticlly or 
    pass config as string to parse locally
    """

    INTERFACE_TYPES = r"([Pp]ort-channel|\w*Ethernet)."
    INTERFACE_FILTER = r"^interface " + INTERFACE_TYPES

    def __init__(self,
                 hostname: str,
                 **kwargs):

        self.hostname = hostname
        self.interfaces = {}
        self.config = kwargs.get('config', None)
        self.timeout = 30
        self.napalm_optional_args = kwargs.get('napalm_optional_args', None)
        self.init_time = dt.datetime.now()
        self.mac_table = {}

        if self.config is not None:
            self._parse_config()

    def retrieve_data(self,
                      username: str,
                      password: str,
                      napalm_optional_args: dict = {}):

        self.napalm_optional_args = napalm_optional_args

        self.connect(username, password, napalm_optional_args)

        self._get_switch_data()

    def connect(self, username: str, password: str, napalm_optional_args: dict = None) -> None:
        driver = napalm.get_network_driver('ios')

        if napalm_optional_args is not None:
            self.napalm_optional_args = napalm_optional_args

        self.session = driver(self.hostname,
                              username=username,
                              password=password,
                              timeout=self.timeout,
                              optional_args=self.napalm_optional_args)

        # TODO: Use logging not print
        print("Connecting to ", self.hostname)
        self.session.open()

    def get_active_vlans(self):
        vlans = set([1])
        for _, intdata in self.interfaces.items():
            vlans.add(intdata.native_vlan)
            try:
                if len(intdata.allowed_vlan) != 4094:
                    vlans = vlans.union(intdata.allowed_vlan)

            except AttributeError:
                continue

        # Find trunk interfaces with no neighbors
        noneightrunks = []
        for intname, intdata in self.interfaces.items():
            if intdata.mode == "trunk":
                try:
                    assert not isinstance(intdata.neighbors[0], Interface)
                except (KeyError, AssertionError, AttributeError):
                    # Interface has explicit neighbor, exclude
                    continue

                noneightrunks.append(intdata)

                # Find if interface has mac addresses
                activevlans = set()
                for mac, macdata in self.mac_table.items():
                    if macdata['interface'] == intdata:
                        activevlans.add(macdata['vlan'])

                vlans = vlans.union(activevlans)

        return vlans

    def _parse_config(self):
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
            self.interfaces[thisint.name] = thisint
        #self.interfaces = {x.name: x for x in self.interfaces}

    def _get_switch_data(self):
        self.facts = self.session.get_facts()

        self.session.device.write_channel("show run")
        self.session.device.write_channel("\n")
        self.session.device.timeout = 30  # Could take ages...
        self.config = self.session.device.read_until_pattern(
            "end\r\n", max_loops=3000)
        #print("Parsing config")

        self._parse_config()

        # Get mac address table
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

        # Get interface status
        int_status = self.session.get_interfaces()

        for intname, intstatus in int_status.items():
            try:
                self.interfaces[intname].is_enabled = intstatus['is_enabled']
                self.interfaces[intname].is_up = intstatus['is_up']
                self.interfaces[intname].speed = intstatus['speed']
                self.interfaces[intname].switch = self
            except KeyError:
                continue

        # Add last in/out status
        self._parse_int_last_inout()

        self._parse_cdp_neighbors()

        # Get VTP status
        command = "show vtp status"
        result = self.session.cli([command])

        self.vtp = result[command]

        self.session.close()

    def _parse_int_last_inout(self):
        interface_types = r"([Pp]ort-channel|\w*Ethernet)."
        commandout = self.session.cli(['show interfaces'])['show interfaces']

        parsed_command = ciscoconfparse.CiscoConfParse(
            config=commandout.splitlines())

        interfaces = parsed_command.find_objects_w_child(
            interface_types, "Last")

        for eth in interfaces:
            name = eth.text.split()[0]
            for line in eth.re_search_children("Last input"):
                try:
                    last_in = line.re_match(
                        r"Last input (.*), output .*, output hang")
                    last_out = line.re_match(
                        r"Last input .*, output (.*), output hang")

                    last_in = self._cisco_time_to_dt(last_in)
                    last_out = self._cisco_time_to_dt(last_out)

                    self.interfaces[name].last_in = last_in
                    self.interfaces[name].last_out = last_out
                except KeyError:
                    print(name)

    def _parse_cdp_neighbors(self):
        # Return parsed cdp neighbours
        # [[empty, hostname, ip, platform, local interface, remote interface, version]]
        # [['', 'SMba03_1_Piking', '10.19.6.15', 'cisco WS-C3560G-48TS', 'GigabitEthernet0/49', 'GigabitEthernet0/2', 'Cisco IOS Software, C3560 Software (C3560-IPBASE-M), Version 12.2(35)SE5, RELEASE SOFTWARE (fc1)']]
        self.session.device.write_channel("show cdp neigh detail")
        self.session.device.write_channel("\n")
        self.session.device.timeout = 30  # Could take ages...
        neighdetail = self.session.device.read_until_prompt(max_loops=3000)
        re_table = textfsm.TextFSM(
            open("textfsm_templates/show_cdp_neigh_detail.textfsm"))
        fsm_results = re_table.ParseText(neighdetail)

        for nei in fsm_results:
            if not hasattr(self.interfaces[nei[5]], "neighbors"):
                self.interfaces[nei[5]].neighbors = []

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
            return None

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

class Interface():
    """
    Define an interface
    Can be initialised with any of the values or by passing
    an array containing each line of the interface configuration
    """

    def __init__(self, **kwargs):
        self.name: str = kwargs.get('name', None)
        self.description: Optional[str] = kwargs.get('description', None)
        self.mode: str = kwargs.get('mode', 'access')
        self.channel_group: Optional[int] = kwargs.get('channel_group', None)
        self.channel_protocol: Optional[str] = kwargs.get(
            'channel_protocol', None)
        self.allowed_vlan: set = kwargs.get('allowed_vlan', set())
        self.native_vlan: int = kwargs.get('native_vlan', 1)
        self.voice_vlan: Optional[int] = kwargs.get('voice_vlan', None)
        self.switch = kwargs.get('switch', None)
        self.parent_interface = kwargs.get('parent_interface', None)
        self.is_up: bool = kwargs.get('is_up', True)
        self.is_enabled: bool = kwargs.get('is_enabled', True)
        self.config: List[str] = kwargs.get('config', None)
        self.mac_count = 0
        self.type_edge = kwargs.get('type_edge', False)
        self.bpduguard = kwargs.get('bpduguard', False)

        if self.config is not None:
            self.parse_config()

    def parse_config(self):
        if isinstance(self.config, str):
            self.config = self.config.split("\n")

        for line in self.config:
            cleanline = line.strip()
            # Find interface name
            match = re.search(r"^interface ([A-Za-z\-]*(\/*\d*)+)", cleanline)
            if match is not None:
                self.name = match.groups()[0]

            # Find description
            match = re.search(r"description (.*)$", cleanline)
            if match is not None:
                self.description = match.groups()[0]

            # Find port-channel properties
            match = re.search(r"channel-group (\d*) mode (\w*)", cleanline)
            if match is not None:
                self.channel_group = match.groups()[0]
                self.channel_protocol = match.groups()[1]

            # Port mode
            match = re.search(r"switchport mode (.*)$", cleanline)
            if match is not None:
                self.mode = match.groups()[0].strip()
                if self.mode == 'trunk' and len(self.allowed_vlan) == 0:
                    self.allowed_vlan = set([x for x in range(1, 4095)])

            # Native vlan
            match = re.search(r"switchport access vlan (.*)$", cleanline)
            if match is not None and self.mode == 'access':
                self.native_vlan = int(match.groups()[0])

            # Trunk native vlan
            match = re.search(r"switchport trunk native vlan (.*)$", cleanline)
            if match is not None and self.mode == 'trunk':
                self.native_vlan = int(match.groups()[0])

            # Trunk allowed vlan
            match = re.search(
                r"switchport trunk allowed vlan ([0-9\-\,]*)$", cleanline)
            if match is not None:
                self.allowed_vlan = self._allowed_vlan_to_list(
                    match.groups()[0])

            # Trunk allowed vlan add
            match = re.search(
                r"switchport trunk allowed vlan add ([0-9\-\,]*)$", cleanline)
            if match is not None:
                new_vlans = self._allowed_vlan_to_list(match.groups()[0])
                self.allowed_vlan.update(list(new_vlans))

            # Portfast
            match = re.search(
                r"spanning-tree portfast", cleanline)
            if match is not None:
                self.type_edge = True

            match = re.search(
                r"spanning-tree bpduguard", cleanline)
            if match is not None:
                self.bpduguard = True

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

        fullconfig = fullconfig + f" switchport mode {self.mode}\n"

        if self.mode == "access":
            fullconfig = fullconfig + f" switchport access vlan {self.native_vlan}\n"

        elif self.mode== "trunk":
            fullconfig = fullconfig + f" switchport trunk native vlan {self.native_vlan}\n"
            if len(self.allowed_vlan) != 4094:
                vlan_str = ",".join(map(str, self.allowed_vlan))
                fullconfig = fullconfig + f" switchport trunk allowed vlan {vlan_str}\n"
            else:
                fullconfig = fullconfig + " switchport trunk allowed vlan all\n"
        else:
            raise KeyError("Unknown interface mode")


        if self.mode == "access" and self.voice_vlan is not None:
            fullconfig = fullconfig + f" switchport voice vlan {self.voice_vlan}\n"

        if self.type_edge:
            fullconfig = fullconfig + " spanning-tree portfast"

            if self.mode == "trunk":
                fullconfig = fullconfig + " trunk\n"
            else:
                fullconfig = fullconfig + "\n"

        if self.is_enabled:
            fullconfig = fullconfig + " no shutdown\n"
        else:
            fullconfig = fullconfig + " shutdown\n"

        fullconfig = fullconfig + "!\n"
        return fullconfig
