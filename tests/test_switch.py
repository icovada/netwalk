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

if __name__ == '__main__':
    unittest.main()