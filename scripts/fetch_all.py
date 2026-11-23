#!/usr/bin/env python3
"""Collecte globale : Sénat (tous les dossiers depuis oct. 2024 + ceux liés à l'AN), sénateurs, Cour des comptes.
Usage : python3 fetch_all.py <dossier_senat> <dossier_ccomptes> <dossier_raw_AN>
"""
import glob, json, os, re, sys, time, urllib.request
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from senat_common import read_csv, fr_date, norm_url, SINCE
SEN, CC, RAW = sys.argv[1:4]
for d in (f"{SEN}/dossiers", f"{SEN}/amdt", CC): os.makedirs(d, exist_ok=True)

def get(url, dest, tries=3, force=False):
    if not force and os.path.exists(dest) and os.path.getsize(dest) > 0: return True
    err = None
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"Accept-Encoding": "identity"}), timeout=180) as r:
                b = r.read()
            open(dest, "wb").write(b); time.sleep(0.15); return True
        except Exception as e:
            err = e; time.sleep(2 * (i + 1))
    print("échec", url, err, file=sys.stderr, flush=True); return False

for f in ["dosleg/dossiers-legislatifs.csv", "dosleg/rapports.csv", "dosleg/ppl.csv", "questions/questions-depuis-un-an.csv"]:
    get(f"https://data.senat.fr/data/{f}", f"{SEN}/{os.path.basename(f)}", force=True)
get("https://www.senat.fr/ordre-du-jour/ordre-du-jour.html", f"{SEN}/odj.html", force=True)
get("https://www.senat.fr/api-senat/senateurs.json", f"{SEN}/senateurs.json", force=True)

# Cour des comptes : pages de publications jusqu'à oct. 2024
for p in range(0, 600):
    dest = f"{CC}/p{p:03d}.html"
    if not get(f"https://www.ccomptes.fr/fr/publications?page={p}", dest, force=p < 3): break
    dates = re.findall(r'datetime="(\d{4}-\d{2}-\d{2})', open(dest, encoding="utf-8", errors="replace").read())
    if not dates or min(dates) < SINCE.isoformat(): break
print("Cour des comptes :", p + 1, "pages", flush=True)

urls = set()
for r in read_csv(f"{SEN}/dossiers-legislatifs.csv"):
    d = fr_date(r.get("Date initiale"))
    if (d and d >= SINCE) or (r.get("État du dossier") or "").startswith(("Première", "Deuxième", "Nouvelle", "Commission mixte")):
        if d and d >= SINCE: urls.add(norm_url(r["URL du dossier"]))
for f in glob.glob(f"{RAW}/dossiers/json/dossierParlementaire/*.json"):
    j = json.load(open(f, encoding="utf-8"))["dossierParlementaire"]
    if j.get("legislature") == "17" and j["titreDossier"].get("senatChemin"):
        urls.add(norm_url(j["titreDossier"]["senatChemin"]))
print("Sénat :", len(urls), "dossiers", flush=True)
n = 0
# Rafraîchissement : les dossiers encore en navette sont retéléchargés si la copie locale a plus de REFRESH_HOURS heures
REFRESH_H = float(os.environ.get("REFRESH_HOURS", "0"))
etat = {norm_url(r["URL du dossier"]): (r.get("État du dossier") or "").lower() for r in read_csv(f"{SEN}/dossiers-legislatifs.csv")}
FINAL = ("promulgu", "caduc", "rejet", "retir", "non adopt")
def stale(path, u):
    if not REFRESH_H or not os.path.exists(path): return False
    if any(w in etat.get(u, "") for w in FINAL): return False
    return (time.time() - os.path.getmtime(path)) > REFRESH_H * 3600
for i, u in enumerate(sorted(urls)):
    slug = u.rsplit("/", 1)[-1].replace(".html", "")
    page = f"{SEN}/dossiers/{slug}.html"
    if not get(u, page, force=stale(page, u)): continue
    html = open(page, encoding="utf-8", errors="replace").read()
    for kind, sess, num in set(re.findall(r'/amendements/(commissions/)?(\d{4}-\d{4})/(\d+)/', html)):
        if kind: name = f"jeu_complet_commission_{sess}_{num}.csv"; url = f"https://www.senat.fr/amendements/commissions/{sess}/{num}/{name}"
        else: name = f"jeu_complet_{sess}_{num}.csv"; url = f"https://www.senat.fr/amendements/{sess}/{num}/{name}"
        dest = f"{SEN}/amdt/{slug}__{name}"
        if get(url, dest, force=stale(dest, u)): n += 1
    if i % 50 == 0: print(i, "dossiers", n, "fichiers amdt", flush=True)
print("FIN", len(urls), "dossiers,", n, "fichiers d'amendements", flush=True)
