"Define Switch object"

import logging
import os
from io import StringIO
import datetime as dt
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
        self.hostname = hostname
        self.interfaces = {}
        self.config = kwargs.get('config', None)
        self.timeout = 30
        self.napalm_optional_args = kwargs.get('napalm_optional_args', None)
        self.init_time = dt.datetime.now()
        self.mac_table = {}
        self.vtp = None
        self.arp_table = {}
        self.interfaces_ip = {}
        self.vlans = None
        self.vlans_set = {x for x in range(1,4095)} # VLANs configured on the switch
        self.facts = kwargs.get('facts', None)

        if self.config is not None:
            self._parse_config()

    def retrieve_data(self,
                      username: str,
                      password: str,
                      napalm_optional_args: dict = {}):

        self.napalm_optional_args = napalm_optional_args

        self.connect(username, password, napalm_optional_args)

        self._get_switch_data()
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

        # Remove vlans not explicitly configured
        vlans.intersection_update(self.vlans_set)
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

    def _get_switch_data(self):
        self.facts = self.session.get_facts()

        self.init_time = dt.datetime.now()

        self.session.device.write_channel("show run")
        self.session.device.write_channel("\n")
        self.session.device.timeout = 30  # Could take ages...
        self.config = self.session.device.read_until_pattern(
            "end\r\n", max_loops=3000)
        #print("Parsing config")

        self._parse_config()

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

        int_counters = self.session.get_interfaces_counters()
        for intname, intstatus in int_counters.items():
            try:
                self.interfaces[intname].counters = intstatus
            except KeyError:
                continue

        # Add last in/out status
        self._parse_int_last_inout()

        self._parse_cdp_neighbors()

        # Get VTP status
        command = "show vtp status"
        result = self.session.cli([command])

        self.vtp = result[command]

        # Get VLANs
        self.vlans = self.session.get_vlans()
        self.vlans_set = set([int(k) for k, v in self.vlans.items()])

        # Get l3 interfaces
        self.interfaces_ip = self.session.get_interfaces_ip()
        self.arp_table = self.session.get_arp_table()

    def _parse_int_last_inout(self):
        "Get last in and last out as well as last coutner clearing"
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
                    pass

            for line in eth.re_search_children("Last clearing of"):
                try:
                    last_clearing = line.re_match(r"counters (.*)")

                    last_clearing = self._cisco_time_to_dt(last_clearing)
                    self.interfaces[name].last_clearing = last_clearing
                except KeyError:
                    pass

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
