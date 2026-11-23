#!/usr/bin/env python3
"""Flux RSS officiels (Assemblée nationale, Sénat, Cour des comptes) -> rss.json
Usage : python3 fetch_rss.py <sortie/rss.json>
"""
import json, re, sys, html, urllib.request, datetime as dt, email.utils
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo
PARIS = ZoneInfo("Europe/Paris")
OUT = sys.argv[1]
W2 = "https://www2.assemblee-nationale.fr/feeds/detail/"
# (source, catégorie, nom, url, thèmes)
FEEDS = [
 ("AN", "Général", "Publications parlementaires", W2 + "documents-parlementaires", []),
 ("AN", "Général", "Comptes rendus des débats", W2 + "crs", ["institutions"]),
 ("AN", "Général", "Communiqués de presse", "https://www.assemblee-nationale.fr/dyn/rss/communiques-de-presse.xml", []),
 ("AN", "Commissions", "Commission des affaires culturelles", W2 + "ID_419604/(type)/instance", ["education", "culture"]),
 ("AN", "Commissions", "Commission des affaires économiques", W2 + "ID_419610/(type)/instance", ["economie", "agriculture", "logement"]),
 ("AN", "Commissions", "Commission des affaires étrangères", W2 + "ID_59047/(type)/instance", ["international"]),
 ("AN", "Commissions", "Commission des affaires sociales", W2 + "ID_420120/(type)/instance", ["social", "sante", "travail"]),
 ("AN", "Commissions", "Commission de la défense", W2 + "ID_59046/(type)/instance", ["defense"]),
 ("AN", "Commissions", "Commission du développement durable", W2 + "ID_419865/(type)/instance", ["environnement", "transports"]),
 ("AN", "Commissions", "Commission des finances", W2 + "ID_59048/(type)/instance", ["finances"]),
 ("AN", "Commissions", "Commission des lois", W2 + "ID_59051/(type)/instance", ["institutions", "securite", "justice", "collectivites"]),
 ("AN", "Commissions", "Commission des affaires européennes", W2 + "ID_415287/(type)/instance", ["international"]),
 ("AN", "Délégations", "OPECST", W2 + "ID_273589/(type)/instance", ["numerique", "environnement"]),
 ("AN", "Délégations", "Délégation aux droits des femmes", W2 + "ID_201269/(type)/instance", ["societe"]),
 ("AN", "Délégations", "Délégation aux outre-mer", W2 + "ID_675659/(type)/instance", ["outremer"]),
 ("AN", "Délégations", "Délégation aux collectivités territoriales", W2 + "ID_744127/(type)/instance", ["collectivites"]),
 ("AN", "Délégations", "Délégation aux droits des enfants", W2 + "ID_804431/(type)/instance", ["social", "societe"]),
 ("AN", "Délégations", "MECSS", W2 + "ID_412120/(type)/instance", ["social", "finances"]),
 ("AN", "Délégations", "Comité d'évaluation et de contrôle", W2 + "ID_420375/(type)/instance", ["institutions"]),
 ("SN", "Général", "Textes", "https://www.senat.fr/rss/textes.rss", []),
 ("SN", "Général", "Rapports", "https://www.senat.fr/rss/rapports.rss", []),
 ("SN", "Général", "Presse", "https://www.senat.fr/rss/presse.rss", []),
 ("CC", "Général", "Publications", "https://www.ccomptes.fr/rss/publications", []),
 ("CC", "Général", "Actualités", "https://www.ccomptes.fr/rss/actualites", []),
]
SEN_THEMES = [("Affaires étrangères et coopération", 4, ["international"]), ("Agriculture et pêche", 2, ["agriculture"]), ("Aménagement du territoire", 30, ["collectivites"]),
 ("Anciens combattants", 23, ["defense"]), ("Budget", 10, ["finances"]), ("Collectivités territoriales", 1, ["collectivites"]), ("Culture", 12, ["culture"]),
 ("Défense", 29, ["defense"]), ("Économie et finances, fiscalité", 17, ["finances", "economie"]), ("Éducation", 24, ["education"]), ("Énergie", 32, ["environnement"]),
 ("Entreprises", 33, ["economie"]), ("Environnement", 7, ["environnement"]), ("Famille", 13, ["social"]), ("Fonction publique", 19, ["institutions"]),
 ("Justice", 14, ["justice"]), ("Logement et urbanisme", 16, ["logement"]), ("Outre-mer", 18, ["outremer"]), ("PME, commerce et artisanat", 28, ["economie"]),
 ("Police et sécurité", 5, ["securite"]), ("Pouvoirs publics et Constitution", 9, ["institutions"]), ("Questions sociales et santé", 20, ["sante", "social"]),
 ("Recherches, sciences et techniques", 15, ["education", "numerique"]), ("Sécurité sociale", 25, ["social"]), ("Société", 3, ["societe"]), ("Sports", 31, ["culture"]),
 ("Traités et conventions", 11, ["international"]), ("Transports", 21, ["transports"]), ("Travail", 22, ["travail"]), ("Union européenne", 8, ["international"])]
for nom, n, th in SEN_THEMES:
    FEEDS.append(("SN", "Thèmes", nom, f"https://www.senat.fr/themes/rss/therss{n}.rss", th))

def clean(s, n=None):
    t = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s or ""))).strip()
    return (t[:n].rstrip() + "…") if n and len(t) > n else t
def pdate(s):
    s = (s or "").strip()
    if not s: return None
    try: return email.utils.parsedate_to_datetime(s).astimezone(PARIS).isoformat()[:16]
    except Exception: pass
    try: return dt.datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(PARIS).isoformat()[:16]
    except Exception: return None
def loc(tag): return tag.rsplit("}", 1)[-1]

feeds, items, seen = [], [], {}
now = dt.datetime.now(dt.timezone.utc)
for i, (src, cat, nom, url, th) in enumerate(FEEDS):
    f = {"id": i, "src": src, "cat": cat, "nom": nom, "url": url, "th": th, "n": 0, "ok": False}
    feeds.append(f)
    try:
        with urllib.request.urlopen(urllib.request.Request(url), timeout=60) as r: raw = r.read()
        root = ET.fromstring(raw)
    except Exception as e:
        print("échec", nom, e, file=sys.stderr); continue
    f["ok"] = True
    for it in root.iter():
        if loc(it.tag) not in ("item", "entry"): continue
        d = {loc(c.tag): c for c in it}
        title = clean((d.get("title").text if d.get("title") is not None else ""))
        link = d.get("link")
        href = (link.get("href") or link.text or "").strip() if link is not None else ""
        date = pdate((d.get("pubDate") if d.get("pubDate") is not None else d.get("updated") if d.get("updated") is not None else d.get("date")).text if any(k in d for k in ("pubDate", "updated", "date")) else "")
        desc = d.get("description") if d.get("description") is not None else d.get("summary")
        summ = clean(desc.text if desc is not None else "", 360)
        if summ == title: summ = ""
        if not title or title.startswith("Aucun résultat"): continue
        if date and date < (now - dt.timedelta(days=120)).astimezone(PARIS).isoformat()[:16]: continue
        key = (href or title).replace("http://", "https://")
        f["n"] += 1
        if key in seen:
            if i not in seen[key]["f"]: seen[key]["f"].append(i)
            continue
        seen[key] = {"f": [i], "t": title, "l": href.replace("http://", "https://"), "d": date, "s": summ}
        items.append(seen[key])
items.sort(key=lambda x: x["d"] or "", reverse=True)
json.dump({"genere": now.astimezone(PARIS).isoformat()[:16], "feeds": feeds, "items": items}, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
print(len(feeds), "flux,", sum(f["ok"] for f in feeds), "lus,", len(items), "articles")
