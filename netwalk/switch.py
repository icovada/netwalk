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

"""Define Switch object"""




import ipaddress
import logging
import os
from io import StringIO
import datetime as dt
from typing import Dict, Optional, List, Union
from netaddr import EUI
import napalm
import ciscoconfparse
import textfsm
import datetime
from netwalk.interface import Interface
from netwalk.libs import interface_name_expander

class Device():
    hostname: str
    #: Dict of {name: Interface}
    interfaces: Dict[str, 'Interface']
    discovery_status: Optional[Union[str, datetime.datetime]]
    fabric: 'Fabric'
    mgmt_address: Union[ipaddress.ip_address, str]
    facts: dict

    def __init__(self, mgmt_address, **kwargs) -> None:
        if isinstance(mgmt_address, str):
            self.mgmt_address = ipaddress.ip_address(mgmt_address)
        else:
            self.mgmt_address = mgmt_address

        self.hostname: str = kwargs.get('hostname', mgmt_address)
        self.interfaces: Dict[str, 'Interface'] = kwargs.get('interfaces', {})
        self.discovery_status = kwargs.get('discovery_status', None)
        self.fabric: 'Fabric' = kwargs.get('fabric', None)
        self.facts: dict = kwargs.get('facts', None)
        if self.hostname is None:
            self.logger = logging.getLogger(__name__ + str(self.mgmt_address))
        else:
            self.logger = logging.getLogger(__name__ + self.hostname)

        if self.fabric is not None:
            if self.hostname is None:
                self.fabric.switches[str(self.mgmt_address)] = self
            else:
                self.fabric.switches[self.hostname] = self

    def add_interface(self, intobject: Interface):
        """Add interface to device

        :param intobject: Interface to add
        :type intobject: netwalk.Interface
        """
        intobject.switch = self
        self.interfaces[intobject.name] = intobject

        if type(self) == Switch:
            for k, v in self.interfaces.items():
                v.parse_config(second_pass=True)

    def promote_to_switch(self):
        self.__class__ = Switch
        self.__init__(mgmt_address = self.mgmt_address,
                      hostname = self.hostname,
                      interfaces = self.interfaces,
                      discovery_status = self.discovery_status,
                      fabric = self.fabric,
                      facts = self.facts)


class Switch(Device):
    """
    Switch object to hold data
    Initialize with name and hostname, call retrieve_data()
    to connect to device and retrieve automaticlly or
    pass config as string to parse locally
    """

    INTERFACE_TYPES = r"([Pp]ort-channel|\w*Ethernet|Vlan|Loopback)."
    INTERFACE_FILTER = r"^interface " + INTERFACE_TYPES

    logger: logging.Logger
    hostname: str
    #: Dict of {name: Interface}
    interfaces: Dict[str, Interface]
    #: Pass at init time to parse config automatically
    config: Optional[str]
    napalm_optional_args: dict
    #: Time of object initialization. All timers will be calculated from it
    inventory: List[Dict[str, Dict[str, str]]]
    vtp: Optional[str]
    arp_table: Dict[ipaddress.IPv4Interface, dict]
    interfaces_ip: dict
    vlans: Optional[Dict[int, dict]]
    vlans_set: set
    local_admins: Optional[Dict[str, dict]]
    timeout: int
    mac_table: dict

    def __init__(self,
                 mgmt_address,
                 **kwargs):

        super().__init__(mgmt_address, **kwargs)
        self.config: Optional[str] = kwargs.get('config', None)
        self.napalm_optional_args = kwargs.get('napalm_optional_args', None)
        self.vtp: Optional[str] = None
        self.arp_table: Dict[ipaddress.IPv4Interface, dict] = {}
        self.interfaces_ip = {}
        self.vlans: Optional[Dict[int, dict]] = None
        # VLANs configured on the switch
        self.vlans_set = {x for x in range(1, 4095)}
        self.local_admins: Optional[Dict[str, dict]] = None
        self.timeout = 30
        self.mac_table = {}

        if self.config is not None:
            self._parse_config()

    def retrieve_data(self,
                      username: str,
                      password: str,
                      napalm_optional_args: dict = {},
                      scan_options: dict = {}):
        """
        One-stop function to get data from switch.

        :param username: username
        :type username: str
        :param password: password
        :type password: str
        :param napalm_optional_args: Refer to Napalm's documentation
        :type napalm_optional_args: dict
        :param scan_options: Valid keys are 'whitelist' and 'blacklist'. Value must be a list of options to pass to _get_switch_data
        :type scan_options: dict(str, list(str))
        """

        self.napalm_optional_args = napalm_optional_args

        self.connect(username, password, napalm_optional_args)
        try:
            self._get_switch_data(**scan_options)
        except Exception as e:
            self.session.close()
            raise e

        else:
            self.session.close()

    def connect(self, username: str, password: str, napalm_optional_args: dict = None) -> None:
        """Connect to device

        :param username: username
        :type username: str
        :param password: password
        :type password: str
        :param napalm_optional_args: Check Napalm's documentation about optional-args, defaults to None
        :type napalm_optional_args: dict, optional
        """
        driver = napalm.get_network_driver('ios')

        if napalm_optional_args is not None:
            self.napalm_optional_args = napalm_optional_args

        self.session = driver(str(self.mgmt_address),
                              username=username,
                              password=password,
                              timeout=self.timeout,
                              optional_args=self.napalm_optional_args)

        self.logger.info("Connecting to %s", self.mgmt_address)
        self.session.open()

    def get_active_vlans(self):
        """Get active vlans from switch.
        Only lists vlans configured on ports

        :return: [description]
        :rtype: [type]
        """
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

    def _parse_config(self):
        """Parse show run
        """
        if isinstance(self.config, str):
            running = StringIO()
            running.write(self.config)

            # Be kind rewind
            running.seek(0)

            # Get show run and interface access/trunk status
            self.parsed_conf = ciscoconfparse.CiscoConfParse(running)
            interface_config_list: list = self.parsed_conf.find_objects(
                self.INTERFACE_FILTER)

            for intf in interface_config_list:
                thisint = Interface(config=intf.ioscfg)
                localint = self.interfaces.get(thisint.name, None)
                if localint is not None:
                    localint.config = intf.ioscfg
                    localint.parse_config()
                else:
                    thisint.parse_config()
                    self.add_interface(thisint)

        else:
            TypeError("No interface loaded, cannot parse")

    def _get_switch_data(self,
                         whitelist: Optional[List[str]] = None,
                         blacklist: Optional[List[str]] = None):
        """
        Get data from switch.
        If no argument is passed, scan all modules

        :param whitelist: List of modules to scan, defaults to None
        :type whitelist: list(str)
        :param blacklist: List of modules to exclude from scan, defaults to None
        :type blacklist: list(str)

        Either whitelist or blacklist can be passed.
        If both are passed, whitelist takes precedence over blacklist.

        Valid values are:
        - 'mac_address'
        - 'interface_status'
        - 'cdp_neighbors'
        - 'lldp_neighbors'
        - 'vtp'
        - 'vlans'
        - 'l3_int'
        - 'local_admins'
        - 'inventory'

        Running config is ALWAYS returned
        """

        allscans = ['mac_address', 'interface_status',
                    'cdp_neighbors', 'lldp_neighbors', 'vtp', 'vlans', 'l3_int', 'local_admins', 'inventory']
        scan_to_perform = []

        if whitelist is not None:
            for i in whitelist:
                assert i in allscans, "Parameter not recognised in scan list. has to be any of ['mac_address', 'interface_status', 'cdp_neighbors', 'lldp_neighbors', 'vtp', 'vlans', 'l3_int', 'local_admins', 'inventory']"

            scan_to_perform = whitelist

        elif blacklist is not None:
            scan_to_perform = allscans
            for i in blacklist:
                assert i in allscans, "Parameter not recognised in scan list. has to be any of ['mac_address', 'interface_status', 'cdp_neighbors', 'lldp_neighbors', 'vtp', 'vlans', 'l3_int', 'local_admins', 'inventory']"
                scan_to_perform.remove(i)

        else:
            scan_to_perform = allscans

        self.facts = self.session.get_facts()

        try:
            self.hostname = self.facts['fqdn'].replace(".not set","") if self.facts['fqdn'] != 'Unknown' else self.facts['hostname']
        except KeyError:
            pass

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
            self.mac_table = {}  # Clear before adding new data
            mactable = self.session.get_mac_address_table()

            macdict = {EUI(x['mac']): x for x in mactable}

            for k, v in macdict.items():
                if v['interface'] == '':
                    continue

                v['interface'] = interface_name_expander(v['interface'])

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

        if 'lldp_neighbors' in scan_to_perform:
            self._parse_lldp_neighbors()

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

        if 'inventory' in scan_to_perform:
            # Get inventory
            self.inventory = self._parse_inventory()

    def _parse_inventory(self):
        command = "show inventory"
        showinventory = self.session.cli([command])[command]

        fsmpath = os.path.dirname(os.path.realpath(
            __file__)) + "/textfsm_templates/show_inventory.textfsm"
        with open(fsmpath, 'r') as fsmfile:
            try:
                re_table = textfsm.TextFSM(fsmfile)
                fsm_results = re_table.ParseTextToDicts(showinventory)
            except Exception as e:
                self.logger.error("Textfsm parsing error %s", e)
                return {}

        result = {}
        for i in fsm_results:
            result[i['name']] = {'descr': i['descr'],
                                 'pid': i['pid'],
                                 'vid': i['vid'],
                                 'sn': i['sn'],
                                 }

        return result

    def _parse_show_interface(self):
        """Parse output of show inteface with greater data collection than napalm"""
        self.session.device.write_channel("show interface")
        self.session.device.write_channel("\n")
        self.session.device.timeout = 30  # Could take ages...
        showint = self.session.device.read_until_prompt(max_loops=3000)
        fsmpath = os.path.dirname(os.path.realpath(
            __file__)) + "/textfsm_templates/show_interface.textfsm"
        with open(fsmpath, 'r') as fsmfile:
            try:
                re_table = textfsm.TextFSM(fsmfile)
                fsm_results = re_table.ParseTextToDicts(showint)
            except Exception as e:
                self.logger.error("Show interface parsing failed %s", e)
                return None


        for intf in fsm_results:
            if intf['name'] in self.interfaces:
                for k, v in intf.items():
                    if k in ('last_in', 'last_out', 'last_out_hang', 'last_clearing'):
                        setattr(self.interfaces[intf['name']],
                                k, self._cisco_time_to_dt(v))
                    elif k == 'is_enabled':
                        val = True if 'up' in v else False
                        setattr(self.interfaces[intf['name']], k, val)
                    elif k == 'is_up':
                        val = True if 'up' in v else False
                        setattr(self.interfaces[intf['name']], k, val)
                        setattr(
                            self.interfaces[intf['name']], 'protocol_status', v)
                    else:
                        setattr(self.interfaces[intf['name']], k, v)
            else:
                # Sometimes multi-type interfaces appear in one command and not in another
                self.interfaces[intf['name']] = Interface(name=intf['name'])

    def _parse_cdp_neighbors(self):
        """Ask for and parse CDP neighbors"""
        self.session.device.write_channel("show cdp neigh detail")
        self.session.device.write_channel("\n")
        self.session.device.timeout = 30  # Could take ages...
        neighdetail = self.session.device.read_until_prompt(max_loops=3000)
        fsmpath = os.path.dirname(os.path.realpath(
            __file__)) + "/textfsm_templates/show_cdp_neigh_detail.textfsm"
        with open(fsmpath, 'r') as fsmfile:
            try:
                re_table = textfsm.TextFSM(fsmfile)
                fsm_results = re_table.ParseTextToDicts(neighdetail)
            except Exception as e:
                self.logger.error("Show cdp neighbor parsing failed %s", e)
                return None

        for result in fsm_results:
            self.logger.debug("Found CDP neighbor %s IP %s local int %s, remote int %s",
                              result['dest_host'], result['mgmt_ip'], result['local_port'], result['remote_port'])

        for nei in fsm_results:
            neigh_data = {'hostname': nei['dest_host'],
                          'ip': nei['mgmt_ip'],
                          'platform': nei['platform'],
                          'remote_int': nei['remote_port']
                          }

            self.interfaces[nei['local_port']].neighbors.append(neigh_data)

    def _parse_lldp_neighbors(self):
        """Ask for and parse LLDP neighbors"""
        self.session.device.write_channel("show lldp neigh detail")
        self.session.device.write_channel("\n")
        self.session.device.timeout = 30  # Could take ages...
        neighdetail = self.session.device.read_until_prompt(max_loops=3000)

        fsmpath = os.path.dirname(os.path.realpath(
            __file__)) + "/textfsm_templates/show_lldp_neigh_detail.textfsm"
        with open(fsmpath, 'r') as fsmfile:
            try:
                re_table = textfsm.TextFSM(fsmfile)
                fsm_results = re_table.ParseTextToDicts(neighdetail)
            except Exception as e:
                self.logger.error("Show lldp neighbor parsing failed %s", e)
                return None

        for result in fsm_results:
            self.logger.debug("Found LLDP neighbor %s IP %s local int %s, remote int %s",
                              result['neighbor'], result['mgmt_ip'], result['local_port'], result['remote_port'])

        for nei in fsm_results:
            neigh_data = {'hostname': nei['neighbor'],
                          'ip': nei['mgmt_ip'],
                          'platform': nei['system_description'],
                          'remote_int': nei['remote_port']
                          }

            self.interfaces[nei['local_port']].neighbors.append(neigh_data)

    def _cisco_time_to_dt(self, time: str) -> dt.datetime:
        """Converts time from now to absolute, starting when Switch object was initialised

        :param time: Cisco diff time (e.g. '00:00:01' or '5w4d')
        :param type: str

        :return: Absolute time
        :rtype: datetime.datetime
        """
        weeks = 0
        days = 0
        hours = 0
        minutes = 0
        seconds = 0

        if time == 'never' or time == '':
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
        """Return switch config from hostname and interfaces

        :return: Switch "show run" from internal data
        :rtype: str"""
        showrun = f"! {self.hostname}"

        try:
            showrun = showrun + f" {self.facts['hostname']}\n"
        except (AttributeError, KeyError):
            showrun = showrun + "\n"

        showrun = showrun + "!\n"

        for intname, intdata in self.interfaces.items():
            showrun = showrun + str(intdata)

        return showrun
