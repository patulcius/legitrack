# Veille parlementaire et institutionnelle

Site statique de veille sur le travail de l'Assemblée nationale, du Sénat et de la Cour des comptes :
agenda et délais d'amendements, textes et navette, amendements (texte intégral), scrutins et fiches élus,
questions, rapports, flux RSS. Toutes les données sont publiques (open data et pages officielles).

## Fonctionnement

- `scripts/update.sh full|light` télécharge les données et construit le site dans `_site/`.
- `.github/workflows/update.yml` lance la mise à jour automatiquement et publie le site sur GitHub Pages :
  - chaque matin à 8 h 30 (heure d'hiver), après la publication quotidienne des données de l'Assemblée et du Sénat : collecte complète, puis une seconde à 14 h pour les amendements déposés dans la journée (open data de l'Assemblée, Sénat, Cour des comptes) ;
  - toutes les heures en semaine, de 7 h à 21 h : agenda de l'Assemblée, ordre du jour du Sénat, flux RSS.
- Les données téléchargées sont gardées en cache entre deux exécutions (actions/cache), pas dans le dépôt.

## Mise en place (une seule fois)

1. Dépôt public sur GitHub (GitHub Pages gratuit), contenant ces fichiers.
2. Settings > Pages > Build and deployment > Source : **GitHub Actions**.
3. Onglet Actions > « Mise à jour de la veille » > Run workflow (mode full). La première exécution dure environ une heure (collecte complète du Sénat), les suivantes quelques minutes.

Le site est ensuite disponible à l'adresse `https://<compte>.github.io/<dépôt>/`.

## Scripts

| Fichier | Rôle |
|---|---|
| `scripts/update.sh` | orchestration (téléchargements, décompression, construction) |
| `scripts/fetch_all.py` | Sénat (dossiers, amendements, sénateurs, ordre du jour) et Cour des comptes |
| `scripts/build_v3.py` | construction des fichiers JSON du site (thématiques, délais, sous-amendements tombés, votes…) |
| `scripts/fetch_rss.py` | 54 flux RSS officiels |
| `scripts/post_build.py` | journal des nouveautés (comparaison avec la collecte précédente), flux RSS et agendas .ics |
| `scripts/lettre.py` | lettre quotidienne par e-mail (seulement si les secrets d'envoi sont configurés) |
| `site/index.html` | l'application (une seule page, sans dépendance à installer) |
| `site/equipe.json` | facultatif : profil d'équipe appliqué à la première visite (voir plus bas) |

Les préférences (thématiques, textes, parlementaires et flux suivis) sont enregistrées dans le navigateur de chaque utilisateur.

## Nouveautés, alertes et partage

- **Nouveautés** : à chaque collecte, `post_build.py` compare les données à celles de la collecte précédente
  (instantané gardé dans `data/etat/`) et publie `changes.json` (trois semaines d'historique). Le site affiche
  un badge, un bandeau « depuis votre dernière visite » et une page Nouveautés filtrable.
- **Flux RSS** : `feeds/tout.xml`, `feeds/<thématique>.xml` et `feeds/t/<texte>.xml`.
- **Agendas .ics** : `ics/tout.ics`, `ics/<thématique>.ics` et `ics/t/<texte>.ics`, abonnables dans Outlook
  (« Ajouter un calendrier », puis « À partir d'Internet »).
- **Partage** : le bouton de partage du site copie un lien ou enregistre un fichier contenant la sélection
  (thématiques, textes, parlementaires, flux). Rien n'est stocké sur un serveur.
- **Profil d'équipe** : un fichier `site/equipe.json` facultatif, par exemple
  `{"nom": "Pôle sécurité", "th": ["securite", "justice"], "tx": [], "el": [], "fx": []}`,
  est appliqué automatiquement à la première visite de chaque membre, et reste proposé ensuite.
- **Lettre par e-mail** : secrets `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`, `LETTRE_FROM` et
  `LETTRE_DEST` (par exemple `alice@exemple.fr:securite,justice; equipe@exemple.fr:*`). Les adresses restent
  dans les secrets du dépôt et n'apparaissent jamais sur le site.
