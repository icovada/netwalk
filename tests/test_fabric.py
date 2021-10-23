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
from netwalk import Fabric, Switch, Interface


class TestFabricBase(unittest.TestCase):
    def test_cdp_neighborship(self):
        """
        A --- B
        |     |
        C --- D
        """

        f = Fabric()
        a = Switch(hostname="A", facts={'hostname': 'A', 'fqdn': 'A.not set'})
        b = Switch(hostname="B", facts={'hostname': 'B', 'fqdn': 'B.not set'})
        c = Switch(hostname="C", facts={'hostname': 'C', 'fqdn': 'C.not set'})
        d = Switch(hostname="D", facts={'hostname': 'D', 'fqdn': 'D.not set'})

        f.switches = {'A': a,
                      'B': b,
                      'C': c,
                      'D': d}

        a.interfaces = {'GigabitEthernet0/0': Interface(name='GigabitEthernet0/0',
                                                        neighbors=[{'hostname': 'B',
                                                                    'remote_int': 'GigabitEthernet0/0'}],
                                                        switch=b),
                        'GigabitEthernet0/1': Interface(name='GigabitEthernet0/1',
                                                        neighbors=[{'hostname': 'C',
                                                                    'remote_int': 'GigabitEthernet0/1'}],
                                                        switch=c)}

        b.interfaces = {'GigabitEthernet0/0': Interface(name='GigabitEthernet0/0',
                                                        neighbors=[{'hostname': 'A',
                                                                    'remote_int': 'GigabitEthernet0/0'}],
                                                        switch=a),
                        'GigabitEthernet0/1': Interface(name='GigabitEthernet0/1',
                                                        neighbors=[{'hostname': 'D',
                                                                    'remote_int': 'GigabitEthernet0/1'}],
                                                        switch=d)}

        c.interfaces = {'GigabitEthernet0/0': Interface(name='GigabitEthernet0/0',
                                                        neighbors=[{'hostname': 'D',
                                                                    'remote_int': 'GigabitEthernet0/0'}],
                                                        switch=d),
                        'GigabitEthernet0/1': Interface(name='GigabitEthernet0/1',
                                                        neighbors=[{'hostname': 'A',
                                                                    'remote_int': 'GigabitEthernet0/1'}],
                                                        switch=a)}

        d.interfaces = {'GigabitEthernet0/0': Interface(name='GigabitEthernet0/0',
                                                        neighbors=[{'hostname': 'C',
                                                                    'remote_int': 'GigabitEthernet0/0'}],
                                                        switch=c),
                        'GigabitEthernet0/1': Interface(name='GigabitEthernet0/1',
                                                        neighbors=[{'hostname': 'B',
                                                                    'remote_int': 'GigabitEthernet0/1'}],
                                                        switch=b)}

        f._find_links()
        assert f.switches['A'].interfaces['GigabitEthernet0/0'].neighbors[0] == f.switches['B'].interfaces['GigabitEthernet0/0']
        assert f.switches['A'].interfaces['GigabitEthernet0/1'].neighbors[0] == f.switches['C'].interfaces['GigabitEthernet0/1']
        assert f.switches['B'].interfaces['GigabitEthernet0/0'].neighbors[0] == f.switches['A'].interfaces['GigabitEthernet0/0']
        assert f.switches['B'].interfaces['GigabitEthernet0/1'].neighbors[0] == f.switches['D'].interfaces['GigabitEthernet0/1']
        assert f.switches['C'].interfaces['GigabitEthernet0/0'].neighbors[0] == f.switches['D'].interfaces['GigabitEthernet0/0']
        assert f.switches['C'].interfaces['GigabitEthernet0/1'].neighbors[0] == f.switches['A'].interfaces['GigabitEthernet0/1']
        assert f.switches['D'].interfaces['GigabitEthernet0/0'].neighbors[0] == f.switches['C'].interfaces['GigabitEthernet0/0']
        assert f.switches['D'].interfaces['GigabitEthernet0/1'].neighbors[0] == f.switches['B'].interfaces['GigabitEthernet0/1']

    def test_pathfinding_one_target(self):
        """
        A --- B
        |     |
        C --- D
        Find paths from C to A
        """

        f = Fabric()
        a = Switch(hostname="A", facts={'hostname': 'A', 'fqdn': 'A.not set'})
        b = Switch(hostname="B", facts={'hostname': 'B', 'fqdn': 'B.not set'})
        c = Switch(hostname="C", facts={'hostname': 'C', 'fqdn': 'C.not set'})
        d = Switch(hostname="D", facts={'hostname': 'D', 'fqdn': 'D.not set'})

        f.switches = {'A': a,
                      'B': b,
                      'C': c,
                      'D': d}

        a.interfaces = {'GigabitEthernet0/0': Interface(name='GigabitEthernet0/0',
                                                        neighbors=[{'hostname': 'B',
                                                                    'remote_int': 'GigabitEthernet0/0'}],
                                                        switch=a),
                        'GigabitEthernet0/1': Interface(name='GigabitEthernet0/1',
                                                        neighbors=[{'hostname': 'C',
                                                                    'remote_int': 'GigabitEthernet0/1'}],
                                                        switch=a)}

        b.interfaces = {'GigabitEthernet0/0': Interface(name='GigabitEthernet0/0',
                                                        neighbors=[{'hostname': 'A',
                                                                    'remote_int': 'GigabitEthernet0/0'}],
                                                        switch=b),
                        'GigabitEthernet0/1': Interface(name='GigabitEthernet0/1',
                                                        neighbors=[{'hostname': 'D',
                                                                    'remote_int': 'GigabitEthernet0/1'}],
                                                        switch=b)}

        c.interfaces = {'GigabitEthernet0/0': Interface(name='GigabitEthernet0/0',
                                                        neighbors=[{'hostname': 'D',
                                                                    'remote_int': 'GigabitEthernet0/0'}],
                                                        switch=c),
                        'GigabitEthernet0/1': Interface(name='GigabitEthernet0/1',
                                                        neighbors=[{'hostname': 'A',
                                                                    'remote_int': 'GigabitEthernet0/1'}],
                                                        switch=c)}

        d.interfaces = {'GigabitEthernet0/0': Interface(name='GigabitEthernet0/0',
                                                        neighbors=[{'hostname': 'C',
                                                                    'remote_int': 'GigabitEthernet0/0'}],
                                                        switch=d),
                        'GigabitEthernet0/1': Interface(name='GigabitEthernet0/1',
                                                        neighbors=[{'hostname': 'B',
                                                                    'remote_int': 'GigabitEthernet0/1'}],
                                                        switch=d)}

        f._find_links()

        paths = f.find_paths(c, [a])
        assert c.interfaces['GigabitEthernet0/0'] in paths[0]
        assert d.interfaces['GigabitEthernet0/1'] in paths[0]
        assert d.interfaces['GigabitEthernet0/0'] in paths[0]
        assert b.interfaces['GigabitEthernet0/0'] in paths[0]
        assert b.interfaces['GigabitEthernet0/1'] in paths[0]
        assert a.interfaces['GigabitEthernet0/0'] in paths[0]

        assert c.interfaces['GigabitEthernet0/1'] in paths[1]
        assert a.interfaces['GigabitEthernet0/1'] in paths[1]

    def test_pathfinding_two_targets(self):
        """
        A --- B
        |     |
        C --- D
        Find paths from C to A or B
        """

        f = Fabric()
        a = Switch(hostname="A", facts={'hostname': 'A', 'fqdn': 'A.not set'})
        b = Switch(hostname="B", facts={'hostname': 'B', 'fqdn': 'B.not set'})
        c = Switch(hostname="C", facts={'hostname': 'C', 'fqdn': 'C.not set'})
        d = Switch(hostname="D", facts={'hostname': 'D', 'fqdn': 'D.not set'})

        f.switches = {'A': a,
                      'B': b,
                      'C': c,
                      'D': d}

        a.interfaces = {'GigabitEthernet0/0': Interface(name='GigabitEthernet0/0',
                                                        neighbors=[{'hostname': 'B',
                                                                    'remote_int': 'GigabitEthernet0/0'}],
                                                        switch=a),
                        'GigabitEthernet0/1': Interface(name='GigabitEthernet0/1',
                                                        neighbors=[{'hostname': 'C',
                                                                    'remote_int': 'GigabitEthernet0/1'}],
                                                        switch=a)}

        b.interfaces = {'GigabitEthernet0/0': Interface(name='GigabitEthernet0/0',
                                                        neighbors=[{'hostname': 'A',
                                                                    'remote_int': 'GigabitEthernet0/0'}],
                                                        switch=b),
                        'GigabitEthernet0/1': Interface(name='GigabitEthernet0/1',
                                                        neighbors=[{'hostname': 'D',
                                                                    'remote_int': 'GigabitEthernet0/1'}],
                                                        switch=b)}

        c.interfaces = {'GigabitEthernet0/0': Interface(name='GigabitEthernet0/0',
                                                        neighbors=[{'hostname': 'D',
                                                                    'remote_int': 'GigabitEthernet0/0'}],
                                                        switch=c),
                        'GigabitEthernet0/1': Interface(name='GigabitEthernet0/1',
                                                        neighbors=[{'hostname': 'A',
                                                                    'remote_int': 'GigabitEthernet0/1'}],
                                                        switch=c)}

        d.interfaces = {'GigabitEthernet0/0': Interface(name='GigabitEthernet0/0',
                                                        neighbors=[{'hostname': 'C',
                                                                    'remote_int': 'GigabitEthernet0/0'}],
                                                        switch=d),
                        'GigabitEthernet0/1': Interface(name='GigabitEthernet0/1',
                                                        neighbors=[{'hostname': 'B',
                                                                    'remote_int': 'GigabitEthernet0/1'}],
                                                        switch=d)}

        f._find_links()

        paths = f.find_paths(c, [a, b])
        assert c.interfaces['GigabitEthernet0/0'] in paths[0]
        assert d.interfaces['GigabitEthernet0/1'] in paths[0]
        assert d.interfaces['GigabitEthernet0/0'] in paths[0]
        assert b.interfaces['GigabitEthernet0/1'] in paths[0]

        assert not b.interfaces['GigabitEthernet0/0'] in paths[0]
        assert not a.interfaces['GigabitEthernet0/0'] in paths[0]

        assert c.interfaces['GigabitEthernet0/1'] in paths[1]
        assert a.interfaces['GigabitEthernet0/1'] in paths[1]

    def test_pathfinding_two_targets_dead_end(self):
        """
        A --- B
        |     |
        C --- D - E
        Find paths from C to A or B.
        Check E not in path
        """

        f = Fabric()
        a = Switch(hostname="A", facts={'hostname': 'A', 'fqdn': 'A.not set'})
        b = Switch(hostname="B", facts={'hostname': 'B', 'fqdn': 'B.not set'})
        c = Switch(hostname="C", facts={'hostname': 'C', 'fqdn': 'C.not set'})
        d = Switch(hostname="D", facts={'hostname': 'D', 'fqdn': 'D.not set'})
        e = Switch(hostname="E", facts={'hostname': 'E', 'fqdn': 'E.not set'})

        f.switches = {'A': a,
                      'B': b,
                      'C': c,
                      'D': d,
                      'E': e}

        a.interfaces = {'GigabitEthernet0/0': Interface(name='GigabitEthernet0/0',
                                                        neighbors=[{'hostname': 'B',
                                                                    'remote_int': 'GigabitEthernet0/0'}],
                                                        switch=a),
                        'GigabitEthernet0/1': Interface(name='GigabitEthernet0/1',
                                                        neighbors=[{'hostname': 'C',
                                                                    'remote_int': 'GigabitEthernet0/1'}],
                                                        switch=a)}

        b.interfaces = {'GigabitEthernet0/0': Interface(name='GigabitEthernet0/0',
                                                        neighbors=[{'hostname': 'A',
                                                                    'remote_int': 'GigabitEthernet0/0'}],
                                                        switch=b),
                        'GigabitEthernet0/1': Interface(name='GigabitEthernet0/1',
                                                        neighbors=[{'hostname': 'D',
                                                                    'remote_int': 'GigabitEthernet0/1'}],
                                                        switch=b)}

        c.interfaces = {'GigabitEthernet0/0': Interface(name='GigabitEthernet0/0',
                                                        neighbors=[{'hostname': 'D',
                                                                    'remote_int': 'GigabitEthernet0/0'}],
                                                        switch=c),
                        'GigabitEthernet0/1': Interface(name='GigabitEthernet0/1',
                                                        neighbors=[{'hostname': 'A',
                                                                    'remote_int': 'GigabitEthernet0/1'}],
                                                        switch=c)}

        d.interfaces = {'GigabitEthernet0/0': Interface(name='GigabitEthernet0/0',
                                                        neighbors=[{'hostname': 'C',
                                                                    'remote_int': 'GigabitEthernet0/0'}],
                                                        switch=d),
                        'GigabitEthernet0/1': Interface(name='GigabitEthernet0/1',
                                                        neighbors=[{'hostname': 'B',
                                                                    'remote_int': 'GigabitEthernet0/1'}],
                                                        switch=d),
                        'GigabitEthernet0/2': Interface(name='GigabitEthernet0/2',
                                                        neighbors=[{'hostname': 'E',
                                                                    'remote_int': 'GigabitEthernet0/2'}],
                                                        switch=d)}

        e.interfaces = {'GigabitEthernet0/2': Interface(name='GigabitEthernet0/2',
                                                        neighbors=[{'hostname': 'D',
                                                                    'remote_int': 'GigabitEthernet0/2'}],
                                                        switch=d)}

        f._find_links()

        paths = f.find_paths(c, [a, b])
        assert e.interfaces['GigabitEthernet0/2'] not in paths[0]

    def test_mac_table(self):
        from netaddr import EUI
        """
        A G0/0 --- G0/0 B
      G0/1             G0/1
        |               |
      G0/1             G0/1
        C G0/0 --- G0/0 D G0/2 - - PC
        Check PC mac is on D-Gi0/2
        """

        f = Fabric()
        a = Switch(hostname="A", facts={'hostname': 'A', 'fqdn': 'A.not set'})
        b = Switch(hostname="B", facts={'hostname': 'B', 'fqdn': 'B.not set'})
        c = Switch(hostname="C", facts={'hostname': 'C', 'fqdn': 'C.not set'})
        d = Switch(hostname="D", facts={'hostname': 'D', 'fqdn': 'D.not set'})

        f.switches = {'A': a,
                      'B': b,
                      'C': c,
                      'D': d}

        a00 = Interface(name='GigabitEthernet0/0',
                        neighbors=[{'hostname': 'B',
                                   'remote_int': 'GigabitEthernet0/0'}],
                        switch=a)
        a01 = Interface(name='GigabitEthernet0/1',
                        neighbors=[{'hostname': 'C',
                                    'remote_int': 'GigabitEthernet0/1'}],
                        switch=a)
        b00 = Interface(name='GigabitEthernet0/0',
                        neighbors=[{'hostname': 'A',
                                    'remote_int': 'GigabitEthernet0/0'}],
                        switch=b)
        b01 = Interface(name='GigabitEthernet0/1',
                        neighbors=[{'hostname': 'D',
                                    'remote_int': 'GigabitEthernet0/1'}],
                        switch=b)
        c00 = Interface(name='GigabitEthernet0/0',
                        neighbors=[{'hostname': 'D',
                                    'remote_int': 'GigabitEthernet0/0'}],
                        switch=c)
        c01 = Interface(name='GigabitEthernet0/1',
                        neighbors=[{'hostname': 'A',
                                    'remote_int': 'GigabitEthernet0/1'}],
                        switch=c)
        c02 = Interface(name='GigabitEthernet0/2',
                        switch=c)
        d00 = Interface(name='GigabitEthernet0/0',
                        neighbors=[{'hostname': 'C',
                                    'remote_int': 'GigabitEthernet0/0'}],
                        switch=d)
        d01 = Interface(name='GigabitEthernet0/1',
                        neighbors=[{'hostname': 'B',
                                    'remote_int': 'GigabitEthernet0/1'}],
                        switch=d)

        a.interfaces = {'GigabitEthernet0/0': a00,
                        'GigabitEthernet0/1': a01}

        b.interfaces = {'GigabitEthernet0/0': b00,
                        'GigabitEthernet0/1': b01}

        c.interfaces = {'GigabitEthernet0/0': c00,
                        'GigabitEthernet0/1': c01,
                        'GigabitEthernet0/2': c02}

        d.interfaces = {'GigabitEthernet0/0': d00,
                        'GigabitEthernet0/1': d01}

        amac = EUI("aa:aa:aa:aa:aa:aa")
        bmac = EUI("bb:bb:bb:bb:bb:bb")
        cmac = EUI("cc:cc:cc:cc:cc:cc")
        dmac = EUI("dd:dd:dd:dd:dd:dd")
        pcmac = EUI("01:01:01:01:01:01")

        a.mac_table = {amac: {'interface': a.interfaces['GigabitEthernet0/0']},
                       cmac: {'interface': b.interfaces['GigabitEthernet0/0']},
                       pcmac: {'interface': b.interfaces['GigabitEthernet0/0']},
                       dmac: {'interface': b.interfaces['GigabitEthernet0/1']}}

        b.mac_table = {amac: {'interface': b.interfaces['GigabitEthernet0/0']},
                       cmac: {'interface': b.interfaces['GigabitEthernet0/1']},
                       pcmac: {'interface': b.interfaces['GigabitEthernet0/1']},
                       dmac: {'interface': b.interfaces['GigabitEthernet0/0']}}

        c.mac_table = {amac: {'interface': c.interfaces['GigabitEthernet0/1']},
                       bmac: {'interface': c.interfaces['GigabitEthernet0/1']},
                       pcmac: {'interface': c.interfaces['GigabitEthernet0/2']},
                       dmac: {'interface': c.interfaces['GigabitEthernet0/1']}}

        d.mac_table = {amac: {'interface': d.interfaces['GigabitEthernet0/1']},
                       bmac: {'interface': d.interfaces['GigabitEthernet0/1']},
                       pcmac: {'interface': d.interfaces['GigabitEthernet0/1']},
                       cmac: {'interface': d.interfaces['GigabitEthernet0/1']}}

        f.refresh_global_information()

        assert f.mac_table[pcmac] == {'interface' : c.interfaces['GigabitEthernet0/2']}
        assert c.interfaces['GigabitEthernet0/2'].mac_count == 1


if __name__ == '__main__':
    unittest.main()
