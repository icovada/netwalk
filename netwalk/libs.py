"Miscellaneous functions that can be useful across objects"

def interface_name_expander(name):
    mapping = {'Fa': 'FastEthernet',
               'Gi': 'GigabitEthernet',
               'Te': 'TenGigabitEthernet',
               'Po': 'Port-Channel',
               'Twe': 'TwentyFiveGigabitEthernet'}
    
    for k, v in mapping.items():
        if name.startswith(k):
            return name.replace(k, v)
    
    return name