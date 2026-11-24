# Comptes et alertes e-mail

Le site reste statique (GitHub Pages) et consultable sans compte. Les comptes s'appuient sur
Supabase (projet « Legitrack », région UE eu-west-1) et les e-mails sur Brevo.

- `schema.sql` : tables `profils`, `alertes`, `envois`, `admins_autorises`, règles RLS et
  fonctions d'administration. Toute inscription crée un profil « en attente » ; seul un
  administrateur peut le valider (page `#admin` du site). Un compte non validé ne peut ni
  enregistrer de préférences ni créer d'alerte.
- `agenda_perso.sql` : à exécuter une fois dans l'éditeur SQL (déjà inclus dans `schema.sql` pour une
  nouvelle installation). Ajoute à chaque profil un jeton `agenda_jeton` et la fonction
  `nouveau_jeton_agenda()` ; `scripts/agendas_perso.py` publie alors `ics/u/<jeton>.ics` pour chaque compte validé.
- `scripts/alertes.py` : lancé après chaque collecte par `update.sh`. Prévient les
  administrateurs des demandes, prévient les demandeurs de la décision, envoie les alertes
  (dès la collecte ou en récapitulatif quotidien après 8 h) via l'API Brevo.

## Configuration

GitHub (Settings > Secrets and variables > Actions) :

| Nom | Type | Valeur |
| --- | --- | --- |
| `SUPABASE_URL` | variable | `https://ihkcwhzamieintzhqpki.supabase.co` |
| `SUPABASE_SERVICE_ROLE_KEY` | secret | clé secrète du projet (Supabase > Project Settings > API Keys) |
| `BREVO_API_KEY` | secret | clé d'API Brevo (SMTP & API > API Keys) |
| `ALERTES_FROM` | secret | expéditeur validé dans Brevo, par exemple `Legitrack <alertes@exemple.fr>` |

Supabase (Authentication) :

- URL Configuration : Site URL `https://patulcius.github.io/legitrack/`, Redirect URLs
  `https://patulcius.github.io/legitrack/**`.
- SMTP Settings (obligatoire : l'envoi intégré de Supabase ne sert que l'équipe du projet) :
  hôte `smtp-relay.brevo.com`, port `587`, identifiant SMTP Brevo, mot de passe = clé SMTP
  Brevo, expéditeur identique à `ALERTES_FROM`.
- Email Templates : modèles en français ci-dessous.

Ajouter un administrateur : `insert into public.admins_autorises(email) values ('…');` avant son
inscription, ou bouton « Rendre administrateur » sur la page `#admin`.

### Modèle « Confirm signup »

Objet : `Legitrack · confirmez votre adresse`

```html
<p>Bonjour,</p>
<p>Vous avez demandé un compte Legitrack. Confirmez votre adresse e-mail :</p>
<p><a href="{{ .ConfirmationURL }}">Confirmer mon adresse</a></p>
<p>L'administrateur validera ensuite votre compte ; vous recevrez un e-mail à ce moment-là.</p>
<p>Si vous n'êtes pas à l'origine de cette demande, ignorez ce message.</p>
```

### Modèle « Reset password »

Objet : `Legitrack · nouveau mot de passe`

```html
<p>Bonjour,</p>
<p>Pour choisir un nouveau mot de passe Legitrack, ouvrez ce lien dans le navigateur où vous avez fait la demande :</p>
<p><a href="{{ .ConfirmationURL }}">Choisir un nouveau mot de passe</a></p>
<p>Si vous n'êtes pas à l'origine de cette demande, ignorez ce message.</p>
```
