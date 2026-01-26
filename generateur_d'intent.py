

import json
import os
import re

# fonction utilitaire qui retourne une liste de routeurs "R{i}" à partir d'une range de routeur comme par exemple 1-6
def parse_router_list(input_str):
    """
    Transforme une chaîne de caractères (ex: "1-3, 5, R6") en une liste 
    triée de noms de routeurs (ex: ["R1", "R2", "R3", "R5", "R6"]).
    """
    routers = []
    
    # on supprime les espaces et on découpe par virgule pour isoler chaque bloc
    parts = input_str.replace(" ", "").split(",")
    
    for part in parts:
        if "-" in part:
            try:
                # on sépare le début et la fin, on convertit en entiers
                start, end = map(int, part.split("-"))
                # on génère chaque routeur dans l'intervalle avec le préfixe "R"
                for i in range(start, end + 1):
                    routers.append(f"R{i}")
            except ValueError:
                # petite sécurité si l'utilisateur tape n'importe quoi (ex: "1-abc")
                print(f"Format incorrect ignoré : {part}")
        
        else:
            # on nettoie pour ne garder que le chiffre de "r5" ou "R5"
            clean_part = part.upper().replace("R", "")
            if clean_part.isdigit():
                routers.append(f"R{clean_part}")
    
    # on trie la liste par numéro de routeur 
    # le lambda permet de trier numériquement sur le chiffre après le 'R' (ex: R10 après R2)
    routers.sort(key=lambda x: int(x[1:]))
    
    return routers


print("=== GÉNÉRATEUR D'INTENTION RÉSEAU (JSON) ===")

intent = {
    "project_name": input("Nom du projet (ex: Projet_Auto_GNS3) : ") or "Projet_Auto_GNS3",#on demande le nom du projet
    "global_options": {
        "inter_as_subnet": input("Sous-réseau Inter-AS (Défaut: 2001:FFFF) : ") or "2001:FFFF",#ici le prefixe du sous réseau
        "mgmt_loopback_prefix": input("Préfixe Loopback Mgmt (Défaut: 2001:BAD:CAFE) : ") or "2001:BAD:CAFE"#prefixe loopback
    },
    "as_list": [],
    "bgp_policies": {},#une liste pour les règles politiques qu'on veut en BGP
    "external_relationships": [],#une liste pourles relations entre AS
    "ospf_custom_metrics": []  #une liste pour stocker les métriques en OSPF
}

# Configuration des AS
print("\n--- CONFIGURATION DES AS ---")
while True:
    print(f"\nAjout d'un nouvel AS (Tapez 'q' pour arrêter)")
    asn = input("Numéro d'AS (ASN) : ")#un num d'AS
    if asn.lower() == 'q':#on pourra taper q pour arrêter à chaque fois
        break
    prefix = input(f"Préfixe de l'AS {asn} (ex: 2001:{asn}) : ")#un prefixe...
    
    while True:
        proto = input("Protocole IGP (rip / ospf) : ").lower()
        if proto in ["rip", "ospf"]:#choix entre les deux IGP
            break
        print("Erreur: choisir 'rip' ou 'ospf'.")

    r_input = input("Liste des routeurs (ex: '1-3') : ")#on demande une range de routeurs
    routers = parse_router_list(r_input)#on utilise la fonction pour avoir une liste de routeurs
    
    as_obj = {    #pour chaque AS on aura un dico qui stock ses "caracteristiques"
        "asn": asn,  #numero d'AS
        "prefix": prefix, 
        "protocol": proto,
        "routers": routers
    }

    if proto == "rip":#on demande un nom pour le processus RIP
        as_obj["rip_process_name"] = input("Nom du processus RIP (Défaut: PROC_RIP) : ") or "PROC_RIP"
    elif proto == "ospf": #pareil pour OSPF
        as_obj["ospf_process_id"] = input("ID du processus OSPF (Défaut: 1) : ") or "1"

    intent["as_list"].append(as_obj)#on ajoute dans la liste des AS le dico de l'AS

# Politiques BGP
print("\n--- POLITIQUES BGP (COMMUNITIES & PREFS) ---")
intent["bgp_policies"] = { #un dico pour les politiques
    "customer_community": input("Community Client (Défaut: [numéro d'as]:10) : ") or "100:10",#on demande une community list
    "local_pref_customer": int(input("Local Pref Client (Défaut: 200) : ") or 200),#pareil pour les locals prefs clients
    "local_pref_peer": int(input("Local Pref Peer (Défaut: 100) : ") or 100),#peer
    "local_pref_provider": int(input("Local Pref Provider (Défaut: 50) : ") or 50)#provider
}#on peut améliorer cela en demandant des modifs d'AS_PATH ou autres...

# eBGP
print("\n--- RELATIONS EXTERNES (PEERING/TRANSIT) ---")
while True:
    print("\nAjout d'une relation eBGP (Tapez 'q' pour arrêter)")
    r_src = input("Routeur Source (ex: R3) : ")#on choisit un routeur de référence
    if r_src.lower() == 'q':
        break
    r_dst = input("Routeur Destination (ex: R4) : ")# et un autre 
    
    print("Type de relation : 1. peer, 2. customer, 3. provider")#on choisit une relation dans le sens R referent vers l'autre
    rel_choice = input("Choix (1/2/3) : ")
    
    relationship = "peer"   #par defaut c'est un peering
    if rel_choice == "2": relationship = "customer"#sinon le routeur referent est le client
    elif rel_choice == "3": relationship = "provider"# ou sinon le provider

    intent["external_relationships"].append({  # on ajoute dans le dico final un dico qui a pour clé external_relationships et valeur :
        "nodes": [r_src, r_dst],#une liste des deux routeurs de la relation dans le sens referent -> autre routeur
        "relationship": relationship# le type de relation
    })

# métriques OSPF
print("\n--- METRIQUES OSPF (Custom Costs) ---")
print("Permet de forcer le coût OSPF sur des liens spécifiques (ex: R1-R2 cost 50).")
while True:
    print("\nAjouter un coût manuel ? (Tapez 'q' pour arrêter)")
    r_a = input("Routeur A (ex: R1) : ")#on demande un routeur de départ
    if r_a.lower() == 'q':
        break
    r_b = input("Routeur B (ex: R2) : ")# et d'arrivée
    cost = input("Coût OSPF (ex: 100) : ")# et enfin un coût entre les deux
    
    if cost.isdigit():
        intent["ospf_custom_metrics"].append({ # on ajoute comme précédemment le tout
            "nodes": [r_a, r_b],
            "cost": int(cost)
        })
        print(f" -> Coût OSPF {cost} défini entre {r_a} et {r_b}")
    else:
        print("Erreur : Le coût doit être un nombre.")

# Sauvegarde
output_file = "intent.json"
with open(output_file, 'w') as f:
    json.dump(intent, f, indent=4)

print(f"\nSUCCÈS ! Le fichier '{output_file}' a été généré avec les options OSPF.")
