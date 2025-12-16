import json
import os
import re

# --- CONFIGURATION ---
# Chemin vers votre fichier de projet GNS3
chemin_projet = r"C:\Users\Lucas\GNS3\projects\RESEAUV4\RESEAUV4.gns3"
dossier_sortie = r"C:\Users\Lucas\GNS3\projects\RESEAUV4\configs_generees"

# Définition des règles de l'AS (Intention)
# On déduit l'AS selon le numéro du routeur
def get_router_info(router_name):
    rid = int(re.search(r'\d+', router_name).group())
    
    # R1 à R7 = AS 100 (RIP)
    if 1 <= rid <= 7:
        return {"asn": "100", "prefix": "2001:100", "proto": "rip"}
    
    # R8 à R14 = AS 200 (OSPF)
    elif 8 <= rid <= 14:
        return {"asn": "200", "prefix": "2001:200", "proto": "ospf"}
    
    # Autres (si vous en rajoutez)
    else:
        return {"asn": "999", "prefix": "2001:999", "proto": "none"}

# --- CHARGEMENT DU GNS3 ---
if not os.path.exists(chemin_projet):
    print(f"Erreur : Fichier introuvable -> {chemin_projet}")
    exit()

with open(chemin_projet, 'r') as f:
    gns3_data = json.load(f)

# 1. Création d'un dictionnaire ID -> Nom (ex: "uuid-long..." -> "R1")
nodes_map = {}
for node in gns3_data['topology']['nodes']:
    nodes_map[node['node_id']] = node['name']

# Dictionnaire pour stocker les configs
configs = {}
for name in nodes_map.values():
    configs[name] = f"! Config générée pour {name}\nipv6 unicast-routing\n"

# --- ETAPE 1 : LOOPBACKS ---
print("--- Génération des Loopbacks ---")
for name in nodes_map.values():
    info = get_router_info(name)
    rid = int(re.search(r'\d+', name).group())
    
    configs[name] += f"interface Loopback0\n"
    configs[name] += f" ipv6 address {info['prefix']}::{rid}/128\n"
    configs[name] += " ipv6 enable\n exit\n"

# --- ETAPE 2 : LIENS PHYSIQUES (Depuis le fichier GNS3) ---
print("--- Analyse des câbles GNS3 ---")

def format_interface(adapter, port):
    # Adaptez selon vos routeurs (c7200 utilise souvent GiX/0 ou GiX/Y)
    # Dans le JSON GNS3, adapter_number correspond souvent au Slot
    return f"GigabitEthernet{adapter}/{port}"

for link in gns3_data['topology']['links']:
    # Un lien connecte deux noeuds
    node_a = link['nodes'][0]
    node_b = link['nodes'][1]
    
    name_a = nodes_map[node_a['node_id']]
    name_b = nodes_map[node_b['node_id']]
    
    # Récupération des infos AS
    info_a = get_router_info(name_a)
    info_b = get_router_info(name_b)
    
    rid_a = int(re.search(r'\d+', name_a).group())
    rid_b = int(re.search(r'\d+', name_b).group())

    # Calcul du Subnet
    subnet = ""
    # Même AS (Lien Interne)
    if info_a['asn'] == info_b['asn']:
        # Convention : 2001:100:12::/64
        min_id = min(rid_a, rid_b)
        max_id = max(rid_a, rid_b)
        subnet = f"{info_a['prefix']}:{min_id}{max_id}::"
    else:
        # AS Différent (Lien Externe)
        subnet = "2001:FFFF::"

    # Attribution .1 / .2
    ip_suffix_a = "1" if rid_a < rid_b else "2"
    ip_suffix_b = "1" if rid_a > rid_b else "2" # L'inverse

    # Nom des interfaces (Depuis le JSON GNS3)
    int_a = format_interface(node_a['adapter_number'], node_a['port_number'])
    int_b = format_interface(node_b['adapter_number'], node_b['port_number'])

    # Ecriture Config Routeur A
    configs[name_a] += f"interface {int_a}\n"
    configs[name_a] += f" ipv6 address {subnet}{ip_suffix_a}/64\n"
    configs[name_a] += " no shutdown\n exit\n"

    # Ecriture Config Routeur B
    configs[name_b] += f"interface {int_b}\n"
    configs[name_b] += f" ipv6 address {subnet}{ip_suffix_b}/64\n"
    configs[name_b] += " no shutdown\n exit\n"

# --- PARTIE 3 : ROUTAGE RIPng (AS X) ---
def generate_rip_configuration():
    print("--- Génération de la configuration RIPng ---")
    process_name = "PROCESS_RIP"  # Nom du processus RIP (arbitraire)

    # On parcourt tous les routeurs connus
    for name in nodes_map.values():
        info = get_router_info(name)

        # On ne configure QUE si le protocole est 'rip'
        if info['proto'] == 'rip':
            
            # 1. Configuration Globale du Processus
            configs[name] += f"! --- Configuration RIPng ---\n"
            configs[name] += f"ipv6 router rip {process_name}\n"
            configs[name] += " redistribute connected\n" # Important pour annoncer les réseaux directs
            configs[name] += " exit\n"

            # 2. Activation sur la Loopback
            configs[name] += "interface Loopback0\n"
            configs[name] += f" ipv6 rip {process_name} enable\n"
            configs[name] += " exit\n"

            # 3. Activation sur les interfaces physiques
            # On doit re-scanner la topologie pour trouver les interfaces de ce routeur
            for link in gns3_data['topology']['links']:
                node_a = link['nodes'][0]
                node_b = link['nodes'][1]
                
                # On cherche si le routeur actuel (name) est l'un des bouts du lien
                target_node = None
                if nodes_map[node_a['node_id']] == name:
                    target_node = node_a
                elif nodes_map[node_b['node_id']] == name:
                    target_node = node_b
                
                # Si on a trouvé une interface appartenant à ce routeur
                if target_node:
                    int_name = format_interface(target_node['adapter_number'], target_node['port_number'])
                    
                    configs[name] += f"interface {int_name}\n"
                    configs[name] += f" ipv6 rip {process_name} enable\n"
                    configs[name] += " exit\n"

generate_rip_configuration() 



# --- SAUVEGARDE ---
if not os.path.exists(dossier_sortie):
    os.makedirs(dossier_sortie)

for name, cfg in configs.items():
    chemin_fichier = os.path.join(dossier_sortie, f"{name}.cfg")
    with open(chemin_fichier, 'w') as f:
        f.write(cfg)
    print(f"Fichier créé : {name}.cfg")

print("\nTerminé ! Vous pouvez copier/coller ces configs.")