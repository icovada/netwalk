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

import pickle
import networkx as nx
from pyvis.network import Network
from netwalk import Interface

#matplotlib.use("Agg")

with open('fabric_data.bin', 'rb') as fabricfile:
    fabric = pickle.load(fabricfile)

g = nx.Graph()

g.add_nodes_from([swdata.facts['fqdn'] for swname, swdata in fabric.switches.items()])

labeldict = {y: x for x, y in fabric.switches.items()}

for swname, swdata in fabric.switches.items():
    for intname, intdata in swdata.interfaces.items():
        if hasattr(intdata, 'neighbors'):
            if len(intdata.neighbors) == 1:
                if isinstance(intdata.neighbors[0], Interface):
                    side_a = intdata.switch.facts['fqdn']
                    side_b = intdata.neighbors[0].switch.facts['fqdn']

                    #try:
                    #    assert side_a.name != "SMba32_CStellaICT"
                    #    assert side_b.name != "SMba32_CStellaICT"
                    #except AssertionError:
                    #    continue

                    g.add_edge(side_a, side_b)




nt = Network('100%', '75%')
nt.show_buttons()
nt.from_nx(g)
nt.show('nx.html')