import unittest
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
        sw = Switch("testsw", config = config)

        assert sw.hostname == "testsw"
        assert len(sw.interfaces) == 2
        assert "GigabitEthernet0/1" in sw.interfaces
        assert "GigabitEthernet0/2" in sw.interfaces
        assert isinstance(sw.interfaces['GigabitEthernet0/1'], Interface)

    def test_get_active_vlans(self):
        gi00 = Interface(name="GigabitEthernet0/0",
                         mode="trunk",
                         native_vlan=999,
                         allowed_vlan=set([2,3,4,5]))
        gi01 = Interface(name="GigabitEthernet0/1",
                         mode="access",
                         native_vlan=111)
        sw = Switch("sw1")
        sw.interfaces = {gi00.name: gi00,
                         gi01.name: gi01}

        vlans = sw.get_active_vlans()
        assert vlans == {1,2,3,4,5,999,111}

if __name__ == '__main__':
    unittest.main()