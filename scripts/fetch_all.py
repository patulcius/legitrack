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

# Contrôle : commissions d'enquête et missions d'information communes du Sénat (fiche, comptes rendus)
CTL = f"{SEN}/controle"; os.makedirs(CTL, exist_ok=True)
ST = "https://www.senat.fr/travaux-parlementaires/structures-temporaires"
MOISC = {"janv": 1, "févr": 2, "mars": 3, "avr": 4, "mai": 5, "juin": 6, "juil": 7, "août": 8, "sept": 9, "oct": 10, "nov": 11, "déc": 12}
pages = []
for kind, lst in (("CE", "commissions-denquete/liste-des-commissions-denquete"), ("MIC", "missions-dinformation-communes/liste-des-missions-dinformation-communes")):
    dest = f"{CTL}/liste_{kind}.html"
    if not get(f"{ST}/{lst}.html", dest, force=True): continue
    h = open(dest, encoding="utf-8", errors="replace").read()
    for m in re.finditer(r'<a[^>]+href="((?:https://www\.senat\.fr)?/travaux-parlementaires/structures-temporaires/[^"#]+\.html)"[^>]*>.*?</a>(.{0,600})', h, re.S):
        u, after = m.group(1), m.group(2)
        if "/liste-des-" in u or "/archives/" in u or "/page/" in u or not re.search(r"/structures-temporaires/(commissions-denquete|missions-dinformation-communes)/[^/]+\.html$", u): continue
        dm = re.search(r"(\d{1,2})\s+(janv|févr|mars|avr|mai|juin|juil|août|sept|oct|nov|déc)\.?\s+(20\d\d)", re.sub(r"<[^>]+>", " ", after))
        if dm and int(dm.group(3)) * 100 + MOISC[dm.group(2)] < 202409: continue
        u = u if u.startswith("http") else "https://www.senat.fr" + u
        if u not in [p[1] for p in pages]: pages.append((kind, u))
ctl_index = []
for kind, u in pages:
    slug = u.rsplit("/", 1)[-1].replace(".html", "")
    dest = f"{CTL}/{slug}.html"
    if not get(u, dest, force=True): continue
    h = open(dest, encoding="utf-8", errors="replace").read()
    cr = re.search(r'href="(?:https?://www\.senat\.fr)?(/compte-rendu-commissions/[^"/]+\.html)"', h)
    if cr: get("https://www.senat.fr" + cr.group(1), f"{CTL}/{slug}__cr.html", force=True)
    ctl_index.append({"kind": kind, "url": u, "slug": slug})
json.dump(ctl_index, open(f"{CTL}/index.json", "w"), ensure_ascii=False)
print("Sénat contrôle :", len(ctl_index), "structures", flush=True)

# Programme de contrôle du Sénat (missions d'information des commissions, délégations, office) et pages de chaque mission
import html as _H
from urllib.parse import urljoin as _UJ
prog = []
for sess in (2025, 2026):
    dest = f"{CTL}/programme_{sess}.html"
    if not get(f"https://www.senat.fr/controle/{sess}/organismes.html", dest, force=True): continue
    h = open(dest, encoding="utf-8", errors="replace").read()
    parts = re.split(r'id="tab-([A-Z]+)"', h)
    for k in range(1, len(parts), 2):
        tab, body = parts[k], parts[k + 1]
        if tab == "INIT": continue  # commissions d'enquête et missions communes : déjà suivies
        hm = re.search(r"<caption[^>]*>(.*?)</caption>", body[:900], re.S)
        struct = re.sub(r"\s+", " ", _H.unescape(re.sub(r"<[^>]+>", "", hm.group(1)))).strip() if hm else tab
        for c1, c2, c3 in re.findall(r"<tr><td>(.*?)</td><td>(.*?)</td><td>(.*?)</td></tr>", body, re.S):
            a = re.search(r'<a[^>]+href="([^"]+)"', c1)
            url = a.group(1) if a else None
            if url: url = _UJ(f"https://www.senat.fr/controle/{sess}/organismes.html", _H.unescape(url))
            title = re.sub(r"\s+", " ", _H.unescape(re.sub(r"<[^>]+>", "", c1))).strip()
            rap = [{"url": u if u.startswith("http") else "https://www.senat.fr" + u, "t": re.sub(r"\s+", " ", _H.unescape(re.sub(r"<[^>]+>", "", t))).strip()}
                   for u, t in re.findall(r'<a[^>]+href="([^"]*notice-rapport[^"]*)"[^>]*>(.*?)</a>', c2, re.S)]
            ech = re.sub(r"\s+", " ", _H.unescape(re.sub(r"<[^>]+>", " ", c2))).strip()
            act = [{"n": n.strip(), "r": r.strip()} for n, r in re.findall(r'alt="([^"(]+)\(([^)]+)\)"', c3)]
            if not title: continue
            prog.append({"sess": sess, "tab": tab, "struct": struct, "t": title, "url": url, "rp": rap, "ech": ech, "act": act})
seen_u = set(); n_p = 0
for p in prog:
    u = p["url"]
    if not u or u in seen_u or "/structures-temporaires/" in u or "notice-rapport" in u: continue
    seen_u.add(u)
    slug = re.sub(r"[^a-z0-9]+", "-", u.split("senat.fr/", 1)[-1].replace(".html", "").lower())[-90:]
    p["slug"] = slug
    if get(u, f"{CTL}/p_{slug}.html", tries=1, force=not p["rp"]): n_p += 1
for p in prog:
    if p.get("url") and not p.get("slug") and p["url"] in seen_u:
        p["slug"] = re.sub(r"[^a-z0-9]+", "-", p["url"].split("senat.fr/", 1)[-1].replace(".html", "").lower())[-90:]
json.dump(prog, open(f"{CTL}/programme.json", "w"), ensure_ascii=False)
print("Sénat programme de contrôle :", len(prog), "travaux,", n_p, "pages", flush=True)
