# Documentation du Projet Auto_GNS3

Ce projet automatise la génération de configurations réseau IPv6 pour une topologie GNS3, incluant le routage IGP (RIP/OSPF) et BGP.

## 1. Plan d'Adressage IPv6

L'adressage est généré automatiquement en fonction du numéro d'AS et des identifiants (ID) des routeurs.

| Type de lien | Format | Exemple (R1 ↔ R2) | Notes |
| :--- | :--- | :--- | :--- |
| **Intra-AS** | `2001:<ASN>:<ID1>:<ID2>::<ID>/64` | `2001:100:1:2::1` | Lien interne à l'AS |
| **Inter-AS** | `2001:FFFF:<ID1>:<ID2>::<ID>/64` | `2001:FFFF:1:2::1` | Lien d'interconnexion (Peering/Transit) |
| **Loopback** | `2001:<ASN>::<ID>/128` | `2001:100::1` | ID BGP et Management |

> **Note :** Le champ `mgmt_loopback_prefix` (ex: BAD:CAFE) présent dans le fichier JSON n'est pas utilisé dans cette version du script. Il est conservé pour une éventuelle implémentation future de multi-adressage (Service vs Management).

## 2. Politiques BGP (Policies)

Le routage BGP applique des politiques de filtrage et de priorisation basées sur les relations entre voisins (Client, Peer, Provider).

### Communities
Les routes sont taguées à l'entrée pour identifier leur source.
* Format : `XX:ASN` (où XX est le type de relation).
* **10:100** : Route apprise d'un **Client**.
* *(20:ASN et 30:ASN pour Peer/Provider non implémentés car le filtrage sortant bloque tout sauf les routes clients).*

### Local Preference
Valeurs appliquées pour influencer le trafic sortant (conformément au sujet de TP) :

| Relation | Local Preference | Priorité |
| :--- | :--- | :--- |
| **Provider** | 200 | Haute |
| **Peer** | 100 | Moyenne |
| **Customer** | 50 | Basse |
