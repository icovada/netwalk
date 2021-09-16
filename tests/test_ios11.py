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
import netwalk


class OldConfigTester(unittest.TestCase):
    """
    Test configs on IOS 11 (yes I am working on some stuff _that_ old)
    """
    def test_old_switchport(self):
        config = ("interface FastEthernet0/1\n"
                  " no ip address\n"
                  " description Antani\n"
                  " switchport trunk native vlan 4\n"
                  " switchport trunk allowed vlan 5-10\n"
                  " switchport mode trunk")

        interface = netwalk.Interface(config=config)

        assert interface.address == {}
        assert interface.mode == 'trunk'
        assert interface.native_vlan == 4
        assert interface.allowed_vlan == {5, 6, 7, 8, 9, 10}
        assert interface.description == 'Antani'
        assert not interface.routed_port

if __name__ == '__main__':
    unittest.main()
