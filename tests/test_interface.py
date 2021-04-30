import unittest
import netwalk


class BaseInterfaceTester(unittest.TestCase):
    def test_empty_config(self):
        config = ("interface GigabitEthernet1/0/1\n")

        interface = netwalk.Interface(config=config)

        assert interface.name == "GigabitEthernet1/0/1"
        assert interface.mode == "access"
        assert interface.native_vlan == 1
        assert interface.voice_vlan is None
        assert interface.description is None
        assert not interface.bpduguard
        assert not interface.type_edge
        assert interface.is_enabled

    def test_shutdown(self):
        config = ("interface E0\n"
                  " shutdown")

        interface = netwalk.Interface(config=config)
        assert not interface.is_enabled

    def test_unparsed_lines(self):
        config = ("interface E0\n"
                  " switchport mode access\n"
                  " antani mascetti perozzi")

        interface = netwalk.Interface(config=config)

        assert interface.unparsed_lines == ["antani mascetti perozzi", ]

    def test_description(self):
        config = ("interface E0\n"
                  " description Antani\n")

        interface = netwalk.Interface(config=config)
        assert interface.description == "Antani"

    def test_bpduguard(self):
        config = ("interface E0\n"
                  " spanning-tree bpduguard enable\n")

        interface = netwalk.Interface(config=config)
        assert interface.bpduguard


class AccessInterfaceTester(unittest.TestCase):
    def test_mode(self):
        config = ("interface E0\n"
                  " switchport mode access\n")

        interface = netwalk.Interface(config=config)
        assert interface.name == "E0"
        assert interface.mode == "access"
        assert interface.native_vlan == 1

    def test_interface_w_vlan(self):
        config = ("interface E0\n"
                  " switchport mode access\n"
                  " switchport access vlan 3\n")

        interface = netwalk.Interface(config=config)
        assert interface.name == "E0"
        assert interface.mode == "access"
        assert interface.native_vlan == 3

    def test_interface_w_trunk_native(self):
        config = ("interface E0\n"
                  " switchport mode access\n"
                  " switchport trunk native vlan 3\n")

        interface = netwalk.Interface(config=config)
        assert interface.name == "E0"
        assert interface.mode == "access"
        assert interface.native_vlan == 1

    def test_interface_portfast(self):
        config = ("interface E0\n"
                  " switchport mode access\n"
                  " spanning-tree portfast\n")

        interface = netwalk.Interface(config=config)
        assert interface.name == "E0"
        assert interface.mode == "access"
        assert interface.type_edge

    def test_interface_portfast_trunk(self):
        config = ("interface E0\n"
                  " switchport mode access\n"
                  " spanning-tree portfast trunk\n")

        interface = netwalk.Interface(config=config)
        assert interface.name == "E0"
        assert interface.mode == "access"
        assert not interface.type_edge

    def test_voice_vlan(self):
        config = ("interface E0\n"
                  " switchport mode access\n"
                  " switchport voice vlan 150\n")

        interface = netwalk.Interface(config=config)
        assert interface.name == "E0"
        assert interface.mode == "access"
        assert interface.native_vlan == 1
        assert interface.voice_vlan == 150


class TrunkInterfaceTester(unittest.TestCase):
    def test_mode(self):
        config = ("interface E0\n"
                  " switchport mode trunk\n")

        interface = netwalk.Interface(config=config)
        assert interface.name == "E0"
        assert interface.mode == "trunk"
        assert interface.native_vlan == 1
        assert interface.allowed_vlan == {x for x in range(1, 4095)}

    def test_interface_w_native_vlan(self):
        config = ("interface E0\n"
                  " switchport mode trunk\n"
                  " switchport trunk native vlan 3\n")

        interface = netwalk.Interface(config=config)
        assert interface.name == "E0"
        assert interface.mode == "trunk"
        assert interface.native_vlan == 3
        assert interface.allowed_vlan == {x for x in range(1, 4095)}

    def test_interface_w_allowed_vlan(self):
        config = ("interface E0\n"
                  " switchport mode trunk\n"
                  " switchport trunk allowed vlan 1,2,3,5,10-12,67,90-95")

        interface = netwalk.Interface(config=config)
        assert interface.name == "E0"
        assert interface.mode == "trunk"
        assert interface.native_vlan == 1
        assert interface.allowed_vlan == set(
            [1, 2, 3, 5, 10, 11, 12, 67, 90, 91, 92, 93, 94, 95])

    def test_interface_w_multiline_allowed_vlan(self):
        config = ("interface E0\n"
                  " switchport mode trunk\n"
                  " switchport trunk allowed vlan 1,2,3-5\n"
                  " switchport trunk allowed vlan add 7,8-10")

        interface = netwalk.Interface(config=config)
        assert interface.name == "E0"
        assert interface.mode == "trunk"
        assert interface.native_vlan == 1
        assert interface.allowed_vlan == set(
            [1, 2, 3, 4, 5, 7, 8, 9, 10])


class TestInterfaceOutString(unittest.TestCase):
    def test_base(self):
        intdata = {'name': 'E0'}
        interface = netwalk.Interface(**intdata)

        outconfig = ('interface E0\n'
                     ' switchport mode access\n'
                     ' switchport access vlan 1\n'
                     ' no shutdown\n'
                     '!\n')

        assert str(interface) == outconfig

    def test_mode_access(self):
        intdata = {'name': 'E0',
                   'mode': 'access'}
        interface = netwalk.Interface(**intdata)

        outconfig = ('interface E0\n'
                     ' switchport mode access\n'
                     ' switchport access vlan 1\n'
                     ' no shutdown\n'
                     '!\n')

        assert str(interface) == outconfig

    def test_mode_access_native_vlan(self):
        intdata = {'name': 'E0',
                   'mode': 'access',
                   'native_vlan': 3}
        interface = netwalk.Interface(**intdata)

        outconfig = ('interface E0\n'
                     ' switchport mode access\n'
                     ' switchport access vlan 3\n'
                     ' no shutdown\n'
                     '!\n')

        assert str(interface) == outconfig

    def test_trunk(self):
        intdata = {'name': 'E0',
                   'mode': 'trunk'}
        interface = netwalk.Interface(**intdata)

        outconfig = ('interface E0\n'
                     ' switchport mode trunk\n'
                     ' switchport trunk native vlan 1\n'
                     ' switchport trunk allowed vlan all\n'
                     ' no shutdown\n'
                     '!\n')

        assert str(interface) == outconfig

    def test_trunk_native(self):
        intdata = {'name': 'E0',
                   'mode': 'trunk',
                   'native_vlan': 3}
        interface = netwalk.Interface(**intdata)

        outconfig = ('interface E0\n'
                     ' switchport mode trunk\n'
                     ' switchport trunk native vlan 3\n'
                     ' switchport trunk allowed vlan all\n'
                     ' no shutdown\n'
                     '!\n')

        assert str(interface) == outconfig

    def test_trunk_allowed_vlan(self):
        intdata = {'name': 'E0',
                   'mode': 'trunk',
                   'allowed_vlan': set([1, 2, 3])}
        interface = netwalk.Interface(**intdata)

        outconfig = ('interface E0\n'
                     ' switchport mode trunk\n'
                     ' switchport trunk native vlan 1\n'
                     ' switchport trunk allowed vlan 1,2,3\n'
                     ' no shutdown\n'
                     '!\n')

        assert str(interface) == outconfig

    def test_bpduguard(self):
        intdata = {'name': 'E0',
                   'bpduguard': True}
        interface = netwalk.Interface(**intdata)

        outconfig = ('interface E0\n'
                     ' switchport mode access\n'
                     ' switchport access vlan 1\n'
                     ' spanning-tree bpduguard enable\n'
                     ' no shutdown\n'
                     '!\n')

        assert str(interface) == outconfig

    def test_type_edge_access(self):
        intdata = {'name': 'E0',
                   'type_edge': True}
        interface = netwalk.Interface(**intdata)

        outconfig = ('interface E0\n'
                     ' switchport mode access\n'
                     ' switchport access vlan 1\n'
                     ' spanning-tree portfast\n'
                     ' no shutdown\n'
                     '!\n')

        assert str(interface) == outconfig

    def test_type_edge_trunk(self):
        intdata = {'name': 'E0',
                   'mode': 'trunk',
                   'type_edge': True}
        interface = netwalk.Interface(**intdata)

        outconfig = ('interface E0\n'
                     ' switchport mode trunk\n'
                     ' switchport trunk native vlan 1\n'
                     ' switchport trunk allowed vlan all\n'
                     ' spanning-tree portfast trunk\n'
                     ' no shutdown\n'
                     '!\n')

        assert str(interface) == outconfig


if __name__ == '__main__':
    unittest.main()
