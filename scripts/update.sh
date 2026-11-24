#!/usr/bin/env bash
# Mise à jour de la veille : télécharge les données, construit le site dans _site/
# Usage : scripts/update.sh full|light
#   full  : toutes les sources (chaque nuit)
#   light : agenda AN, ordre du jour du Sénat, flux RSS (toutes les heures) ; repasse en full si le cache est vide
set -euo pipefail
MODE="${1:-full}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DATA="$ROOT/data"; RAW="$ROOT/work/raw"; OUT="$ROOT/_site"
B="https://data.assemblee-nationale.fr/static/openData/repository/17"
mkdir -p "$DATA/an" "$DATA/senat" "$DATA/ccomptes" "$RAW" "$OUT"

declare -A AN_ZIPS=(
  [dossiers]="$B/loi/dossiers_legislatifs/Dossiers_Legislatifs.json.zip"
  [agenda]="$B/vp/reunions/Agenda.json.zip"
  [qe]="$B/questions/questions_ecrites/Questions_ecrites.json.zip"
  [qosd]="$B/questions/questions_orales_sans_debat/Questions_orales_sans_debat.json.zip"
  [qag]="$B/questions/questions_gouvernement/Questions_gouvernement.json.zip"
  [amo10]="$B/amo/deputes_actifs_mandats_actifs_organes/AMO10_deputes_actifs_mandats_actifs_organes.json.zip"
  [organes]="$B/amo/tous_acteurs_mandats_organes_xi_legislature/AMO30_tous_acteurs_tous_mandats_tous_organes_historique.json.zip"
  [scrutins]="$B/loi/scrutins/Scrutins.json.zip"
  [amendements]="$B/loi/amendements_div_legis/Amendements.json.zip"
)

dl() { # téléchargement robuste d'une archive (reprise si coupure, contrôle d'intégrité)
  local name="$1" url="$2" dest="$DATA/an/$1.zip" tmp="$DATA/an/$1.part"
  rm -f "$tmp"
  for i in 1 2 3 4 5 6; do
    curl -sSL --retry 3 --max-time 900 -C - -o "$tmp" "$url" || true
    if unzip -tq "$tmp" >/dev/null 2>&1; then mv "$tmp" "$dest"; echo "OK $name"; return 0; fi
    sleep $((i * 5))
  done
  echo "Échec du téléchargement de $name, on garde la version précédente" >&2; rm -f "$tmp"
}

if [ "$MODE" = "light" ]; then
  for n in "${!AN_ZIPS[@]}"; do [ -f "$DATA/an/$n.zip" ] || { echo "Cache vide : passage en mode full"; MODE=full; break; }; done
fi

if [ "$MODE" = "full" ]; then
  for n in "${!AN_ZIPS[@]}"; do dl "$n" "${AN_ZIPS[$n]}"; done
else
  dl agenda "${AN_ZIPS[agenda]}"
  curl -sSL --retry 3 -o "$DATA/senat/odj.html.part" https://www.senat.fr/ordre-du-jour/ordre-du-jour.html && mv "$DATA/senat/odj.html.part" "$DATA/senat/odj.html"
fi

# Décompression (hors amendements, lus directement dans le zip)
for n in dossiers agenda qe qosd qag amo10 organes scrutins; do
  rm -rf "${RAW:?}/$n"; mkdir -p "$RAW/$n"; unzip -q -o "$DATA/an/$n.zip" -d "$RAW/$n"
done
ln -sf "$DATA/an/amendements.zip" "$RAW/amendements.zip"

if [ "$MODE" = "full" ]; then
  REFRESH_HOURS=20 python3 -I "$ROOT/scripts/fetch_all.py" "$DATA/senat" "$DATA/ccomptes" "$RAW" || echo "Collecte Sénat / Cour des comptes incomplète" >&2
fi

python3 -I "$ROOT/scripts/build_v3.py" "$RAW" "$DATA/senat" "$DATA/ccomptes" "$OUT"
python3 -I "$ROOT/scripts/fetch_rss.py" "$OUT/rss.json" || echo "Flux RSS indisponibles" >&2
cp -r "$ROOT/site/." "$OUT/"
# Journal des nouveautés, flux RSS par thématique, calendriers .ics (état conservé dans le cache)
if [ -f "$ROOT/scripts/post_build.py" ]; then
  python3 -I "$ROOT/scripts/post_build.py" "$OUT" "$DATA/etat" || echo "Journal des nouveautés indisponible" >&2
fi
# Agendas Outlook personnels des comptes (ics/u/<jeton>.ics) ; ne fait rien sans les secrets
if [ -f "$ROOT/scripts/agendas_perso.py" ]; then
  python3 -I "$ROOT/scripts/agendas_perso.py" "$OUT" || echo "Agendas personnels non écrits" >&2
fi
# Alertes e-mail personnalisées (comptes) : à chaque collecte ; ne fait rien sans les secrets
if [ -f "$ROOT/scripts/alertes.py" ]; then
  python3 -I "$ROOT/scripts/alertes.py" "$OUT" || echo "Alertes e-mail non envoyées" >&2
fi
# Lettre e-mail : une fois par jour, avec la collecte complète du matin
if [ "$MODE" = "full" ] && [ "$(TZ=Europe/Paris date +%H)" -lt 12 ] && [ -f "$ROOT/scripts/lettre.py" ]; then
  python3 -I "$ROOT/scripts/lettre.py" "$OUT" "$DATA/etat" || true
fi
touch "$OUT/.nojekyll"
echo "Site construit ($MODE) : $(du -sh "$OUT" | cut -f1)"
