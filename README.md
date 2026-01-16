
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
200 -> provider
100 -> peer
50 -> customer
(comme en TP)
