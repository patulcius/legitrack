#!/usr/bin/env python3
"""Agendas Outlook personnels des comptes Legitrack.

Usage : agendas_perso.py <dossier du site>

Après post_build.py, écrit pour chaque compte validé un fichier ics/u/<jeton>.ics qui regroupe
les délais d'amendements, séances, commissions et réunions de ses textes et missions suivis
(préférences enregistrées dans le compte). Le jeton (colonne profils.agenda_jeton) rend l'adresse
non devinable ; l'utilisateur peut le changer depuis la page Mes suivis.

Ne fait rien si SUPABASE_URL ou SUPABASE_SERVICE_ROLE_KEY manquent, ou si la colonne n'existe pas
encore (supabase/agenda_perso.sql non appliqué).
"""
import os
import re
import sys
import urllib.error
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from post_build import PARIS, ics, load, site_url, write  # noqa: E402
from alertes import Supa  # noqa: E402

JETON = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


def main(site):
    url, key = os.environ.get("SUPABASE_URL", ""), os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if not url or not key:
        print("Agendas personnels : configuration Supabase absente, rien à faire")
        return
    db = Supa(url, key)
    try:
        profils = db.all("profils?select=id,prefs,agenda_jeton&statut=eq.valide")
    except urllib.error.HTTPError as e:
        print(f"Agendas personnels : lecture impossible ({e.code}) ; supabase/agenda_perso.sql est-il appliqué ?")
        return
    base = site_url()
    now = datetime.now(PARIS)
    since = (now - timedelta(days=30)).date().isoformat()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    core = load(os.path.join(site, "core.json"), {}) or {}
    dossiers = {d["id"]: d for d in core.get("dossiers", [])}
    ag = [e for e in load(os.path.join(site, "agenda.json"), []) or [] if (e.get("d") or "")[:10] >= since]
    ctl = {m["id"]: m for m in (load(os.path.join(site, "controle.json"), {}) or {}).get("items", [])}
    n = 0
    for p in profils:
        j = str(p.get("agenda_jeton") or "")
        if not JETON.match(j):
            continue
        pr = p.get("prefs") or {}
        tx, mi = set(pr.get("tx") or []), set(pr.get("mi") or [])
        L = [e for e in ag if e.get("ds") in tx or e.get("mi") in mi]
        seen = {(e["d"][:16], e.get("mi")) for e in L}
        for mid in mi:  # réunions des missions absentes de l'agenda général (Sénat notamment)
            m = ctl.get(mid)
            if not m:
                continue
            for e in m.get("ev", []):
                if e.get("k") == "cr" or e.get("x") or (e.get("d") or "")[:10] < since or (e["d"][:16], mid) in seen:
                    continue
                L.append({"d": e["d"], "k": "audition" if e.get("k") == "audition" else "reunion", "t": e.get("t", ""),
                          "org": (m.get("court") or m.get("t", ""))[:160], "ch": m.get("ch", "AN"), "mi": mid})
        L.sort(key=lambda e: e["d"])
        write(os.path.join(site, "ics", "u", f"{j}.ics"), ics("Legitrack · mes suivis", L, dossiers, base, stamp))
        n += 1
    print(f"Agendas personnels : {n} écrits")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    try:
        main(sys.argv[1])
    except Exception as e:  # ne jamais bloquer la publication du site
        print(f"Agendas personnels non écrits : {e}")
