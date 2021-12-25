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

import unittest
import ipaddress
from netwalk import Switch
from netwalk import Interface


class TestSwitchBasic(unittest.TestCase):
    def test_base_switch(self):
        config = ("interface GigabitEthernet0/1\n"
                  " switchport mode access\n"
                  "!\n"
                  "interface GigabitEthernet0/2\n"
                  " switchport mode access\n"
                  "!\n")
        sw = Switch("192.168.1.1", config=config)

        assert sw.mgmt_address == ipaddress.ip_address("192.168.1.1")
        assert len(sw.interfaces) == 2
        assert "GigabitEthernet0/1" in sw.interfaces
        assert "GigabitEthernet0/2" in sw.interfaces
        assert isinstance(sw.interfaces['GigabitEthernet0/1'], Interface)

    def test_get_active_vlans(self):
        gi00 = Interface(name="GigabitEthernet0/0",
                         mode="trunk",
                         native_vlan=999,
                         allowed_vlan=set([2, 3, 4, 5]))
        gi01 = Interface(name="GigabitEthernet0/1",
                         mode="access",
                         native_vlan=111)
        sw = Switch("1.1.1.1")
        sw.interfaces = {gi00.name: gi00,
                         gi01.name: gi01}

        vlans = sw.get_active_vlans()
        assert vlans == {1, 2, 3, 4, 5, 999, 111}


if __name__ == '__main__':
    unittest.main()
