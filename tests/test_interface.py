import unittest
import netwalk


class InterfaceTester(unittest.TestCase):
    def unparsed_lines(self):
        config = """
            interface E0
              switchport mode access
              antani mascetti perozzi"""

        interface = netwalk.Interface(config=config)

        assert interface.unparsed_lines == ["antani mascetti perozzi", ]


class AccessInterfaceTester(unittest.TestCase):

    def test_empty_config(self):
        config = """
            interface GigabitEthernet1/0/1
            """
        interface = netwalk.Interface(config=config)

        assert interface.name == "GigabitEthernet1/0/1"

    def test_mode(self):
        config = """
            interface E0
              switchport mode access"""

        interface = netwalk.Interface(config=config)
        assert interface.name == "E0"
        assert interface.mode == "access"
        assert interface.native_vlan == 1

    def test_interface_w_vlan(self):
        config = """
            interface E0
              switchport mode access
              switchport access vlan 3"""

        interface = netwalk.Interface(config=config)
        assert interface.name == "E0"
        assert interface.mode == "access"
        assert interface.native_vlan == 3

    def test_interface_w_trunk_native(self):
        config = """
            interface E0
              switchport mode access
              switchport trunk native vlan 3"""

        interface = netwalk.Interface(config=config)
        assert interface.name == "E0"
        assert interface.mode == "access"
        assert interface.native_vlan == 1

    def test_interface_portfast(self):
        config = """
            interface E0
              switchport mode access
              spanning-tree portfast"""

        interface = netwalk.Interface(config=config)
        assert interface.name == "E0"
        assert interface.mode == "access"
        assert interface.type_edge

    def test_interface_portfast_trunk(self):
        config = """
            interface E0
              switchport mode access
              spanning-tree portfast trunk"""

        interface = netwalk.Interface(config=config)
        assert interface.name == "E0"
        assert interface.mode == "access"
        assert not interface.type_edge


class TrunkInterfaceTester(unittest.TestCase):

    def test_mode(self):
        config = """
            interface E0
              switchport mode trunk"""

        interface = netwalk.Interface(config=config)
        assert interface.name == "E0"
        assert interface.mode == "trunk"
        assert interface.native_vlan == 1
        assert interface.allowed_vlan == {x for x in range(1, 4095)}

    def test_interface_w_native_vlan(self):
        config = """
            interface E0
              switchport mode trunk
              switchport trunk native vlan 3"""

        interface = netwalk.Interface(config=config)
        assert interface.name == "E0"
        assert interface.mode == "trunk"
        assert interface.native_vlan == 3
        assert interface.allowed_vlan == {x for x in range(1, 4095)}

    def test_interface_w_allowed_vlan(self):
        config = """
            interface E0
              switchport mode trunk
              switchport trunk allowed vlan 1,2,3,5,10-12,67,90-95"""

        interface = netwalk.Interface(config=config)
        assert interface.name == "E0"
        assert interface.mode == "trunk"
        assert interface.native_vlan == 1
        assert interface.allowed_vlan == set(
            [1, 2, 3, 5, 10, 11, 12, 67, 90, 91, 92, 93, 94, 95])


if __name__ == '__main__':
    unittest.main()
