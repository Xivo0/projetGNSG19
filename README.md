
Comment se passe l'adressage ?

ici, pour une liaison intra-as entre R1 et R2, on a (sur R1):
2001:numeroAS:1:2::1/64

pour la loopback
2001:numeroAS::1/128

pour une liaison inter-AS:
2001:FFFF:1:2::1/64

la ligne dans le .json de génération de l'adresse de loopback ne sert à rien; elle est là au cas ou on aurait eu besoin de plusieurs adresses de loopback pour une implémentation.

BGP Policies : 
les valeurs pour l'instant :

pour les communities :
10:100 -> 10 pour le customer, 100 pour le numéro d'AS (20 pour un peer, 30 pour un provider, mais on a pas implémenté parce que on envoit que nos routes aux clients)

pour les local pref :
200 -> customer
100 -> peer
50 -> provider
(comme en TP)



Ce que fait le code avec les BGP Policies pour l'instant : créée des community-lists pours les customers avec un permit 10:100, met des local prefs dans les route-maps fait matcher les communities dans les route-maps des providers et peers pour ne leur annoncer que les clients.

Utilisation de L'EEM : l'embedded event manager est un outil cisco qui permet d'appliquer des commandes liées au temps sur cisco entre autre. Ici, il est utilisé pour résoudre un problème de no shutdown automatique sur les routeurs lié à une lecture des configs par le routeur avant que celui ci soit chargé complètement dans GNS3.
