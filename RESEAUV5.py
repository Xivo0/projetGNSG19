import json
import os
import re #pour les expressions régulières

# --- 1. CONFIGURATION ---
DOSSIER_PROJET = r"C:\Users\Lucas\GNS3\projects\untitled4" #Chemin vers le dossier du projet GNS3 (à modifier selon config)
FICHIER_GNS3 = os.path.join(DOSSIER_PROJET, "untitled4.gns3")
FICHIER_INTENT = os.path.join(DOSSIER_PROJET, "intent.json")
DOSSIER_SORTIE = os.path.join(DOSSIER_PROJET, "configs_finales")

# --- 2. FONCTIONS UTILITAIRES ---
def get_id(nom_routeur): #extrait l'ID numérique du routeur à partir de son nom ("R12" -> 12)
    match = re.search(r'\d+', nom_routeur) #re.search cherche une séquence de chiffres dans le nom du routeur
    return int(match.group()) if match else 0  #match.group() retourne la séquence trouvée

    
def format_interface(adapter, port):
        if adapter == 0:
            return f"GigabitEthernet{adapter}/{port}"
        else:    
            return f"FastEthernet{adapter}/{port}"
#s'adapte selon les noms des liens des routeurs disponibles (à modifier selon config sur GNS3)
    

  

# --- 3. CHARGEMENT DES DONNEES ---
if not os.path.exists(FICHIER_GNS3) or not os.path.exists(FICHIER_INTENT):
    print("ERREUR: Fichiers manquants (.gns3 ou intent.json)")
    exit()

with open(FICHIER_GNS3, 'r') as f:
    gns3_data = json.load(f)
with open(FICHIER_INTENT, 'r') as f:
    intent = json.load(f)

nodes_map = {node['node_id']: node['name'] for node in gns3_data['topology']['nodes']}
print(nodes_map)
#structure du dictionnaire {node_id: node_name}
liste_routeurs = sorted(list(nodes_map.values()), key=get_id) #Liste des noms de routeurs triés par ID
#print(liste_routeurs)

configs = {r: f"! Config {r}\nipv6 unicast-routing\n" for r in liste_routeurs} 
#obligatoire pour activer le routage ipv6


def get_router_intent(router_name): #Retourne les données intent pour un routeur donné sous forme de dictionnaire
    #print(intent['as_list']) #test
    for as_data in intent['as_list']: #intent['as_list'] = liste des AS
        if router_name in as_data['routers']: #pour chaque routeur dans la liste des routeurs de l'AS, si on trouve le routeur demandé, on retourne les données de l'AS
            return as_data
            #as_data sous la forme : {'asn': , 'prefix': , 'protocol': 'ospf, 'ospf_process_id': 1, 'routers': []}
            
    return None

def get_link_relationship(r1, r2): #définit les relations entre deux routeurs
    print(intent.get('external_relationships', [])) #test
    for rel in intent.get('external_relationships', []): #rel sous la forme {'nodes': [r1, r2], 'relationship': 'customer/provider/peer'}
        if r1 in rel['nodes'] and r2 in rel['nodes']:
            return rel['relationship'] #customer, provider, peer, selon intent.json
    return "peer"
#les liens non spécifiés sont considérés comme des peers par défaut
    

print("1. Configuration des IPs et Loopbacks...")
for r in liste_routeurs:
    data = get_router_intent(r)
    if not data: continue
    rid = get_id(r) 
    
    # Loopback
    configs[r] += f"interface Loopback0\n"
    configs[r] += f" ipv6 address {data['prefix']}::{rid}/128\n"
    configs[r] += " ipv6 enable\n exit\n"

    # --- AJOUT OBLIGATOIRE POUR BGP ---
    # Crée la route statique pour que la commande 'network' fonctionne
    configs[r] += f"ipv6 route {data['prefix']}::/32 Null0\n"

# Liens Physiques (Lecture GNS3)
for link in gns3_data['topology']['links']:#lis automatiquement la topologie réel du reseau (boucle sur chaque lien entre 2 routeurs pour donner un nom à ces routeurs)
    node_a = link['nodes'][0]
    node_b = link['nodes'][1]
    name_a = nodes_map[node_a['node_id']]#traduit le name_id du routeur donner par le .gns3 en routeur R1, R2 ect...
    name_b = nodes_map[node_b['node_id']]
    
    data_a = get_router_intent(name_a)#recupération de l'intent / data_a est tout le bloc JSON décrivant l’AS du routeur (prefix/protocol/routeur)
    data_b = get_router_intent(name_b)
    
    if not data_a or not data_b: continue#filtrage des non routeurs (sur le .gns3 il peut y avoir des pc, des switchs...)

    rid_a = get_id(name_a)#recupére l'id du routeur ici si R1 -> 1
    rid_b = get_id(name_b)
    
    # Subnet
    if data_a['asn'] == data_b['asn']:#Ce lien est-il interne à un AS ou entre deux AS différents ?
        mnemo = f"{min(rid_a, rid_b)}:{max(rid_a, rid_b)}" # traduit le lien entre 2 routeurs: R3 ↔ R7 min:3 max:7 -> mnemo = 37
        subnet = f"{data_a['prefix']}:{mnemo}::"# generation du prefix 
    else:
        #correction duplicata d'ip
        # On utilise les IDs pour rendre le lien unique aussi en Inter-AS 
        mnemo = f"{min(rid_a, rid_b)}:{max(rid_a, rid_b)}"
        subnet = f"{intent['global_options']['inter_as_subnet']}:{mnemo}::"#lien intra-AS unique

    int_a = format_interface(node_a['adapter_number'], node_a['port_number'])#dans GNS3 "adapter_number": 0,"port_number": 1 -> GigabitEthernet0/1
    int_b = format_interface(node_b['adapter_number'], node_b['port_number'])
    
    """suff_a = "1" if rid_a < rid_b else "2"# exemple R2 ↔ R5 2<5 R2::1 et R5::2
    suff_b = "2" if rid_a < rid_b else "1"
    """
    suff_a = f"{rid_a}" #mieux car on prends l'id en suffixe
    suff_b = f"{rid_b}"
    
    # --- CORRECTION NO SHUTDOWN ---
    configs[name_a] += f"interface {int_a}\n ipv6 address {subnet}{suff_a}/64\n no shutdown\n exit\n"
    configs[name_b] += f"interface {int_b}\n ipv6 address {subnet}{suff_b}/64\n no shutdown\n exit\n"

print("2. Configuration IGP (RIP/OSPF)...")
# Configuration Globale des protocoles
for r in liste_routeurs:
    data = get_router_intent(r)
    if not data: continue#si le routeur n'est pas decrit dans le intent on passe 
    
    if data['protocol'] == 'rip':
        proc = data['rip_process_name']#Récupère le nom du processus RIP
        configs[r] += f"ipv6 router rip {proc}\n redistribute connected\n exit\n"#Ajoute une configuration Cisco au buffer
        configs[r] += f"interface Loopback0\n ipv6 rip {proc} enable\n exit\n"#interface doit être explicitement activée sur le loopback sinon pas annoncé 
        
    elif data['protocol'] == 'ospf':#cas ospf 
        proc = data['ospf_process_id']
        rid = get_id(r)#R3 → 3.3.3.3
        configs[r] += f"ipv6 router ospf {proc}\n router-id {rid}.{rid}.{rid}.{rid}\n exit\n"
        configs[r] += f"interface Loopback0\n ipv6 ospf {proc} area 0\n exit\n"#active ospf sur le loopback 

# --- CORRECTION : ACTIVATION IGP SUR INTERFACES PHYSIQUES ---
print("   -> Activation IGP sur les liens physiques...")
for link in gns3_data['topology']['links']:# parcour chaque cable phyqique 
    node_a = link['nodes'][0]#recup les 2 extremité du lien 
    node_b = link['nodes'][1]
    name_a = nodes_map[node_a['node_id']]#convertion ID GNS3
    name_b = nodes_map[node_b['node_id']]
    
    data_a = get_router_intent(name_a)#Associe extrémité à son As
    data_b = get_router_intent(name_b)

    # Pour Routeur A
    if data_a and data_a['asn'] == data_b['asn']: # Seulement si lien interne (Même AS)
        int_a = format_interface(node_a['adapter_number'], node_a['port_number'])#fait un Gigabyte1/0
        if data_a['protocol'] == 'rip':
            configs[name_a] += f"interface {int_a}\n ipv6 rip {data_a['rip_process_name']} enable\n exit\n"#activation RIPng sur l'interface 
        elif data_a['protocol'] == 'ospf':
            configs[name_a] += f"interface {int_a}\n ipv6 ospf {data_a['ospf_process_id']} area 0\n exit\n"#pareil 

    # Pour Routeur B
    if data_b and data_b['asn'] == data_a['asn']: # Seulement si lien interne
        int_b = format_interface(node_b['adapter_number'], node_b['port_number'])
        if data_b['protocol'] == 'rip':
            configs[name_b] += f"interface {int_b}\n ipv6 rip {data_b['rip_process_name']} enable\n exit\n"
        elif data_b['protocol'] == 'ospf':
            configs[name_b] += f"interface {int_b}\n ipv6 ospf {data_b['ospf_process_id']} area 0\n exit\n"


print("3. Configuration BGP Avancée (Policies)...")
for r in liste_routeurs: #r = "R2" par exemple avec ses liens, vient du fichier GNS3
    data = get_router_intent(r) #rentre dans le JSON pour trouver règles décidées pour R2
    #AS, protocole, voisins ...
    if not data: continue
    
    asn = data['asn'] # numéro AS
    rid = get_id(r)
    bgp_rid = f"{rid}.{rid}.{rid}.{rid}" # BGP router-ID, 22.22.22.22 par exemple
    
    configs[r] += f"! --- BGP --- \n"
    configs[r] += f"router bgp {asn}\n" # Démarre le processus BGP avec le numéro d'AS défini dans intent.json (ex: 112).
    configs[r] += f" bgp router-id {bgp_rid}\n" # Force l'identité du routeur pour éviter l'erreur si aucune IPv4 n'est présente.
    configs[r] += f" no bgp default ipv4-unicast\n" # Désactive le mode par défaut IPv4 (car on fait un labo 100% IPv6).

    # Initialise une variable vide pour stocker les commandes 'activate' et 'route-map' qu'on injectera plus tard.
    neighbors_config = ""
    
    # 3.1 iBGP
    # Parcourt la liste des routeurs appartenant au MEME AS (définis dans intent.json).
    for neighbor in data['routers']:
        # Évite de se configurer soi-même comme voisin.
        if neighbor == r: continue
            
        n_rid = get_id(neighbor)
        n_ip = f"{data['prefix']}::{n_rid}" # Calcule l'adresse IP Loopback du voisin (Cible stable pour l'iBGP).
        
        configs[r] += f" neighbor {n_ip} remote-as {asn}\n" # Déclare le voisin. Comme l'AS est le même -> C'est une session iBGP.
        configs[r] += f" neighbor {n_ip} update-source Loopback0\n" #On force l'utilisation de notre Loopback comme source, sinon le voisin rejette la connexion.
        neighbors_config += f"  neighbor {n_ip} activate\n" # Prépare l'activation du voisin dans la famille IPv6
        neighbors_config += f"  neighbor {n_ip} next-hop-self\n" #Dit aux routeurs internes de passer par MOI pour sortir
        neighbors_config += f"  neighbor {n_ip} send-community\n" # Active l'envoi des tags (communities) pour propager les infos clients/fournisseurs en interne

    # 3.2 eBGP
    # Parcourt tous les câbles physiques du schéma GNS3 pour trouver les voisins directs
    for link in gns3_data['topology']['links']:
        # Récupération des IDs et noms des deux extrémités du câble
        # Identification de qui est "me" (moi) et "neighbor_name" (l'autre)
        node_a_id = link['nodes'][0]['node_id']
        node_b_id = link['nodes'][1]['node_id']
        name_a, name_b = nodes_map[node_a_id], nodes_map[node_b_id]
        
        me, neighbor_name = (None, None)
        if name_a == r: me, neighbor_name = name_a, name_b
        elif name_b == r: me, neighbor_name = name_b, name_a
        else: continue
            
        # Récupère les infos de l'AS du voisin dans le fichier intent.json.
        neighbor_data = get_router_intent(neighbor_name)

        # Vérifie si le voisin est dans un AS DIFFÉRENT
        if neighbor_data and neighbor_data['asn'] != asn:
            # --- CORRECTION DUPLICATA BGP ---
            # Récupère le sous-réseau global pour les liens inter-AS
            # On réutilise la meme logique que pour l'adressage IP pour eviter les duplicatas
            n_rid = get_id(neighbor_name)
            mnemo = f"{min(rid, n_rid)}:{max(rid, n_rid)}"
            subnet = f"{intent['global_options']['inter_as_subnet']}:{mnemo}::"
            
            """# Logique déterministe : Le plus petit ID prend .1, le plus grand prend .2.
            suffix = "1" if n_rid < rid else "2"
            """
            suffix = f"{n_rid}" #idem, on prend l'id en suffixe plutôt
            
            # Construit l'adresse IP physique de l'interface du voisin.
            n_ip = f"{subnet}{suffix}"

            # Récupère le type de relation (Peer, Provider, Customer) depuis intent.json
            relationship = get_link_relationship(me, neighbor_name)

            # Déclare le voisin avec son AS différent -> Session eBGP
            configs[r] += f" neighbor {n_ip} remote-as {neighbor_data['asn']}\n"

            # Génère dynamiquement les noms des Route-Maps (ex: RM-PEER-IN)
            rm_in = f"RM-{relationship.upper()}-IN"
            rm_out = f"RM-{relationship.upper()}-OUT"
            
            # Prépare l'activation IPv6
            neighbors_config += f"  neighbor {n_ip} activate\n"
            # Active l'échange de communautés standards
            neighbors_config += f"  neighbor {n_ip} send-community\n"
            # Applique le filtrage en ENTRÉE du routeur
            neighbors_config += f"  neighbor {n_ip} route-map {rm_in} in\n"
            # Applique le filtrage en SORTIE du routeur
            neighbors_config += f"  neighbor {n_ip} route-map {rm_out} out\n"

    # Entre dans le mode de configuration spécifique IPv6 de BGP
    configs[r] += " address-family ipv6 unicast\n"
    #Injecte le préfixe de l'AS dans BGP pour l'annoncer sur Internet/les autres AS, rendant ainsi l'AS joignable
    configs[r] += f"  network {data['prefix']}::/32\n"
    # Injecte tout le bloc de configuration des voisins (activations + route-maps) préparé ci-dessus
    configs[r] += neighbors_config
    configs[r] += " exit-address-family\n"
    configs[r] += " exit\n"

    # --- CORRECTION INDENTATION SECTION 3.3 ---
    # 3.3 DEFINITION DES ROUTE-MAPS (Policies)
    pols = intent['bgp_policies']#on cherche les policies dans le fichier intent
    comm_cust = pols['customer_community']
    
    configs[r] += "! --- POLICIES ---\n"
    configs[r] += f"ip community-list 1 permit {comm_cust}\n"#on definit la liste community et on l'ajoute plus tard
    
    # CUSTOMER
    configs[r] += f"route-map RM-CUSTOMER-IN permit 10\n" #création de la route map d'entrée
    configs[r] += f" set local-preference {pols['local_pref_customer']}\n"#local pref élevé puisque c'est le client
    configs[r] += f" set community {comm_cust} additive\n exit\n"#on ajoute la community list crée avant pour tag les clients
    configs[r] += f"route-map RM-CUSTOMER-OUT permit 10\n exit\n"#on l'a mise pour une eventuelle modif plus tard mais pas utile pour l'instant
    
    # PROVIDER
    configs[r] += f"route-map RM-PROVIDER-IN permit 10\n"#route map d'entree
    configs[r] += f" set local-preference {pols['local_pref_provider']}\n exit\n"#local pref faible
    configs[r] += f"route-map RM-PROVIDER-OUT permit 10\n"#route map de sortie
    configs[r] += f" match community 1\n exit\n"#en sortie on ne permet que les route allant vers nos client
    
    # PEER
    configs[r] += f"route-map RM-PEER-IN permit 10\n"#route map entree
    configs[r] += f" set local-preference {pols['local_pref_peer']}\n exit\n"#local pref mid 
    configs[r] += f"route-map RM-PEER-OUT permit 10\n"#sortie
    configs[r] += f" match community 1\n exit\n"#pareil que les providers


# --- 6. SAUVEGARDE ---
if not os.path.exists(DOSSIER_SORTIE):#si le fichier n'existe pas on le creer
    os.makedirs(DOSSIER_SORTIE)

for name, content in configs.items():
    # On ajoute 'end' pour dire au routeur que le fichier est fini
    # On ajoute 'write memory' pour ne pas tout perdre
    content += "end\n"
    content += "write memory\n"
    
    path = os.path.join(DOSSIER_SORTIE, f"{name}.cfg")#on donne l'adresse exacte
    with open(path, 'w') as f:#on regarde si le fichier pour chaque routeur existe sinon on le creer
        f.write(content)#on ecrit toute la config

    print(f"Généré : {name}.cfg")#...
