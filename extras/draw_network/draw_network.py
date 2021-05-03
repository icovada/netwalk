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