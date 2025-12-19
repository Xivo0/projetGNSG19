import json
import os
import re

# --- 1. CONFIGURATION ---
DOSSIER_PROJET = r"C:\Users\Lucas\GNS3\projects\untitled2"
FICHIER_GNS3 = os.path.join(DOSSIER_PROJET, "untitled2.gns3")
FICHIER_INTENT = os.path.join(DOSSIER_PROJET, "intent.json")
DOSSIER_SORTIE = os.path.join(DOSSIER_PROJET, "configs_finales")

# --- 2. FONCTIONS UTILITAIRES ---
def get_id(nom_routeur):
    match = re.search(r'\d+', nom_routeur)
    return int(match.group()) if match else 0

    
def format_interface(adapter, port):
        return f"GigabitEthernet{adapter}/{port}"
    


  

# --- 3. CHARGEMENT DES DONNEES ---
if not os.path.exists(FICHIER_GNS3) or not os.path.exists(FICHIER_INTENT):
    print("ERREUR: Fichiers manquants (.gns3 ou intent.json)")
    exit()

with open(FICHIER_GNS3, 'r') as f:
    gns3_data = json.load(f)
with open(FICHIER_INTENT, 'r') as f:
    intent = json.load(f)

nodes_map = {node['node_id']: node['name'] for node in gns3_data['topology']['nodes']}
liste_routeurs = sorted(list(nodes_map.values()), key=get_id)

configs = {r: f"! Config {r}\nipv6 unicast-routing\n" for r in liste_routeurs}

# --- 4. LOGIQUE METIER ---
def get_router_intent(router_name):
    for as_data in intent['as_list']:
        if router_name in as_data['routers']:
            return as_data
    return None

def get_link_relationship(r1, r2):
    for rel in intent.get('external_relationships', []):
        if r1 in rel['nodes'] and r2 in rel['nodes']:
            return rel['relationship']
    return "peer"

# --- 5. GENERATION CONFIGURATION ---

print("1. Configuration des IPs et Loopbacks...")
for r in liste_routeurs:
    data = get_router_intent(r)
    if not data: continue
    rid = get_id(r)
    
    # Loopback
    configs[r] += f"interface Loopback0\n"
    configs[r] += f" ipv6 address {data['prefix']}::{rid}/128\n"
    configs[r] += " ipv6 enable\n exit\n"

# Liens Physiques (Lecture GNS3)
for link in gns3_data['topology']['links']:
    node_a = link['nodes'][0]
    node_b = link['nodes'][1]
    name_a = nodes_map[node_a['node_id']]
    name_b = nodes_map[node_b['node_id']]
    
    data_a = get_router_intent(name_a)
    data_b = get_router_intent(name_b)
    
    if not data_a or not data_b: continue

    rid_a = get_id(name_a)
    rid_b = get_id(name_b)
    
    # Subnet
    if data_a['asn'] == data_b['asn']:
        mnemo = f"{min(rid_a, rid_b)}{max(rid_a, rid_b)}"
        subnet = f"{data_a['prefix']}:{mnemo}::"
    else:
        subnet = f"{intent['global_options']['inter_as_subnet']}::"

    int_a = format_interface(node_a['adapter_number'], node_a['port_number'])
    int_b = format_interface(node_b['adapter_number'], node_b['port_number'])
    
    suff_a = "1" if rid_a < rid_b else "2"
    suff_b = "2" if rid_a < rid_b else "1"
    
    # --- CORRECTION NO SHUTDOWN ---
    configs[name_a] += f"interface {int_a}\n ipv6 address {subnet}{suff_a}/64\n no shutdown\n exit\n"
    configs[name_b] += f"interface {int_b}\n ipv6 address {subnet}{suff_b}/64\n no shutdown\n exit\n"

print("2. Configuration IGP (RIP/OSPF)...")
# Configuration Globale des protocoles
for r in liste_routeurs:
    data = get_router_intent(r)
    if not data: continue
    
    if data['protocol'] == 'rip':
        proc = data['rip_process_name']
        configs[r] += f"ipv6 router rip {proc}\n redistribute connected\n exit\n"
        configs[r] += f"interface Loopback0\n ipv6 rip {proc} enable\n exit\n"
        
    elif data['protocol'] == 'ospf':
        proc = data['ospf_process_id']
        rid = get_id(r)
        configs[r] += f"ipv6 router ospf {proc}\n router-id {rid}.{rid}.{rid}.{rid}\n exit\n"
        configs[r] += f"interface Loopback0\n ipv6 ospf {proc} area 0\n exit\n"

# --- CORRECTION : ACTIVATION IGP SUR INTERFACES PHYSIQUES ---
print("   -> Activation IGP sur les liens physiques...")
for link in gns3_data['topology']['links']:
    node_a = link['nodes'][0]
    node_b = link['nodes'][1]
    name_a = nodes_map[node_a['node_id']]
    name_b = nodes_map[node_b['node_id']]
    
    data_a = get_router_intent(name_a)
    data_b = get_router_intent(name_b)

    # Pour Routeur A
    if data_a and data_a['asn'] == data_b['asn']: # Seulement si lien interne (Même AS)
        int_a = format_interface(node_a['adapter_number'], node_a['port_number'])
        if data_a['protocol'] == 'rip':
            configs[name_a] += f"interface {int_a}\n ipv6 rip {data_a['rip_process_name']} enable\n exit\n"
        elif data_a['protocol'] == 'ospf':
            configs[name_a] += f"interface {int_a}\n ipv6 ospf {data_a['ospf_process_id']} area 0\n exit\n"

    # Pour Routeur B
    if data_b and data_b['asn'] == data_a['asn']: # Seulement si lien interne
        int_b = format_interface(node_b['adapter_number'], node_b['port_number'])
        if data_b['protocol'] == 'rip':
            configs[name_b] += f"interface {int_b}\n ipv6 rip {data_b['rip_process_name']} enable\n exit\n"
        elif data_b['protocol'] == 'ospf':
            configs[name_b] += f"interface {int_b}\n ipv6 ospf {data_b['ospf_process_id']} area 0\n exit\n"


print("3. Configuration BGP Avancée (Policies)...")
for r in liste_routeurs:
    data = get_router_intent(r)
    if not data: continue
    
    asn = data['asn']
    rid = get_id(r)
    bgp_rid = f"{rid}.{rid}.{rid}.{rid}"
    
    configs[r] += f"! --- BGP --- \n"
    configs[r] += f"router bgp {asn}\n"
    configs[r] += f" bgp router-id {bgp_rid}\n"
    configs[r] += f" no bgp default ipv4-unicast\n"
    
    neighbors_config = ""
    
    # 3.1 iBGP
    for neighbor in data['routers']:
        if neighbor == r: continue
        n_rid = get_id(neighbor)
        n_ip = f"{data['prefix']}::{n_rid}"
        
        configs[r] += f" neighbor {n_ip} remote-as {asn}\n"
        configs[r] += f" neighbor {n_ip} update-source Loopback0\n"
        neighbors_config += f"  neighbor {n_ip} activate\n"
        neighbors_config += f"  neighbor {n_ip} next-hop-self\n"
        neighbors_config += f"  neighbor {n_ip} send-community\n"

    # 3.2 eBGP
    for link in gns3_data['topology']['links']:
        node_a_id = link['nodes'][0]['node_id']
        node_b_id = link['nodes'][1]['node_id']
        name_a, name_b = nodes_map[node_a_id], nodes_map[node_b_id]
        
        me, neighbor_name = (None, None)
        if name_a == r: me, neighbor_name = name_a, name_b
        elif name_b == r: me, neighbor_name = name_b, name_a
        else: continue
        
        neighbor_data = get_router_intent(neighbor_name)
        
        if neighbor_data and neighbor_data['asn'] != asn:
            subnet = f"{intent['global_options']['inter_as_subnet']}::"
            n_rid = get_id(neighbor_name)
            suffix = "1" if n_rid < rid else "2"
            n_ip = f"{subnet}{suffix}"
            
            relationship = get_link_relationship(me, neighbor_name)
            
            configs[r] += f" neighbor {n_ip} remote-as {neighbor_data['asn']}\n"
            
            rm_in = f"RM-{relationship.upper()}-IN"
            rm_out = f"RM-{relationship.upper()}-OUT"
            
            neighbors_config += f"  neighbor {n_ip} activate\n"
            neighbors_config += f"  neighbor {n_ip} send-community\n"
            neighbors_config += f"  neighbor {n_ip} route-map {rm_in} in\n"
            neighbors_config += f"  neighbor {n_ip} route-map {rm_out} out\n"

    configs[r] += " address-family ipv6 unicast\n"
    configs[r] += f"  network {data['prefix']}::/32\n"
    configs[r] += neighbors_config
    configs[r] += " exit-address-family\n"
    configs[r] += " exit\n"

    # --- CORRECTION INDENTATION SECTION 3.3 ---
    # 3.3 DEFINITION DES ROUTE-MAPS (Policies)
    pols = intent['bgp_policies']
    comm_cust = pols['customer_community']
    
    configs[r] += "! --- POLICIES ---\n"
    configs[r] += f"ip community-list 1 permit {comm_cust}\n"
    
    # CUSTOMER
    configs[r] += f"route-map RM-CUSTOMER-IN permit 10\n"
    configs[r] += f" set local-preference {pols['local_pref_customer']}\n"
    configs[r] += f" set community {comm_cust} additive\n exit\n"
    configs[r] += f"route-map RM-CUSTOMER-OUT permit 10\n exit\n"
    
    # PROVIDER
    configs[r] += f"route-map RM-PROVIDER-IN permit 10\n"
    configs[r] += f" set local-preference {pols['local_pref_provider']}\n exit\n"
    configs[r] += f"route-map RM-PROVIDER-OUT permit 10\n"
    configs[r] += f" match community 1\n exit\n"
    
    # PEER
    configs[r] += f"route-map RM-PEER-IN permit 10\n"
    configs[r] += f" set local-preference {pols['local_pref_peer']}\n exit\n"
    configs[r] += f"route-map RM-PEER-OUT permit 10\n"
    configs[r] += f" match community 1\n exit\n"


# --- 6. SAUVEGARDE ---
if not os.path.exists(DOSSIER_SORTIE):
    os.makedirs(DOSSIER_SORTIE)

for name, content in configs.items():
    # --- CORRECTION CRITIQUE ---
    # On ajoute 'end' pour dire au routeur que le fichier est fini
    # On ajoute 'write memory' pour sauvegarder dès le premier boot (optionnel mais pratique)
    content += "end\n"
    content += "write memory\n"
    
    path = os.path.join(DOSSIER_SORTIE, f"{name}.cfg")
    with open(path, 'w') as f:
        f.write(content)
    print(f"Généré : {name}.cfg")