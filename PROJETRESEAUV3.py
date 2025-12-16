import json
import os
import re

# --- CONFIGURATION DES CHEMINS ---
# Ajustez le nom du fichier .gns3 si besoin
DOSSIER_PROJET = r"C:\Users\Lucas\GNS3\projects\RESEAUV4"
FICHIER_GNS3 = os.path.join(DOSSIER_PROJET, "RESEAUV4.gns3")
FICHIER_INTENT = os.path.join(DOSSIER_PROJET, "intent.json")
DOSSIER_CONFIGS = os.path.join(DOSSIER_PROJET, "configs_generees")

# --- OUTILS ---
def get_id(nom_routeur):
    """Extrait le chiffre du nom (ex: R12 -> 12)"""
    m = re.search(r'\d+', nom_routeur)
    return int(m.group()) if m else 0

def format_interface(adapter, port):
    """Formate le nom de l'interface (GNS3 -> Cisco)"""
    # Si vos routeurs sont en FastEthernet, changez ici
    return f"GigabitEthernet{adapter}/{port}"

# --- ETAPE 1 : ANALYSE DU GNS3 ---
if not os.path.exists(FICHIER_GNS3):
    print(f"ERREUR CRITIQUE : Fichier introuvable : {FICHIER_GNS3}")
    exit()

print(f"Lecture de la topologie : {FICHIER_GNS3}...")
with open(FICHIER_GNS3, 'r') as f:
    gns3_data = json.load(f)

# Création d'un dictionnaire ID -> Nom
nodes_map = {}
liste_routeurs = []
for node in gns3_data['topology']['nodes']:
    name = node['name']
    nodes_map[node['node_id']] = name
    liste_routeurs.append(name)

# Tri des routeurs pour l'affichage (R1, R2, R3...)
liste_routeurs.sort(key=get_id)
print(f"Routeurs trouvés : {', '.join(liste_routeurs)}\n")

# --- ETAPE 2 : INTERACTION UTILISATEUR (CREATION DE L'INTENT) ---
print("--- CONFIGURATION DE L'INTENTION RESEAU ---")
print("Nous allons définir les AS et les protocoles ensemble.\n")

intent_data = {
    "global_options": {
        "inter_as_subnet": input("Préfixe pour les liens Inter-AS (ex: 2001:FFFF) : ") or "2001:FFFF"
    },
    "as_list": []
}

nb_as = int(input("Combien d'Autonomous Systems (AS) voulez-vous configurer ? "))

available_routers = liste_routeurs.copy()

for i in range(1, nb_as + 1):
    print(f"\n--- Configuration de l'AS n°{i} ---")
    asn = input(f"Numéro de l'AS (ex: {100*i}) : ")
    prefix = input(f"Préfixe IPv6 de base (ex: 2001:{100*i}) : ")
    proto = input("Protocole de routage (rip / ospf) : ").lower()
    
    print(f"Routeurs disponibles : {', '.join(available_routers)}")
    print("Quels routeurs appartiennent à cet AS ?")
    start = int(input("  Du routeur numéro (ex: 1) : "))
    end = int(input("  Au routeur numéro (ex: 6) : "))
    
    # Sélection des routeurs
    selected_routers = []
    for r in available_routers:
        rid = get_id(r)
        if start <= rid <= end:
            selected_routers.append(r)
    
    # Validation
    print(f" -> Routeurs ajoutés à l'AS {asn} : {selected_routers}")
    
    intent_data["as_list"].append({
        "asn": asn,
        "prefix": prefix,
        "protocol": proto,
        "routers": selected_routers
    })

# Sauvegarde du fichier intent.json
with open(FICHIER_INTENT, 'w') as f:
    json.dump(intent_data, f, indent=4)
print(f"\nFichier '{FICHIER_INTENT}' généré avec succès !")

# --- ETAPE 3 : GENERATION DES CONFIGS ---
print("\n--- Génération des configurations Cisco ---")

configs = {}
for r in liste_routeurs:
    configs[r] = f"! Config générée pour {r}\nipv6 unicast-routing\n"

# Fonction pour retrouver les infos d'un routeur depuis l'intent
def get_router_info(router_name):
    for as_item in intent_data['as_list']:
        if router_name in as_item['routers']:
            return as_item
    return None # Routeur orphelin

# 3.1 Loopbacks
for r in liste_routeurs:
    info = get_router_info(r)
    if info:
        rid = get_id(r)
        configs[r] += f"interface Loopback0\n"
        configs[r] += f" ipv6 address {info['prefix']}::{rid}/128\n"
        configs[r] += " ipv6 enable\n exit\n"

# 3.2 Liens Physiques (Via GNS3 topology)
for link in gns3_data['topology']['links']:
    # Récupération des deux bouts du câble
    node_a = link['nodes'][0]
    node_b = link['nodes'][1]
    name_a = nodes_map[node_a['node_id']]
    name_b = nodes_map[node_b['node_id']]
    
    info_a = get_router_info(name_a)
    info_b = get_router_info(name_b)
    
    if not info_a or not info_b: continue # Skip si un routeur n'est pas configuré
    
    rid_a = get_id(name_a)
    rid_b = get_id(name_b)
    
    # Calcul Subnet
    subnet = ""
    if info_a['asn'] == info_b['asn']: # Interne
        mnemo = f"{min(rid_a, rid_b)}{max(rid_a, rid_b)}"
        subnet = f"{info_a['prefix']}:{mnemo}::"
    else: # Externe
        subnet = f"{intent_data['global_options']['inter_as_subnet']}::"
        
    # Interfaces
    int_a = format_interface(node_a['adapter_number'], node_a['port_number'])
    int_b = format_interface(node_b['adapter_number'], node_b['port_number'])
    
    # Ecriture
    suffix_a = "1" if rid_a < rid_b else "2"
    suffix_b = "2" if rid_a < rid_b else "1"
    
    configs[name_a] += f"interface {int_a}\n ipv6 address {subnet}{suffix_a}/64\n no shutdown\n exit\n"
    configs[name_b] += f"interface {int_b}\n ipv6 address {subnet}{suffix_b}/64\n no shutdown\n exit\n"

# 3.3 Protocoles de Routage (RIP & OSPF)
for r in liste_routeurs:
    info = get_router_info(r)
    if not info: continue
    
    proto = info['protocol']
    rid = get_id(r)
    
    # --- RIP ---
    if proto == 'rip':
        proc_name = "PROCESS_RIP"
        configs[r] += f"! RIP CONFIG\nipv6 router rip {proc_name}\n redistribute connected\n exit\n"
        # Activation sur Loopback
        configs[r] += f"interface Loopback0\n ipv6 rip {proc_name} enable\n exit\n"
        # Activation sur les interfaces physiques (Scan rapide des liens du routeur)
        # Note : Une méthode plus propre serait de stocker les interfaces actives, 
        # mais ici on réutilise la logique de parsing pour faire simple.
        # Pour ce script "Wizard", on va supposer que toutes les interfaces configurées parlent RIP.
        # (C'est le comportement standard dans ce genre de lab).
        # On ajoute une commande générique qui s'appliquera si l'interface existe :
        # Petite astuce : on ajoute RIP sur toutes les interfaces actives détectées précédemment
        # (Nécessiterait une structure de données plus complexe, je simplifie ici :)
        
    # --- OSPF ---
    elif proto == 'ospf':
        configs[r] += f"! OSPF CONFIG\nipv6 router ospf 1\n router-id {rid}.{rid}.{rid}.{rid}\n exit\n"
        configs[r] += f"interface Loopback0\n ipv6 ospf 1 area 0\n exit\n"

# Petite passe finale pour activer les protocoles sur les interfaces physiques
# On relit les liens pour injecter la commande protocole sur les bonnes interfaces
for link in gns3_data['topology']['links']:
    node_a = link['nodes'][0]
    name_a = nodes_map[node_a['node_id']]
    info_a = get_router_info(name_a)
    
    node_b = link['nodes'][1]
    name_b = nodes_map[node_b['node_id']]
    info_b = get_router_info(name_b)

    # Routeur A
    if info_a:
        int_a = format_interface(node_a['adapter_number'], node_a['port_number'])
        cmd = ""
        if info_a['protocol'] == 'rip': cmd = " ipv6 rip PROCESS_RIP enable"
        elif info_a['protocol'] == 'ospf': cmd = " ipv6 ospf 1 area 0"
        
        if cmd: configs[name_a] += f"interface {int_a}\n{cmd}\n exit\n"

    # Routeur B
    if info_b:
        int_b = format_interface(node_b['adapter_number'], node_b['port_number'])
        cmd = ""
        if info_b['protocol'] == 'rip': cmd = " ipv6 rip PROCESS_RIP enable"
        elif info_b['protocol'] == 'ospf': cmd = " ipv6 ospf 1 area 0"
        
        if cmd: configs[name_b] += f"interface {int_b}\n{cmd}\n exit\n"


# --- SAUVEGARDE FINALE ---
if not os.path.exists(DOSSIER_CONFIGS):
    os.makedirs(DOSSIER_CONFIGS)

for r, content in configs.items():
    path = os.path.join(DOSSIER_CONFIGS, f"{r}.cfg")
    with open(path, 'w') as f:
        f.write(content)
    print(f"Config générée : {r}.cfg")

print("\nTerminé ! Vous pouvez importer les fichiers.")