# Legitrack

Veille parlementaire et institutionnelle.

Site statique de veille sur le travail de l'Assemblée nationale, du Sénat et de la Cour des comptes :
agenda et délais d'amendements, textes et navette, amendements (texte intégral), scrutins et fiches élus,
questions, rapports, missions d'information et commissions d'enquête (composition, auditions, comptes rendus, rapports), flux RSS. Toutes les données sont publiques (open data et pages officielles).

## Fonctionnement

- `scripts/update.sh full|light` télécharge les données et construit le site dans `_site/`.
- `.github/workflows/update.yml` lance la mise à jour automatiquement et publie le site sur GitHub Pages :
  - chaque matin à 8 h 30 (heure d'hiver), après la publication quotidienne des données de l'Assemblée et du Sénat : collecte complète, puis une seconde à 14 h pour les amendements déposés dans la journée (open data de l'Assemblée, Sénat, Cour des comptes) ;
  - toutes les heures en semaine, de 7 h à 21 h : agenda de l'Assemblée, ordre du jour du Sénat, flux RSS.
- Les données téléchargées sont gardées en cache entre deux exécutions (actions/cache), pas dans le dépôt.

## Mise en place (une seule fois)

1. Dépôt public sur GitHub (GitHub Pages gratuit), contenant ces fichiers.
2. Settings > Pages > Build and deployment > Source : **GitHub Actions**.
3. Onglet Actions > « Mise à jour de Legitrack » > Run workflow (mode full). La première exécution dure environ une heure (collecte complète du Sénat), les suivantes quelques minutes.

Le site est ensuite disponible à l'adresse `https://<compte>.github.io/<dépôt>/`.

## Scripts

| Fichier | Rôle |
|---|---|
| `scripts/update.sh` | orchestration (téléchargements, décompression, construction) |
| `scripts/fetch_all.py` | Sénat (dossiers, amendements, sénateurs, ordre du jour) et Cour des comptes |
| `scripts/build_v3.py` | construction des fichiers JSON du site (thématiques, délais, sous-amendements tombés, votes…) |
| `scripts/fetch_rss.py` | 54 flux RSS officiels |
| `scripts/post_build.py` | journal des nouveautés (comparaison avec la collecte précédente), flux RSS et agendas .ics |
| `scripts/agendas_perso.py` | agendas .ics personnels des comptes (`ics/u/<jeton>.ics`, textes et missions suivis) |
| `scripts/lettre.py` | lettre quotidienne par e-mail (seulement si les secrets d'envoi sont configurés) |
| `site/index.html` | l'application (une seule page, sans dépendance à installer) |
| `site/equipe.json` | facultatif : profil d'équipe appliqué à la première visite (voir plus bas) |

Les préférences (thématiques, textes, parlementaires et flux suivis) sont enregistrées dans le navigateur de chaque utilisateur.

## Organisation du site

- **Pour moi** : *Mon fil* (accueil personnel, sans compte : délais d'amendements des textes suivis regroupés par
  texte, semaine à venir, nouveautés sur les suivis, cartes des suivis, découvertes dans les thématiques choisies),
  *Nouveautés*, *Mon agenda* et *Mes suivis* (onglets textes, missions, parlementaires, thématiques, avec alertes,
  agendas et flux). Sans aucun suivi, Mon fil propose un démarrage en trois étapes.
- **Explorer** : *Vue d'ensemble* (l'ancien accueil, tout le Parlement), agenda parlementaire, textes, *Contrôle*
  (missions et enquêtes, rapports parlementaires, Cour des comptes), questions, élus.
- Un seul bouton **Suivre** sur chaque texte, mission ou parlementaire ; une fois suivi, il ouvre un panneau
  (Mon fil, alerte e-mail, agenda Outlook, flux RSS). Les listes ont un interrupteur commun « Pour moi · Tout ».
- Sur téléphone : barre de navigation en bas (Mon fil, Agenda, Rechercher, Nouveautés, Plus).

## Nouveautés, alertes et partage

- **Nouveautés** : à chaque collecte, `post_build.py` compare les données à celles de la collecte précédente
  (instantané gardé dans `data/etat/`) et publie `changes.json` (trois semaines d'historique). Le site affiche
  un badge, un bandeau « depuis votre dernière visite » et une page Nouveautés filtrable.
- **Flux RSS** : `feeds/tout.xml`, `feeds/<thématique>.xml` et `feeds/t/<texte>.xml`.
- **Agendas .ics** : `ics/tout.ics`, `ics/<thématique>.ics` et `ics/t/<texte>.ics`, abonnables dans Outlook
  (« Ajouter un calendrier », puis « À partir d'Internet »).
- **Agenda personnel** : chaque compte validé dispose d'une adresse privée non devinable `ics/u/<jeton>.ics`,
  régénérée à chaque collecte avec ses textes et missions suivis (`supabase/agenda_perso.sql`, une seule fois).
  L'adresse peut être changée depuis Mes suivis ; sans compte, l'agenda des suivis se télécharge en .ics.
- **Partage** : le bouton de partage du site copie un lien ou enregistre un fichier contenant la sélection
  (thématiques, textes, parlementaires, flux). Rien n'est stocké sur un serveur.
- **Profil d'équipe** : un fichier `site/equipe.json` facultatif, par exemple
  `{"nom": "Pôle sécurité", "th": ["securite", "justice"], "tx": [], "el": [], "fx": []}`,
  est appliqué automatiquement à la première visite de chaque membre, et reste proposé ensuite.
- **Lettre par e-mail** : secrets `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`, `LETTRE_FROM` et
  `LETTRE_DEST` (par exemple `alice@exemple.fr:securite,justice; equipe@exemple.fr:*`). Les adresses restent
  dans les secrets du dépôt et n'apparaissent jamais sur le site.

## Comptes et alertes e-mail

Comptes validés par un administrateur, préférences synchronisées et alertes e-mail sur mesure (missions, textes, thématiques) : voir [supabase/README.md](supabase/README.md).
