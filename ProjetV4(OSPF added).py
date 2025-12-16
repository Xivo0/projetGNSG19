import json
import os
import re

# ==========================================
# 1. CONFIGURATION ET OUTILS
# ==========================================

# --- CHEMINS ---
# Adaptez le chemin de votre dossier projet ici
DOSSIER_PROJET = r"C:\Users\redan\GNS3\projects\GNS_projet"
# Le script cherche le fichier .gns3 automatiquement dans le dossier
try:
    fichiers_gns3 = [f for f in os.listdir(DOSSIER_PROJET) if f.endswith('.gns3')]
    if not fichiers_gns3: raise FileNotFoundError
    FICHIER_GNS3 = os.path.join(DOSSIER_PROJET, fichiers_gns3[0])
except:
    print(f"ERREUR : Aucun fichier .gns3 trouvé dans {DOSSIER_PROJET}")
    exit()

FICHIER_INTENT = os.path.join(DOSSIER_PROJET, "intent.json")
DOSSIER_CONFIGS = os.path.join(DOSSIER_PROJET, "configs_generees")

# --- FONCTIONS UTILES ---
def get_id(nom_routeur):
    """Extrait le chiffre du nom (ex: R12 -> 12)"""
    m = re.search(r'\d+', nom_routeur)
    return int(m.group()) if m else 0

def format_interface(adapter, port):
    """Formate le nom de l'interface (GNS3 -> Cisco)"""
    # Si vos routeurs sont en FastEthernet, remplacez par "FastEthernet"
    return f"GigabitEthernet{adapter}/{port}"

# ==========================================
# 2. ANALYSE DE LA TOPOLOGIE (GNS3)
# ==========================================

print(f"--- Lecture de la topologie : {FICHIER_GNS3} ---")
with open(FICHIER_GNS3, 'r') as f:
    gns3_data = json.load(f)

# Mapping ID -> Nom
nodes_map = {}
liste_routeurs = []
for node in gns3_data['topology']['nodes']:
    name = node['name']
    nodes_map[node['node_id']] = name
    liste_routeurs.append(name)

# Tri pour affichage propre
liste_routeurs.sort(key=get_id)
print(f"Routeurs détectés : {', '.join(liste_routeurs)}\n")

# ==========================================
# 3. INTERACTION UTILISATEUR (INTENT)
# ==========================================

print("--- DEFINITION DE L'INTENTION RESEAU ---")
print("Nous allons définir les AS, les protocoles et les métriques.\n")

intent_data = {
    "global_options": {
        "inter_as_subnet": input("Préfixe pour les liens Inter-AS (ex: 2001:FFFF) [Entrée pour défaut]: ") or "2001:FFFF"
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
    print("Plage de routeurs pour cet AS :")
    start = int(input("  Du routeur numéro (ex: 1) : "))
    end = int(input("  Au routeur numéro (ex: 6) : "))
    
    # Sélection des routeurs
    selected_routers = []
    for r in available_routers:
        rid = get_id(r)
        if start <= rid <= end:
            selected_routers.append(r)
    
    # Structure de l'AS
    as_object = {
        "asn": asn,
        "prefix": prefix,
        "protocol": proto,
        "routers": selected_routers,
        "custom_costs": [] # Liste vide pour les coûts
    }
    
    # --- AJOUT SPECIFIQUE OSPF METRIC (Section 3.4.2) ---
    if proto == 'ospf':
        print(f"\n[OPTION OSPF] Voulez-vous optimiser les coûts des liens pour l'AS {asn} ?")
        want_metrics = input("Configurer des coûts spécifiques ? (o/n) : ")
        
        if want_metrics.lower() == 'o':
            print("Entrez les liens (ex: R7 vers R8 avec coût 50). Tapez 'fin' pour arrêter.")
            while True:
                r1 = input("  Routeur 1 (ex: R7 ou fin) : ")
                if r1.lower() == 'fin': break
                r2 = input("  Routeur 2 (ex: R8) : ")
                cost = input("  Coût (Metric) (ex: 50) : ")
                
                as_object['custom_costs'].append({
                    "r1": r1, "r2": r2, "cost": int(cost)
                })
                print(f"  -> Lien {r1}-{r2} coût {cost} enregistré.")

    intent_data["as_list"].append(as_object)

# Sauvegarde Intent
with open(FICHIER_INTENT, 'w') as f:
    json.dump(intent_data, f, indent=4)
print(f"\nFichier '{FICHIER_INTENT}' sauvegardé.")

# ==========================================
# 4. GENERATION DES CONFIGURATIONS
# ==========================================
print("\n--- Génération des fichiers .cfg ---")

configs = {}
for r in liste_routeurs:
    configs[r] = f"! Config générée pour {r}\nipv6 unicast-routing\n"

def get_router_info(router_name):
    """Retrouve les infos AS d'un routeur"""
    for as_item in intent_data['as_list']:
        if router_name in as_item['routers']:
            return as_item
    return None

def get_ospf_cost(as_info, r_name, neighbor_name):
    """Cherche si un coût est défini dans l'intent pour ce lien"""
    if 'custom_costs' not in as_info: return None
    for item in as_info['custom_costs']:
        # Vérif bidirectionnelle
        if (item['r1'] == r_name and item['r2'] == neighbor_name) or \
           (item['r1'] == neighbor_name and item['r2'] == r_name):
            return item['cost']
    return None

# --- 4.1 Loopbacks ---
for r in liste_routeurs:
    info = get_router_info(r)
    if info:
        rid = get_id(r)
        configs[r] += f"interface Loopback0\n"
        configs[r] += f" ipv6 address {info['prefix']}::{rid}/128\n"
        configs[r] += " ipv6 enable\n"
        
        # Activation IGP sur Loopback
        if info['protocol'] == 'rip':
            configs[r] += " ipv6 rip PROCESS_RIP enable\n"
        elif info['protocol'] == 'ospf':
            configs[r] += " ipv6 ospf 1 area 0\n"
            
        configs[r] += " exit\n"

# --- 4.2 Configuration Globale Routing ---
for r in liste_routeurs:
    info = get_router_info(r)
    if not info: continue
    rid = get_id(r)
    
    if info['protocol'] == 'rip':
        configs[r] += f"ipv6 router rip PROCESS_RIP\n redistribute connected\n exit\n"
        
    elif info['protocol'] == 'ospf':
        configs[r] += f"ipv6 router ospf 1\n router-id {rid}.{rid}.{rid}.{rid}\n exit\n"

# --- 4.3 Interfaces Physiques & Métriques ---
# On parcourt les liens du GNS3 pour configurer les interfaces
for link in gns3_data['topology']['links']:
    # Récupération des extrémités
    node_a = link['nodes'][0]
    node_b = link['nodes'][1]
    name_a = nodes_map[node_a['node_id']]
    name_b = nodes_map[node_b['node_id']]
    
    info_a = get_router_info(name_a)
    info_b = get_router_info(name_b)
    
    if not info_a or not info_b: continue
    
    rid_a = get_id(name_a)
    rid_b = get_id(name_b)
    
    # A. Calcul Adresse IP (Subnet)
    subnet = ""
    if info_a['asn'] == info_b['asn']: # Interne
        mnemo = f"{min(rid_a, rid_b)}{max(rid_a, rid_b)}"
        subnet = f"{info_a['prefix']}:{mnemo}::"
    else: # Externe (eBGP link)
        subnet = f"{intent_data['global_options']['inter_as_subnet']}::"
        
    int_a = format_interface(node_a['adapter_number'], node_a['port_number'])
    int_b = format_interface(node_b['adapter_number'], node_b['port_number'])
    
    suffix_a = "1" if rid_a < rid_b else "2"
    suffix_b = "2" if rid_a < rid_b else "1"

    # B. Construction Commande Interface Routeur A
    configs[name_a] += f"interface {int_a}\n"
    configs[name_a] += f" ipv6 address {subnet}{suffix_a}/64\n"
    configs[name_a] += " no shutdown\n"
    
    if info_a['protocol'] == 'rip':
        configs[name_a] += " ipv6 rip PROCESS_RIP enable\n"
    elif info_a['protocol'] == 'ospf':
        configs[name_a] += " ipv6 ospf 1 area 0\n"
        # -- Ajout du coût OSPF --
        cost = get_ospf_cost(info_a, name_a, name_b)
        if cost:
            configs[name_a] += f" ipv6 ospf cost {cost}\n"
            print(f"   [OSPF] Coût {cost} appliqué sur {name_a} -> {name_b}")
            
    configs[name_a] += " exit\n"

    # C. Construction Commande Interface Routeur B (Symétrique)
    configs[name_b] += f"interface {int_b}\n"
    configs[name_b] += f" ipv6 address {subnet}{suffix_b}/64\n"
    configs[name_b] += " no shutdown\n"
    
    if info_b['protocol'] == 'rip':
        configs[name_b] += " ipv6 rip PROCESS_RIP enable\n"
    elif info_b['protocol'] == 'ospf':
        configs[name_b] += " ipv6 ospf 1 area 0\n"
        # -- Ajout du coût OSPF --
        cost = get_ospf_cost(info_b, name_b, name_a)
        if cost:
            configs[name_b] += f" ipv6 ospf cost {cost}\n"
    
    configs[name_b] += " exit\n"

# --- SAUVEGARDE FINALE ---
if not os.path.exists(DOSSIER_CONFIGS):
    os.makedirs(DOSSIER_CONFIGS)

print(f"\nEcriture des fichiers dans : {DOSSIER_CONFIGS}")
for r, content in configs.items():
    path = os.path.join(DOSSIER_CONFIGS, f"{r}.cfg")
    with open(path, 'w') as f:
        f.write(content)

print("Terminé ! Configs prêtes.")
