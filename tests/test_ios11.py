import unittest
import ipaddress
import netwalk


class OldConfigTester(unittest.TestCase):
    """
    Test configs on IOS 11 (yes I am working on some stuff _that_ old)
    """
    def test_old_switchport(self):
        config = ["interface FastEthernet0/1\n",
                  " no ip address\n",
                  " description Antani\n",
                  " switchport trunk native vlan 4\n",
                  " switchport trunk allowed vlan 5-10\n",
                  " switchport mode trunk"]

        interface = netwalk.Interface(config=config)

        assert interface.address == {}
        assert interface.mode == 'trunk'
        assert interface.native_vlan == 4
        assert interface.allowed_vlan == {5, 6, 7, 8, 9, 10}
        assert interface.description == 'Antani'
        assert not interface.routed_port

if __name__ == '__main__':
    unittest.main()
