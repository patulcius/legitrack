#!/usr/bin/env python3
"""Veille parlementaire v3 : suivi global AN + Sénat + Cour des comptes, avec thématiques et fiches élus.

Usage : python3 build_v3.py <dossier_raw_AN> <dossier_senat> <dossier_ccomptes> <dossier_sortie>
<dossier_raw_AN> : dossiers/, agenda/, qe/, qosd/, qag/, organes/ (AMO30, historique complet), amo10/, scrutins/, amendements.zip
Sorties (fichiers JSON chargés à la demande par le site) :
  core.json, dos/NN.json, amdt/*.json, agenda.json, questions.json, rapports.json, elus.json, votes/NN.json, scrutins.json
"""
import csv, glob, html as H, io, json, os, re, sys, zipfile, zlib, datetime as dt
from collections import Counter, defaultdict

RAW, SEN, CC, OUT = sys.argv[1:5]
TODAY = dt.date.today()
TODAY_S = TODAY.isoformat()
NOW_ISO = dt.datetime.now().astimezone().isoformat(timespec="minutes")
AN = "https://www.assemblee-nationale.fr"
SINCE = dt.date(2024, 10, 1)
import gzip
for sub in ("dos", "amdt", "votes", "amtx"):
    os.makedirs(f"{OUT}/{sub}", exist_ok=True)
    for f in glob.glob(f"{OUT}/{sub}/*.json*") + glob.glob(f"{OUT}/{sub}/*.txt"): os.remove(f)
def ptxt(h):
    """HTML -> texte en gardant les paragraphes."""
    t = re.sub(r"(?i)<br\s*/?>|</p>|</li>|</h\d>|</tr>", "\n", h or "")
    t = H.unescape(re.sub(r"<[^>]+>", " ", t)).replace("\xa0", " ")
    return "\n".join(l for l in (re.sub(r"[ \t]+", " ", x).strip() for x in t.split("\n")) if l)
def dumpgz(obj, p):
    """JSON compressé (gzip) puis encodé en base64 dans un .txt : le site le décompresse avec DecompressionStream."""
    import base64
    raw = gzip.compress(json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8"), 9)
    with open(p.replace(".json.gz", ".txt"), "w") as f: f.write(base64.b64encode(raw).decode())

def load(p):
    with open(p, encoding="utf-8") as f: return json.load(f)
def dump(obj, p):
    with open(p, "w", encoding="utf-8") as f: json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))
def aslist(x):
    if x is None: return []
    return x if isinstance(x, list) else [x]
def txt(x):
    if x is None: return ""
    if isinstance(x, list): return " ".join(txt(i) for i in x)
    if isinstance(x, dict): return " ".join(txt(v) for v in x.values())
    return str(x)
def s(x): return x if isinstance(x, str) else None
def clean(h, n=None):
    t = re.sub(r"\s+", " ", H.unescape(re.sub(r"<[^>]+>", " ", h or ""))).replace("\xa0", " ").strip()
    return t[:n].rstrip() + "…" if n and len(t) > n else t
def cap(t): return t[:1].upper() + t[1:] if t else t
def norm_url(u): return re.sub(r"^http://", "https://", (u or "").strip())
def read_csv(path, sep=";"):
    with open(path, encoding="latin1") as f: t = f.read()
    if t.startswith("sep="): t = t.split("\n", 1)[1]
    return [{(k or "").strip(): (v or "").strip() for k, v in r.items()} for r in csv.DictReader(io.StringIO(t), delimiter=sep)]
def fr_date(x):
    x = (x or "").strip()
    try:
        if re.match(r"\d{2}/\d{2}/\d{4}", x): return dt.date(int(x[6:10]), int(x[3:5]), int(x[:2]))
        if re.match(r"\d{4}-\d{2}-\d{2}", x): return dt.date.fromisoformat(x[:10])
    except ValueError: return None
    return None
def shard(key, n): return zlib.crc32(key.encode()) % n

# ---------------------------------------------------------------- thématiques
THEMES = [
    ("securite", "Sécurité, police, gendarmerie", r"gendarm|polic(e|ier)|forces de l.ordre|sécurité intérieure|vidéoprotection|vidéosurveillance|narcotrafic|ordre public|terroris|renseignement|refus d.obtemp|sécurité privée|stupéfiants|délinquan|criminalité|sécurité des biens|légitime défense|\bSécurités\b|sécurité civile|pompiers|incendie et de secours"),
    ("justice", "Justice et droit", r"justice|pénal|peines?\b|détenu|prison|pénitentiaire|tribunal|magistrat|juridiction|procédure civile|code civil|droit civil|victimes?|avocat|notaire|greffe|casier|récidive"),
    ("defense", "Défense et anciens combattants", r"défense nationale|\barmées?\b|militaire|anciens combattants|programmation militaire|forces armées|OTAN|dissuasion|mémoire"),
    ("international", "Europe et affaires étrangères", r"accord entre|convention entre|traité|européen|Union européenne|international|coopération|diplomat|Ukraine|Israël|Palestin|Gaza|affaires étrangères|francophonie|aide au développement"),
    ("immigration", "Immigration, asile, nationalité", r"étrangers?|immigration|asile|nationalité|titre de séjour|migra|rétention administrative|OQTF|intégration"),
    ("sante", "Santé", r"santé|médic|hôpita|soins|patients?|maladie|pharma|fin de vie|aide à mourir|médecin|infirmi|psychiatr|cancer|vaccin|addiction|tabac|alcool"),
    ("social", "Solidarités, famille, retraites", r"sécurité sociale|retraite|famille|familial|handicap|pauvreté|solidarit|personnes âgées|autonomie|allocation|\bRSA\b|aidants?|enfance|enfants?|petite enfance|EHPAD|minima sociaux|sans-abri"),
    ("travail", "Travail et emploi", r"travail|emploi|salari|chômage|syndica|apprentissage|formation professionnelle|licenci|France Travail|assurance chômage|dialogue social"),
    ("economie", "Économie et entreprises", r"entreprises?|économi|commerce|industri|artisan|consommat|concurrence|\bPME\b|tourisme|banque|bancaire|assurances?\b|souveraineté|start-up|attractivité|postal|La Poste"),
    ("finances", "Finances publiques et fiscalité", r"loi de finances|budget|fiscal|impôts?|taxes?\b|dette|comptes publics|\bTVA\b|financement de la sécurité sociale|règlement du budget|dépenses publiques|douane|contribu"),
    ("collectivites", "Collectivités territoriales", r"collectivités|communes?\b|maires?\b|municipa|intercommunal|départements?\b|régions?\b|élus? locaux|élu local|décentralis|territori|ruralité"),
    ("education", "Éducation, recherche, jeunesse", r"école|éducation|enseign|élèves?|universit|étudiant|recherche|scolaire|lycée|collège|jeunesse|baccalauréat|professeurs?"),
    ("environnement", "Environnement et énergie", r"environnement|climat|énergie|énergétique|nucléaire|\beaux?\b|biodiversité|pollution|déchets|renouvelable|carbone|électricité|hydrogène|forêts?|littoral|risques naturels|écolog|nature|PFAS|chasse|loups?"),
    ("agriculture", "Agriculture, alimentation, pêche", r"agricol|agricult|alimentation|alimentaire|pêche|élevage|éleveurs|viticult|phytosanitaire|foncier agricole|vétérinaire|bien-être animal"),
    ("transports", "Transports et mobilités", r"transports?|mobilit|ferroviaire|\bSNCF\b|routi|aérien|aéroport|automobil|véhicule|permis de conduire|sécurité routière|autoroute|VTC|taxis?"),
    ("logement", "Logement et urbanisme", r"logement|locati|\bbaux\b|\bbail\b|urbanisme|habitat|copropri|construction|loyer|immobili|\bHLM\b|artificialisation|\bZAN\b"),
    ("numerique", "Numérique, médias, télécoms", r"numérique|internet|données|cyber|intelligence artificielle|plateformes?|réseaux sociaux|télécom|audiovisuel|médias|presse|écrans|influenceurs"),
    ("culture", "Culture, sport, patrimoine", r"cultur|patrimoine|sport|olympiques|musée|spectacle|\blivres?\b|cinéma|langues?\b|artistes|monuments"),
    ("institutions", "Institutions et vie publique", r"constitution|élect|scrutin|référendum|parlement|Assemblée nationale|Sénat\b|vie publique|partis politiques|lobby|transparence|fonction publique|fonctionnaires|haute autorité|déontologie|mandat|Conseil d.État|commission d.enquête"),
    ("outremer", "Outre-mer", r"outre-mer|Mayotte|Guadeloupe|Martinique|Guyane|La Réunion|Nouvelle-Calédonie|Polynésie|Saint-Pierre|Wallis|Saint-Martin|Saint-Barthélemy|ultramarin"),
    ("societe", "Égalité, droits, société", r"égalité|femmes|discrimination|violences (conjugales|sexuelles|sexistes|intrafamiliales|faites)|laïcité|religi|droits de l.homme|animal|animaux|bioéthique|harcèlement|\bLGBT|\bIVG\b|racisme|antisémitisme|libertés?|vie privée|associations?"),
]
THEMES_RE = [(k, re.compile(r, re.I)) for k, _, r in THEMES]
COM_FALLBACK = [(r"lois|législation", "institutions"), (r"finances|budget", "finances"), (r"affaires sociales", "social"),
                (r"défense|forces armées", "defense"), (r"affaires étrangères|européennes", "international"),
                (r"affaires économiques", "economie"), (r"développement durable|aménagement", "environnement"),
                (r"culture|éducation", "education"), (r"outre-mer", "outremer"), (r"droits des femmes", "societe")]

def themes_of(text, organe=None, extra=None, maxn=3):
    sc = Counter()
    for k, r in THEMES_RE:
        n = len(r.findall(text or ""))
        if n: sc[k] = n
    if extra:
        for k, r in THEMES_RE:
            if r.search(extra): sc[k] += 2
    th = [k for k, _ in sc.most_common(maxn)]
    if not th and organe:
        for pat, k in COM_FALLBACK:
            if re.search(pat, organe, re.I): th = [k]; break
    return th or ["institutions"]

# ---------------------------------------------------------------- référentiels AN
organes, acteurs, acteur_raw = {}, {}, {}
for base in ("organes", "amo10"):
    for f in glob.glob(f"{RAW}/{base}/**/organe/*.json", recursive=True):
        o = load(f)["organe"]
        organes[o["uid"]] = {"type": o.get("codeType"), "libelle": o.get("libelle"), "court": o.get("libelleAbrege") or o.get("libelleAbrev"),
                             "fin": ((o.get("viMoDe") or {}).get("dateFin"))}
    for f in glob.glob(f"{RAW}/{base}/**/acteur/*.json", recursive=True):
        a = load(f)["acteur"]
        uid = a["uid"]["#text"] if isinstance(a["uid"], dict) else a["uid"]
        i = a["etatCivil"]["ident"]
        acteurs[uid] = f"{i.get('prenom','')} {i.get('nom','')}".strip()
        if base == "amo10" or uid not in acteur_raw: acteur_raw[uid] = (a, base)

def org_name(ref): return (organes.get(ref) or {}).get("libelle")
def org_court(ref): o = organes.get(ref) or {}; return o.get("court") or o.get("libelle")

# ---------------------------------------------------------------- délais réglementaires
def easter(y):
    a=y%19;b=y//100;c=y%100;d=b//4;e=b%4;f=(b+8)//25;g=(b-f+1)//3;h=(19*a+b-d-g+15)%30
    i=c//4;k=c%4;l=(32+2*e+2*i-h-k)%7;m=(a+11*h+22*l)//451;mo=(h+l-7*m+114)//31;da=((h+l-7*m+114)%31)+1
    return dt.date(y,mo,da)
def holidays(y):
    e = easter(y)
    return {dt.date(y,1,1), e+dt.timedelta(1), dt.date(y,5,1), dt.date(y,5,8), e+dt.timedelta(39), e+dt.timedelta(50),
            dt.date(y,7,14), dt.date(y,8,15), dt.date(y,11,1), dt.date(y,11,11), dt.date(y,12,25)}
def third_working_day_before(d):
    n, cur = 0, d
    while n < 3:
        cur -= dt.timedelta(1)
        if cur.weekday() != 6 and cur not in holidays(cur.year): n += 1
    return cur
MOIS = {m: i+1 for i, m in enumerate(["janvier","février","mars","avril","mai","juin","juillet","août","septembre","octobre","novembre","décembre"])}
DL_RE = re.compile(r"date limite de dépôt des amendements[^.]*?fixée au (?:\w+ )?(\d{1,2})(?:er)? (\w+)(?: (\d{4}))?,? à (\d{1,2}) ?h(?:eures)?(?: ?(\d{2}))?", re.I)
def parse_deadline(text, ref):
    m = DL_RE.search(text)
    if not m: return None
    d, mo, y, h, mi = m.groups(); mo = MOIS.get(mo.lower())
    if not mo: return None
    y = int(y) if y else ref.year
    try: dd = dt.datetime(y, mo, int(d), int(h), int(mi or 0))
    except ValueError: return None
    if dd.date() > ref: dd = dd.replace(year=y-1)
    return dd

# ---------------------------------------------------------------- dossiers AN
documents = {}
for f in glob.glob(f"{RAW}/dossiers/json/document/*.json"):
    d = load(f)["document"]; documents[d["uid"]] = d

def chambre_of(code, ref):
    if code.startswith("SN"): return "Sénat"
    if code.startswith("CMP"): return "CMP"
    if code.startswith(("CC", "PROM")): return "—"
    return "Assemblée"

def walk_actes(a, out):
    for x in aslist(a):
        code = x.get("codeActe", "")
        lib = (x.get("libelleActe") or {}).get("nomCanonique") or code
        date = x.get("dateActe")
        if date:
            it = {"d": date[:16], "c": code, "l": lib, "o": org_court(x.get("organeRef")), "ch": chambre_of(code, x.get("organeRef"))}
            if x.get("texteAssocie"): it["tx"] = x["texteAssocie"]
            rap = [acteurs.get(r.get("acteurRef")) for r in aslist((x.get("rapporteurs") or {}).get("rapporteur"))]
            if any(rap): it["rap"] = [r for r in rap if r]
            if x.get("statutConclusion"): it["l"] += f" ({txt(x['statutConclusion'].get('libelle'))})"
            if code.endswith("COM-FOND-SAISIE"): it["of"] = x.get("organeRef")
            out.append(it)
        walk_actes((x.get("actesLegislatifs") or {}).get("acteLegislatif"), out)

TYPE_COURT = {"Projet de loi ordinaire": "PJL", "Proposition de loi ordinaire": "PPL", "Résolution": "PPR",
              "Résolution Article 34-1": "PPR 34-1", "Mission d'information": "Mission", "Rapport d'information sans mission": "Rapport",
              "Projet ou proposition de loi constitutionnelle": "PJL/PPL constit.", "Projet de loi de finances de l'année": "PLF",
              "Projet de loi de financement de la sécurité sociale": "PLFSS", "Projet de loi de finances rectificative": "PLFR",
              "Projet de ratification des traités et conventions": "Traité", "Projet ou proposition de loi organique": "Loi organique",
              "Commission d'enquête": "Commission d'enquête", "Allocution du Président de l'Assemblée nationale": "Allocution",
              "Engagement de la responsabilité gouvernementale": "Art. 49", "Message du Président de la République": "Message",
              "Déclaration du gouvernement suivie d'un vote": "Déclaration", "Projet de loi de règlement des comptes": "PLRG",
              "Pétition": "Pétition", "Immunité": "Immunité", "Responsabilité pénale du président de la république": "Art. 68",
              "Résolution européenne": "PPRE", "Motion de censure": "Motion de censure", "Approbation des comptes": "Comptes"}
LAWLIKE = ("PJL", "PPL", "PLF", "PLFSS", "PLFR", "Traité", "Loi organique", "PJL/PPL constit.", "PLRG")

dossiers = {}
doc_title_map = {}
for f in glob.glob(f"{RAW}/dossiers/json/dossierParlementaire/*.json"):
    d = load(f)["dossierParlementaire"]
    if d.get("legislature") != "17": continue
    titre = cap(d["titreDossier"]["titre"])
    proc = d["procedureParlementaire"]["libelle"]
    tl = []
    walk_actes((d.get("actesLegislatifs") or {}).get("acteLegislatif"), tl)
    tl.sort(key=lambda x: x["d"])
    seen, t2 = set(), []
    for t in tl:
        k = (t["d"], t["l"], t["o"])
        if k not in seen: seen.add(k); t2.append(t)
    tl = t2
    init = [acteurs.get(a.get("acteurRef")) for a in aslist(((d.get("initiateur") or {}).get("acteurs") or {}).get("acteur"))]
    init_ids = [a.get("acteurRef") for a in aslist(((d.get("initiateur") or {}).get("acteurs") or {}).get("acteur")) if a.get("acteurRef")]
    init = [i for i in init if i]
    depot = next((t for t in tl if t["c"].endswith("DEPOT")), None)
    depot_an = next((t for t in tl if "DEPOT" in t["c"] and t["ch"] == "Assemblée" and t.get("tx", "").startswith(("PRJLAN", "PIONAN", "PNREAN"))), None)
    ref_doc = (depot_an or depot or {}).get("tx")
    num = (documents.get(ref_doc) or {}).get("notice", {}).get("numNotice") if ref_doc else None
    if num and "SNR" in (ref_doc or ""): num += " (Sénat)"
    com_fond = next((t for t in reversed(tl) if t.get("of")), None)
    typ = TYPE_COURT.get(proc, proc)
    dossiers[d["uid"]] = {
        "id": d["uid"], "titre": titre, "type": typ, "procedure": proc,
        "url": f"{AN}/dyn/17/dossiers/{d['uid']}", "senat": norm_url(d["titreDossier"].get("senatChemin")) or None,
        "auteurs": init, "auteurs_id": init_ids, "numero": num,
        "commission": org_name(com_fond["of"]) if com_fond else None,
        "rapporteurs": sorted({r for t in tl for r in t.get("rap", [])}),
        "depot": depot["d"][:10] if depot else (tl[0]["d"][:10] if tl else None),
        "timeline": tl, "documents": [], "budget": [], "origine": "Assemblée",
    }

# documents de chaque dossier
for uid, doc in documents.items():
    ref = doc.get("dossierRef")
    tp = (doc.get("titres") or {}).get("titrePrincipal") or ""
    if ref in dossiers and uid[:4] in ("PION", "PRJL") and tp:
        k = re.sub(r"^(projet|proposition) de loi( organique| constitutionnelle)?\s*", "", tp.lower()).strip(" .")
        doc_title_map.setdefault(k[:120], ref)
    if ref not in dossiers: continue
    ch = (doc.get("cycleDeVie") or {}).get("chrono") or {}
    typ = ((doc.get("classification") or {}).get("type") or {})
    dossiers[ref]["documents"].append({
        "n": typ.get("libelle") or uid[:4], "ch": "Sénat" if "SNR" in uid else "Assemblée",
        "num": (doc.get("notice") or {}).get("numNotice"),
        "d": (ch.get("dateDepot") or ch.get("dateCreation") or "")[:10] or None,
        "t": tp[:240], "url": f"{AN}/dyn/opendata/{uid}.html"})
for d in dossiers.values():
    d["documents"].sort(key=lambda x: x["d"] or "")

# ---------------------------------------------------------------- Sénat : dossiers
by_url = {d["senat"]: d for d in dossiers.values() if d.get("senat")}
sen_dl = {norm_url(r["URL du dossier"]): r for r in read_csv(f"{SEN}/dossiers-legislatifs.csv")}
sen_ppl = {norm_url(r["URL du dossier"]): r for r in read_csv(f"{SEN}/ppl.csv")}
for u, d in by_url.items():
    if u in sen_dl:
        d["etat_senat"] = sen_dl[u]["État du dossier"]; d["themes_senat"] = sen_dl[u].get("Thèmes")
STYPE = [("proposition de loi organique", "Loi organique"), ("projet de loi organique", "Loi organique"),
         ("proposition de loi constitutionnelle", "PJL/PPL constit."), ("projet de loi constitutionnelle", "PJL/PPL constit."),
         ("projet de loi de finances", "PLF"), ("projet de loi de financement", "PLFSS"),
         ("projet de loi", "PJL"), ("proposition de loi", "PPL"), ("proposition de résolution européenne", "PPRE"), ("proposition de résolution", "PPR")]
for u, r in sen_dl.items():
    dep = fr_date(r["Date initiale"])
    if not dep or dep < SINCE or u in by_url: continue
    slug = u.rsplit("/", 1)[-1].replace(".html", "")
    p = sen_ppl.get(u) or {}
    auteurs = [a.strip().title() for a in (p.get("Auteurs") or "").split(",") if a.strip()]
    ty = r["Type de dossier"].lower()
    tl = [{"d": dep.isoformat() + "T00:00", "c": "SN1-DEPOT", "l": "Dépôt au Sénat", "o": "Sénat", "ch": "Sénat"}]
    prom = fr_date(r.get("Date de promulgation"))
    if prom: tl.append({"d": prom.isoformat() + "T00:00", "c": "PROM-PUB", "l": f"Promulgation (loi n° {r.get('Numéro de la loi')})", "o": "", "ch": "—"})
    did = "SN-" + slug
    d = dossiers[did] = {"id": did, "titre": cap(r["Titre"]), "type": next((v for k, v in STYPE if ty.startswith(k)), r["Type de dossier"]),
                         "procedure": r["Type de dossier"], "url": u, "senat": u, "auteurs": auteurs, "auteurs_id": [],
                         "numero": (p.get("Numéro de texte") + " (Sénat)") if p.get("Numéro de texte") else None,
                         "commission": None, "rapporteurs": [], "depot": dep.isoformat(), "timeline": tl, "documents": [], "budget": [],
                         "etat_senat": r["État du dossier"], "themes_senat": r.get("Thèmes"), "origine": "Sénat"}
    by_url[u] = d
slug_map = {u.rsplit("/", 1)[-1].replace(".html", ""): d for u, d in by_url.items()}

# Pages des dossiers du Sénat : étapes clés (commission saisie, rapporteurs) si disponibles
for slug, d in slug_map.items():
    p = f"{SEN}/dossiers/{slug}.html"
    if not os.path.exists(p): continue
    h = open(p, encoding="utf-8", errors="replace").read()
    if d["origine"] == "Sénat":
        m = re.search(r"Commission[^<]{0,20}(?:saisie|au fond)[^<]*?:\s*</?[^>]*>\s*([^<]{5,120})", h)
        if m and not d["commission"]: d["commission"] = clean(m.group(1))

# ---------------------------------------------------------------- thèmes des dossiers
for d in dossiers.values():
    d["themes"] = themes_of(d["titre"], d.get("commission"), d.get("themes_senat"))

# ---------------------------------------------------------------- statut de chaque dossier
def status(d):
    tl = d["timeline"]; codes = [t["c"] for t in tl]
    typ = d["type"]
    if any(c.startswith("PROM") for c in codes): return ("Promulgué", "ok")
    if d["origine"] == "Sénat":
        e = (d.get("etat_senat") or "")
        if re.search(r"promulgu", e, re.I): return ("Promulgué", "ok")
        if re.search(r"caduc|non adopt|rejet|retir", e, re.I): return (cap(e), "off")
        if re.search(r"^adopt", e, re.I): return (cap(e), "ok")
        return (cap(e.replace("Première lecture", "1re lecture").replace("Deuxième lecture", "2e lecture")) or "Déposé au Sénat", "sn")
    if typ not in LAWLIKE:
        if typ in ("Mission", "Commission d'enquête", "Rapport"):
            if any("RAPPORT" in c or "RAPP" in c for c in codes): return ("Rapport publié", "ok")
            return ("En cours", "an")
        last = tl[-1]["l"] if tl else "Déposé"
        if any(c.endswith("-DEC") for c in codes): return ("Examiné", "ok")
        return ("Déposé", "neutral")
    if any(c.startswith("CC") for c in codes): return ("Conseil constitutionnel", "cc")
    if not tl: return ("Déposé", "neutral")
    last = codes[-1]
    m = re.match(r"(AN|SN|CMP)(\d|NLEC|LDEF|LNEC)?", last)
    who = {"AN": "AN", "SN": "Sénat", "CMP": "CMP"}.get(m.group(1) if m else "", "")
    lec = {"1": "1re lecture", "2": "2e lecture", "3": "3e lecture", "NLEC": "Nouvelle lecture", "LDEF": "Lecture définitive"}.get((m.group(2) if m else "") or "", "")
    if who == "CMP": return ("Commission mixte paritaire", "cmp")
    if "DEBATS-DEC" in last or "-DEC" in last:
        if who == "AN" and d.get("senat"): return (f"Adopté par l'AN, transmis au Sénat", "sn")
        if who == "Sénat": return (f"Adopté par le Sénat ({lec})", "an")
        return (f"Voté en séance ({lec})", "ok")
    if "DEBATS" in last: return (f"En séance · {who} {lec}".strip(), "an" if who == "AN" else "sn")
    if re.search(r"COM-(FOND|AVIS)-(REUNION|RAPPORT)", last): return (f"En commission · {who} {lec}".strip(), "an" if who == "AN" else "sn")
    if "COM-FOND-NOMIN" in last: return (f"Rapporteur nommé · {who}", "an" if who == "AN" else "sn")
    if "COM" in last: return (f"Déposé · {who}", "neutral" if who == "AN" else "sn")
    if "DEPOT" in last: return (f"Déposé · {who}", "neutral")
    return (f"{who} {lec}".strip() or "En cours", "neutral")

# ---------------------------------------------------------------- amendements
OUTAM = defaultdict(list)
aut_amdt = defaultdict(lambda: [0, 0])  # acteurRef -> [déposés, adoptés]
aut_recent = defaultdict(list)
FINAL_NOT_ADOPTED = ("Rejeté", "Retiré", "Non soutenu", "Tombé", "Irrecevable", "Irrecevable 40", "Non soumis au vote")
z = zipfile.ZipFile(f"{RAW}/amendements.zip")
amd_raw = {}
for name in z.namelist():
    if not name.endswith(".json"): continue
    parts = name.split("/")
    did = parts[1] if len(parts) >= 4 else None
    if did not in dossiers: continue
    a = json.loads(z.read(name))["amendement"]
    corps = (a.get("corps") or {}).get("contenuAuteur") or {}
    cv = a.get("cycleDeVie") or {}
    sort = s(cv.get("sort"))
    etat = ((cv.get("etatDesTraitements") or {}).get("etat") or {}).get("libelle")
    sig = a.get("signataires") or {}
    aut = sig.get("auteur") or {}
    aref = s(aut.get("acteurRef"))
    nom = "Gouvernement" if aut.get("typeAuteur") == "Gouvernement" else (acteurs.get(aref) or clean(s(sig.get("libelle")), 50))
    grp = org_court(s(aut.get("groupePolitiqueRef"))) if s(aut.get("groupePolitiqueRef")) else None
    m = re.search(r"PO(\d+)", a["uid"]); org = "PO" + m.group(1) if m else None
    inst = "AN séance" if org == "PO838901" else "AN commission " + (org_court(org) or "").replace("Commission des ", "").replace("Commission de la ", "").replace("Commission ", "")
    div = (a.get("pointeurFragmentTexte") or {}).get("division") or {}
    art = div.get("articleDesignationCourte") or div.get("articleDesignation") or ""
    if div.get("avant_A_Apres") in ("Avant", "Après") and art: art = f"{div['avant_A_Apres'].lower()} {art}"
    tdoc = documents.get(a.get("texteLegislatifRef")) or {}
    tnum = ((tdoc.get("notice") or {}).get("numNotice") or "").zfill(4)
    ident = a.get("identification") or {}
    if not sort and etat in ("Irrecevable", "Irrecevable 40", "Retiré", "Non soutenu", "Tombé"): sort = etat
    it = {"n": ident.get("numeroLong"), "i": inst, "a": art, "au": nom, "g": grp, "s": sort, "d": (s(cv.get("dateDepot")) or "")[:10],
          "x": clean(corps.get("exposeSommaire"), 220), "u": f"{tnum}/{ident.get('prefixeOrganeExamen')}/{ident.get('numeroLong')}"}
    cos = aslist((sig.get("cosignataires") or {}).get("acteurRef"))
    if cos: it["c"] = len(cos)
    par = s(a.get("amendementParentRef"))
    amd_raw[a["uid"]] = it
    if par: it["_p"] = par
    it["_ar"] = aref
    it["_t"] = [ptxt(corps.get("dispositif")), ptxt(corps.get("exposeSommaire"))]
    if aref: aut_recent[aref].append([it["d"], did, it["n"], it["s"], art, clean(corps.get("exposeSommaire"), 160)])
    OUTAM[did].append(it)

# règle des sous-amendements : tombent si l'amendement parent n'est pas adopté
n_fix = 0
for uid, it in amd_raw.items():
    par = it.pop("_p", None)
    if par and par in amd_raw:
        p = amd_raw[par]; it["p"] = p["n"]
        if p["s"] and p["s"] != "Adopté" and it["s"] in ("Adopté", None):
            it["sb"] = it["s"]; it["s"] = "Tombé"; n_fix += 1
    ar = it.pop("_ar", None)
    if ar:
        aut_amdt[ar][0] += 1
        if it["s"] == "Adopté": aut_amdt[ar][1] += 1
print("sous-amendements requalifiés « Tombé » (AN) :", n_fix)

# Amendements du Sénat
n_fix_sn = 0
for f in glob.glob(f"{SEN}/amdt/*.csv"):
    slug, name = os.path.basename(f).split("__", 1)
    dos = slug_map.get(slug)
    if not dos: continue
    com = "commission" in name
    try: rows = read_csv(f, sep="\t")
    except Exception: continue
    loc = {}
    for r in rows:
        if not r.get("Numéro"): continue
        disp = clean(r.get("Dispositif"))
        sort = r.get("Sort") or None
        if sort and re.search(r"retiré", sort, re.I): sort = "Retiré"
        elif sort and re.search(r"irrecevable", sort, re.I): sort = "Irrecevable"
        elif sort and re.search(r"tombé", sort, re.I): sort = "Tombé"
        elif sort and re.search(r"non soutenu", sort, re.I): sort = "Non soutenu"
        elif sort and re.search(r"rejet", sort, re.I): sort = "Rejeté"
        elif sort and re.search(r"adopt", sort, re.I): sort = "Adopté"
        it = {"n": r["Numéro"], "i": "Sénat commission" if com else "Sénat séance", "a": r.get("Subdivision") or "",
              "au": r.get("Auteur") or "", "g": None, "s": sort, "d": (r.get("Date de dépôt") or "")[:10],
              "x": clean(r.get("Objet"), 220), "U": norm_url(r.get("Url amendement")) or None, "sn": 1,
              "_t": [ptxt(r.get("Dispositif")), ptxt(r.get("Objet"))]}
        if r.get("Au nom de"): it["au"] += f" ({r['Au nom de']})"
        if r.get("Nature") == "S/Amt":
            m = re.search(r"Amendement n°\s*([\w\- .]+?)(?:,|\s{2}|\s+[IVX]+\.|\s+Alinéa|\s+alinéa|$)", disp)
            if m: it["p"] = m.group(1).strip()
        loc[it["n"].split(" ")[0]] = it
        OUTAM[dos["id"]].append(it)
    for it in loc.values():
        if it.get("p"):
            p = loc.get(it["p"].split(" ")[0])
            if p and p["s"] and p["s"] != "Adopté" and it["s"] in ("Adopté", None):
                it["sb"] = it["s"]; it["s"] = "Tombé"; n_fix_sn += 1
print("sous-amendements requalifiés « Tombé » (Sénat) :", n_fix_sn)

# écriture : gros dossiers dans leur propre fichier, les autres regroupés
NAM = 60
groups = defaultdict(dict)
tgroups = defaultdict(dict)
for did, items in OUTAM.items():
    items.sort(key=lambda x: (x["d"] or "", x["n"] or ""))
    dos = dossiers[did]
    dos["amdt"] = {"t": len(items), "s": dict(Counter(x["s"] or "En attente" for x in items)),
                   "i": dict(Counter(x["i"] for x in items)), "last": max((x["d"] for x in items if x["d"]), default=None),
                   "r7": sum(1 for x in items if x["d"] and x["d"] >= (TODAY - dt.timedelta(days=7)).isoformat())}
    texts = [x.pop("_t", ["", ""]) for x in items]
    if len(items) >= 1200:
        fn = f"x{did}"; dump({did: items}, f"{OUT}/amdt/{fn}.json")
        for c in range(0, len(texts), 2000): dumpgz(texts[c:c + 2000], f"{OUT}/amtx/{fn}_{c // 2000}.json.gz")
    else:
        fn = f"g{shard(did, NAM):02d}"; groups[fn][did] = items; tgroups[fn][did] = texts
    dos["amdt"]["f"] = fn
for fn, obj in groups.items(): dump(obj, f"{OUT}/amdt/{fn}.json")
for fn, obj in tgroups.items(): dumpgz(obj, f"{OUT}/amtx/{fn}.json.gz")

# ---------------------------------------------------------------- agenda
events = []
def ev(**e): events.append({k: v for k, v in e.items() if v not in (None, "", False)})
last_dl = {}
for f in glob.glob(f"{RAW}/agenda/json/reunion/*.json"):
    r = load(f)["reunion"]
    start = r.get("timeStampDebut") or ""
    if not start: continue
    sdate = dt.date.fromisoformat(start[:10])
    if sdate < TODAY - dt.timedelta(days=45): continue
    etat = (r.get("cycleDeVie") or {}).get("etat")
    if etat in ("Annulé", "Supprimé"): continue
    seance = r["@xsi:type"] == "seance_type"
    oref = r.get("organeReuniRef")
    o = organes.get(oref) or {}
    if o.get("type") in ("GA", "GE", "GP", "PARPOL"): continue
    organe = "Séance publique" if seance else (o.get("libelle") or "Organe de l'Assemblée")
    odj = r.get("ODJ") or {}
    conv = txt((odj.get("convocationODJ") or {}).get("item"))
    resume = txt((odj.get("resumeODJ") or {}).get("item"))
    points = aslist((odj.get("pointsODJ") or {}).get("pointODJ"))
    lieu = (r.get("lieu") or {}).get("libelleLong")
    base = dict(ch="AN", org=organe, lieu=lieu, etat=etat if etat not in ("Confirmé", "Eventuel") else None, ty=o.get("type") if not seance else "SEANCE")
    if o.get("type") in ("CNPE", "MISINFO", "MISINFOCOM", "MISINFOPRE", "DELEG", "OFFPAR"): base["mi"] = oref
    done = set()
    for p in points:
        for ref in aslist((p.get("dossiersLegislatifsRefs") or {}).get("dossierRef")):
            if ref not in dossiers or ref in done: continue
            done.add(ref)
            dos = dossiers[ref]
            objet = clean(p.get("objet") or "", 300)
            ev(d=start[:16], k="seance" if seance else "commission", t=(objet or ("Discussion en séance" if seance else "Examen en commission")),
               ds=ref, th=dos["themes"], src="Agenda AN", **base)
            if dos["type"] not in LAWLIKE and dos["type"] not in ("PPR", "PPRE", "PPR 34-1"): continue
            key = (ref, seance)
            if key in last_dl and abs((sdate - last_dl[key]).days) < 10: continue
            last_dl[key] = sdate
            explicit = parse_deadline(conv, sdate)
            dl = explicit or dt.datetime.combine(third_working_day_before(sdate), dt.time(17))
            ev(d=dl.isoformat(timespec="minutes"), k="dl_seance" if seance else "dl_com",
               t="Délai de dépôt des amendements en séance" if seance else f"Délai de dépôt des amendements en commission",
               ds=ref, th=dos["themes"], src="Convocation de la commission" if explicit else "Calculé (art. 86 et 99 du Règlement)",
               calc=not explicit, ch="AN", org=organe)
    if done or seance: continue
    blob = " ".join([resume, conv] + [p.get("objet") or "" for p in points])
    titre = cap(re.sub(r"^[\s\-–•]+", "", clean(resume or " · ".join(p.get("objet") or "" for p in points) or conv, 400))) or "Réunion"
    kind = "audition" if re.search(r"audition|table ronde|entendre", blob, re.I) else "reunion"
    ev(d=start[:16], k=kind, t=titre, th=themes_of(blob, organe), src="Agenda AN", **base)

# Ordre du jour du Sénat
MOISN = MOIS
def senat_dt(t, ref):
    m = re.search(r"(\d{1,2})(?:er)?\s+(\w+)(?:\s+(\d{4}))?\s+à\s+(\d{1,2})\s*(?:h|heures)\s*(\d{2})?", t)
    if not m: return None
    d, mo, y, h, mi = m.groups(); mo = MOISN.get(mo.lower())
    if not mo: return None
    y = int(y) if y else ref.year
    cand = dt.datetime(y, mo, int(d), int(h), int(mi or 0))
    if cand.date() > ref + dt.timedelta(days=1) and not m.group(3): cand = cand.replace(year=y - 1)
    return cand
def txt_of(fr): return re.sub(r"\s+", " ", H.unescape(re.sub(r"<[^>]+>", " ", fr))).replace("\xa0", " ").strip()
try: page = open(f"{SEN}/odj.html", encoding="utf-8", errors="replace").read()
except FileNotFoundError: page = ""
for blk in re.split(r'<a name="', page)[1:]:
    hm_ = re.search(r'<button[^>]*>\s*(.*?)\s*</button>', blk, re.S)
    if not hm_: continue
    dm = re.search(r"(\d{1,2})(?:er)? (\w+) (\d{4})", txt_of(hm_.group(1)))
    if not dm or dm.group(2).lower() not in MOISN: continue
    day = dt.date(int(dm.group(3)), MOISN[dm.group(2).lower()], int(dm.group(1)))
    cur = None
    for item in re.split(r'<li class="timeline-item">', blk)[1:]:
        tt = re.search(r'<h3 class="timeline-title">(.*?)</h3>', item, re.S)
        when = txt_of(tt.group(1)) if tt else ""
        hh = re.search(r"(\d{1,2}) h (\d{2})|(\d{1,2}) heures", when)
        start = dt.datetime.combine(day, dt.time(int(hh.group(1) or hh.group(3)), int(hh.group(2) or 0))) if hh else dt.datetime.combine(day, dt.time(9, 30) if "matin" in when.lower() else dt.time(14, 30))
        for cls, frag in re.findall(r'<div class="(activiteParagraphe1|activiteParagrapheSuite)" >(.*?)</div>', item, re.S):
            if cls == "activiteParagraphe1":
                p_ = re.search(r"<p>(.*?)</p>", frag, re.S)
                texte, link = "", None
                if p_:
                    texte = txt_of(p_.group(1)); lk = re.search(r'href="([^"]*dossier-legislatif[^"]*)"', p_.group(1)); link = norm_url(lk.group(1)) if lk else None
                li = re.search(r"<li>(.*?)</li>", frag, re.S)
                sub = re.sub(r"\s*\(durée[^)]*\)", "", txt_of(li.group(1)).lstrip("=> ").strip()).strip() if li else ""
                if link and not link.startswith("http"): link = "https://www.senat.fr" + link
                dos = by_url.get(link) if link else None
                titre = (f"{texte} : {sub}" if sub and texte and len(texte) < 120 else (sub or texte))[:400]
                if not titre: continue
                ev(d=start.isoformat(timespec="minutes"), k="seance", t=titre, ds=dos["id"] if dos else None,
                   th=dos["themes"] if dos else themes_of(f"{texte} {sub}"), src="Ordre du jour du Sénat", ch="SN", org="Séance publique", lieu="Sénat", ty="SEANCE")
                cur = events[-1]
            elif cur is not None:
                for li in re.findall(r"<li>(.*?)</li>", frag, re.S):
                    t = txt_of(li).lstrip("• ").strip()
                    is_com = bool(re.search(r"amendements de commission", t))
                    if re.match(r"Délai limite pour le dépôt des amendements", t):
                        dd = senat_dt(t.split(":", 1)[-1], day)
                        if dd:
                            ev(d=dd.isoformat(timespec="minutes"), k="dl_com" if is_com else "dl_seance",
                               t=f"Délai limite de dépôt des amendements {'en commission' if is_com else 'en séance'}" + (f" : {cur['t'][:160]}" if not cur.get("ds") or dossiers[cur['ds']]['type'] == 'PLF' else ""),
                               ds=cur.get("ds"), th=cur["th"], src="Ordre du jour du Sénat (date officielle)", ch="SN", org="Sénat")
                    elif re.match(r"Réunion de la commission pour le rapport", t):
                        m2 = re.search(r"(\d{1,2})(?:er)?\s+(\w+)", t.split(":", 1)[-1])
                        if m2 and m2.group(2).lower() in MOISN:
                            dday = dt.date(day.year, MOISN[m2.group(2).lower()], int(m2.group(1)))
                            if dday > day: dday = dday.replace(year=day.year - 1)
                            ev(d=dt.datetime.combine(dday, dt.time(9 if "matin" in t else 14, 30)).isoformat(timespec="minutes"), k="commission",
                               t="Examen en commission (rapport et texte de la commission)" + ("" if cur.get("ds") else f" : {cur['t'][:160]}"),
                               ds=cur.get("ds"), th=cur["th"], src="Ordre du jour du Sénat", ch="SN", org="Commission du Sénat")
events.sort(key=lambda e: e["d"])
# dédoublonnage
seen, ev2 = set(), []
for e in events:
    k = (e["d"], e["k"], e.get("ds"), e["t"][:80], e["ch"])
    if k not in seen: seen.add(k); ev2.append(e)
events = ev2
for i, e in enumerate(events): e["id"] = i

for d in dossiers.values(): d["ech"] = []
for e in events:
    if e.get("ds") in dossiers: dossiers[e["ds"]]["ech"].append(e["id"])

# ---------------------------------------------------------------- scrutins et votes (AN)
scrutins = []
votes_by = defaultdict(list)
group_ref = {}
POS = {"pours": 0, "contres": 1, "abstentions": 2, "nonVotants": 3}
for f in sorted(glob.glob(f"{RAW}/scrutins/json/*.json"), key=lambda p: int(re.search(r"V(\d+)", p).group(1))):
    sc = load(f)["scrutin"]
    idx = len(scrutins)
    o = sc.get("objet") or {}
    dref = o.get("dossierLegislatif")
    dref = dref if isinstance(dref, str) else (dref or {}).get("dossierRef") if isinstance(dref, dict) else None
    titre = cap(sc.get("titre") or o.get("libelle") or "")
    if not dref:
        m = re.search(r"(?:du |de la )(?:projet|proposition) de loi(?: organique| constitutionnelle)?\s+(.*?)(?:\s*\((?:première|deuxième|nouvelle|lecture|texte).*)?\.?$", titre, re.I)
        if m:
            k = m.group(1).lower().strip(" .")[:120]
            dref = doc_title_map.get(k)
    syn = (sc.get("syntheseVote") or {}).get("decompte") or {}
    gpos = {}
    for g in aslist(((sc.get("ventilationVotes") or {}).get("organe") or {}).get("groupes", {}).get("groupe")):
        gr = g.get("organeRef"); v = g.get("vote") or {}
        gpos[org_court(gr) or gr] = {"pour": 0, "contre": 1, "abstention": 2}.get(v.get("positionMajoritaire"), 3)
        group_ref[gr] = org_court(gr)
        dn = v.get("decompteNominatif") or {}
        for key, pos in POS.items():
            node = dn.get(key)
            if not node: continue
            for vt in aslist(node.get("votant")):
                aref = vt.get("acteurRef")
                if aref: votes_by[aref].append((idx, pos, gpos[org_court(gr) or gr]))
    sort = (sc.get("sort") or {}).get("code") or ""
    scrutins.append({"n": int(sc["numero"]), "d": sc["dateScrutin"], "t": titre[:260], "ty": (sc.get("typeVote") or {}).get("codeTypeVote"),
                     "r": 1 if sort.startswith("adopt") else 0, "p": int(syn.get("pour") or 0), "c": int(syn.get("contre") or 0),
                     "a": int(syn.get("abstentions") or 0), "ds": dref if dref in dossiers else None, "g": gpos})
for i, sc in enumerate(scrutins):
    if sc["ds"]: dossiers[sc["ds"]].setdefault("scr", []).append(i)
dump(scrutins, f"{OUT}/scrutins.json")

# ---------------------------------------------------------------- questions
questions = []
q_by_aut = Counter()
for folder in ("qe", "qosd", "qag"):
    for f in glob.glob(f"{RAW}/{folder}/json/*.json"):
        q = load(f)["question"]
        idx = q.get("indexationAN") or {}
        rub = idx.get("rubrique") or ""
        ana = txt((idx.get("analyses") or {}).get("analyse"))
        tqs = aslist((q.get("textesQuestion") or {}).get("texteQuestion"))
        date_q = ((tqs[0] if tqs else {}).get("infoJO") or {}).get("dateJO")
        reps = aslist((q.get("textesReponse") or {}).get("texteReponse"))
        date_r = ((reps[0] if reps else {}).get("infoJO") or {}).get("dateJO") if reps else None
        cl = q.get("cloture") or {}
        aref = ((q.get("auteur") or {}).get("identite") or {}).get("acteurRef")
        q_by_aut[aref] += 1
        st = "r" if date_r else ("c" if cl.get("libelleCloture") else "a")
        questions.append({"id": q["uid"], "ty": q.get("type"), "n": q["identifiant"]["numero"], "rub": cap(rub), "an": cap(ana or idx.get("teteAnalyse") or ""),
                          "au": acteurs.get(aref, ""), "ai": aref, "g": ((q.get("auteur") or {}).get("groupe") or {}).get("abrege"),
                          "m": (q.get("minInt") or {}).get("abrege"), "d": date_q, "r": date_r, "st": st, "stl": cl.get("libelleCloture"),
                          "th": themes_of(f"{rub} {ana} {rub}", None, None, 2), "ch": "AN"})
sen_q_by = Counter()
for r in read_csv(f"{SEN}/questions-depuis-un-an.csv"):
    nat = r.get("Nature") or "QE"
    au = f"{r.get('Prénom','')} {r.get('Nom','')}".strip()
    sen_q_by[(r.get("Nom") or "").upper() + "|" + (r.get("Prénom") or "")] += 1
    questions.append({"id": r.get("Référence"), "ty": {"QAG": "QG"}.get(nat, nat), "n": r.get("Numéro"), "rub": r.get("Thème(s)") or "",
                      "an": cap(r.get("Titre") or ""), "au": au, "g": r.get("Groupe"), "m": r.get("Ministère de dépôt"),
                      "d": r.get("Date de publication JO") or None, "r": r.get("Date de réponse JO") or None,
                      "st": "r" if r.get("Date de réponse JO") else "a", "th": themes_of(f"{r.get('Titre','')}", None, r.get("Thème(s)"), 2),
                      "ch": "SN", "url": norm_url(r.get("URL Question"))})
questions.sort(key=lambda x: x.get("d") or "", reverse=True)
dump(questions, f"{OUT}/questions.json")

# ---------------------------------------------------------------- rapports
rapports = []
for uid, doc in documents.items():
    if not uid.startswith(("RINF", "RION")) or "L17" not in uid: continue
    t = (doc.get("titres") or {}).get("titrePrincipal") or ""
    ch = (doc.get("cycleDeVie") or {}).get("chrono") or {}
    auts = [acteurs.get((a.get("acteur") or {}).get("acteurRef")) for a in aslist((doc.get("auteurs") or {}).get("auteur"))]
    orgs = [org_name((a.get("organe") or {}).get("organeRef")) for a in aslist((doc.get("auteurs") or {}).get("auteur"))]
    rapports.append({"src": "AN", "ty": "Rapport d'information", "n": (doc.get("notice") or {}).get("numNotice"), "d": (ch.get("dateDepot") or "")[:10],
                     "t": cap(t[:300]), "au": ", ".join(a for a in auts if a)[:200], "org": next((o for o in orgs if o), None),
                     "url": f"{AN}/dyn/opendata/{uid}.html", "th": themes_of(t, next((o for o in orgs if o), None))})
for r in read_csv(f"{SEN}/rapports.csv"):
    d = fr_date(r.get("Date de dépôt"))
    if not d or d < SINCE: continue
    t = f"{r.get('Titre court','')} {r.get('Titre long','')}"
    rapports.append({"src": "SN", "ty": r.get("Type de rapport") or "Rapport", "n": r.get("Numéro"), "tome": r.get("Tome"), "d": d.isoformat(),
                     "t": cap((r.get("Titre court") or r.get("Titre long"))[:300]), "au": (r.get("Auteurs") or "")[:200],
                     "res": clean(r.get("Résumé"), 400), "url": norm_url(r.get("URL")), "th": themes_of(t, None, r.get("Thèmes"))})
CC_THEME = [(r"Sécurité(?! sociale)|Police", "securite"), (r"Justice", "justice"), (r"Défense", "defense"), (r"Santé", "sante"),
            (r"Solidarit|Sécurité sociale|Protection sociale", "social"), (r"Travail|Emploi", "travail"), (r"Économie|Entreprises|Industrie", "economie"),
            (r"Finances publiques|Fiscalité|Budget", "finances"), (r"Collectivités", "collectivites"), (r"Éducation|Enseignement|Recherche|Jeunesse", "education"),
            (r"Environnement|Énergie|Climat|Écologie", "environnement"), (r"Agriculture", "agriculture"), (r"Transports", "transports"),
            (r"Logement|Urbanisme", "logement"), (r"Numérique", "numerique"), (r"Culture|Sport", "culture"), (r"^Outre-mer", "outremer"),
            (r"Affaires étrangères|Europe|International", "international"), (r"Institutions|Fonction publique|État", "institutions")]
cc_seen = set()
def fmt_jur(j):
    m = re.match(r"(CRC|CTC)\s+(.*)", j)
    if not m: return j.title().replace("Des ", "des ") if j.isupper() else j
    rest = m.group(2).title().replace(" D'", " d'").replace("-Et-", "-et-").replace(" Et ", " et ")
    return f"{m.group(1)} {rest}"
for f in sorted(glob.glob(f"{CC}/p*.html")):
    h = open(f, encoding="utf-8", errors="replace").read()
    for li in re.split(r'<li class="search-result">', h)[1:]:
        li = li.split("</li>", 1)[0] if "</li>" in li[-200:] else li
        a = re.search(r'<a href="(/fr/publications/[^"]+)"', li)
        t = re.search(r'<h2 class="title">\s*(.*?)\s*</h2>', li, re.S)
        tm = re.search(r'datetime="(\d{4}-\d{2}-\d{2})', li)
        if not (a and t and tm) or a.group(1) in cc_seen: continue
        cc_seen.add(a.group(1))
        if tm.group(1) < SINCE.isoformat(): continue
        desc = re.search(r'<p class="description">\s*(.*?)\s*</p>', li, re.S)
        jur = re.search(r'<span class="title-hover title-hover-w-auto"\s*>\s*(.*?)\s*</span>', li, re.S)
        thz = [clean(x) for x in re.findall(r'<div class="field__item">(.*?)</div>', li, re.S)]
        th = []
        for x in thz:
            for pat, k in CC_THEME:
                if re.search(pat, x) and k not in th: th.append(k)
        title = clean(t.group(1))
        if not th: th = themes_of(title + " " + clean(desc.group(1) if desc else ""))
        jr = clean(jur.group(1)) if jur else "Cour des comptes"
        if not jr.lower().startswith("cour des comptes"): continue  # chambres régionales et territoriales, Cour d'appel financière : hors périmètre
        rapports.append({"src": "CC", "ty": "Cour des comptes", "jur": "Cour des comptes",
                         "d": tm.group(1), "t": title[:300], "res": clean(desc.group(1), 400) if desc else "", "url": "https://www.ccomptes.fr" + a.group(1),
                         "th": th[:3], "cct": thz})
rapports.sort(key=lambda r: r["d"] or "", reverse=True)
dump(rapports, f"{OUT}/rapports.json")

# ---------------------------------------------------------------- élus
GCOL = {"RN": "#1f3a93", "EPR": "#f5a623", "LFI-NFP": "#c0392b", "SOC": "#e84393", "DR": "#2e6ad1", "EcoS": "#27ae60", "Dem": "#e67e22",
        "HOR": "#3fa9f5", "LIOT": "#b8860b", "GDR": "#8b0000", "UDR": "#34495e", "NI": "#95a5a6"}
deputes = []
dep_detail = defaultdict(dict)
texts_by = Counter()
for d in dossiers.values():
    for a in d.get("auteurs_id", []): texts_by[a] += 1
first_scr_date = {}
for uid, (a, base) in acteur_raw.items():
    ms = aslist((a.get("mandats") or {}).get("mandat"))
    an = [m for m in ms if m.get("typeOrgane") == "ASSEMBLEE" and m.get("legislature") == "17"]
    if not an: continue
    an.sort(key=lambda m: m.get("dateDebut") or "")
    cur = an[-1]
    actif = not s(cur.get("dateFin"))
    gp = [m for m in ms if m.get("typeOrgane") == "GP" and m.get("legislature") == "17"]
    gp.sort(key=lambda m: (not s(m.get("dateFin")), m.get("dateDebut") or ""))
    g = gp[-1] if gp else None
    gref = ((g or {}).get("organes") or {}).get("organeRef")
    gcourt = org_court(gref) if gref else "NI"
    com = [m for m in ms if m.get("typeOrgane") == "COMPER" and not s(m.get("dateFin"))]
    com.sort(key=lambda m: m.get("dateDebut") or "")
    comlib = org_name(((com[-1] if com else {}).get("organes") or {}).get("organeRef")) if com else None
    roles = []
    for m in ms:
        if s(m.get("dateFin")) or m.get("typeOrgane") not in ("COMPER", "CNPS", "MISINFO", "CIEN", "DELEG", "OFFPAR", "GP", "COMNL", "ORGEXTPARL", "BUREAU", "CMP"): continue
        q = (m.get("infosQualite") or {}).get("codeQualite") or ""
        if q and q.lower() not in ("membre", "membre suppléant", "membre titulaire", "apparenté"):
            roles.append(f"{q} · {org_name((m.get('organes') or {}).get('organeRef')) or ''}")
    el = (cur.get("election") or {}).get("lieu") or {}
    i = a["etatCivil"]["ident"]
    nais = (a["etatCivil"].get("infoNaissance") or {}).get("dateNais")
    vs = votes_by.get(uid, [])
    start = (an[0].get("dateDebut") or "2024-07-18")[:10]
    end = s(cur.get("dateFin")) or "9999"
    possible = sum(1 for sc in scrutins if start <= sc["d"] <= end[:10])
    cast = [v for v in vs if v[1] != 3]
    loyal = sum(1 for v in cast if v[1] == v[2])
    deputes.append({"id": uid, "nom": f"{i.get('prenom','')} {i.get('nom','')}", "tri": i.get("alpha"), "civ": i.get("civ"),
                    "g": gcourt, "gl": org_name(gref) if gref else "Non inscrit", "dep": el.get("departement"), "nd": el.get("numDepartement"), "ci": el.get("numCirco"),
                    "com": comlib, "act": actif, "prof": s((a.get("profession") or {}).get("libelleCourant")),
                    "nais": nais, "nv": len(cast), "pa": round(100 * len(cast) / possible) if possible else None,
                    "lo": round(100 * loyal / len(cast)) if cast else None, "am": aut_amdt.get(uid, [0, 0])[0], "ad": aut_amdt.get(uid, [0, 0])[1],
                    "q": q_by_aut.get(uid, 0), "tx": texts_by.get(uid, 0), "ro": roles[:8], "vf": f"v{shard(uid, 24):02d}"})
    dep_detail[f"v{shard(uid, 24):02d}"][uid] = {"v": [[v[0], v[1]] for v in vs], "am": sorted(aut_recent.get(uid, []), key=lambda x: x[0] or "", reverse=True)[:60]}
deputes.sort(key=lambda x: (not x["act"], x["tri"] or x["nom"]))
for fn, obj in dep_detail.items(): dump(obj, f"{OUT}/votes/{fn}.json")

senateurs = []
sen_am = defaultdict(lambda: [0, 0])
sen_recent = defaultdict(list)
for did, items in OUTAM.items():
    for it in items:
        if not it.get("sn"): continue
        for au in re.findall(r"(?:M\.|Mme)\s+([A-ZÀ-Ý][A-ZÀ-Ý' \-]+?)(?=,|\s+et\s|\s*\(|$)", it["au"]):
            sen_am[au.strip()][0] += 1
            sen_recent[au.strip()].append([it["d"], did, it["n"], it["s"], it["a"], (it.get("x") or "")[:160]])
            if it["s"] == "Adopté": sen_am[au.strip()][1] += 1
try:
    sj = load(f"{SEN}/senateurs.json")
    for x in (sj if isinstance(sj, list) else sj.get("senateurs", sj.get("results", []))):
        nom = f"{x.get('prenom') or x.get('prenomUsuel') or ''} {x.get('nom') or x.get('nomUsuel') or ''}".strip()
        grp = x.get("groupe") or {}
        circ = x.get("circonscription") or {}
        coms = [o.get("libelle") for o in (x.get("organismes") or []) if o.get("type") == "COMMISSION"]
        x["commissionPermanente"] = coms[0] if coms else ""
        cle = (x.get("nom") or "").upper()
        senateurs.append({"id": x.get("matricule") or nom, "nom": nom, "civ": x.get("civilite"), "g": (grp.get("libelleCourt") if isinstance(grp, dict) else grp) or "",
                          "am": sen_am.get(cle, [0, 0])[0], "ad": sen_am.get(cle, [0, 0])[1], "prof": (x.get("categorieProfessionnelle") or {}).get("libelle"),
                          "gl": (grp.get("libelle") if isinstance(grp, dict) else grp) or "",
                          "dep": (circ.get("libelle") if isinstance(circ, dict) else circ) or "",
                          "com": ((x.get("commissionPermanente") or {}).get("libelle") if isinstance(x.get("commissionPermanente"), dict) else x.get("commissionPermanente")) or "",
                          "cle": cle, "url": "https://www.senat.fr" + (x.get("url") or ""), "q": sen_q_by.get((x.get("nom") or "").upper() + "|" + (x.get("prenom") or ""), 0)})
except Exception as e:
    print("sénateurs :", e)
dump({s_["cle"]: sorted(sen_recent.get(s_["cle"], []), key=lambda x: x[0] or "", reverse=True)[:60] for s_ in senateurs if s_.get("cle")}, f"{OUT}/senam.json")
dump({"deputes": deputes, "senateurs": senateurs, "groupes": {k: GCOL.get(k, "#7f8c8d") for k in sorted({d["g"] for d in deputes})}}, f"{OUT}/elus.json")

# ---------------------------------------------------------------- contrôle : missions, commissions d'enquête, délégations
CTL_LABEL = {"CNPE": "Commission d'enquête", "MISINFO": "Mission d'information", "MISINFOCOM": "Mission d'information commune",
             "MISINFOPRE": "Mission d'information de la Conférence des présidents", "DELEG": "Délégation", "OFFPAR": "Office parlementaire"}
CTL_START = "2024-07-18"
ctl_org = {}
for f in glob.glob(f"{RAW}/organes/**/organe/*.json", recursive=True):
    o = load(f)["organe"]
    ty = o.get("codeType")
    if ty not in CTL_LABEL: continue
    vm = o.get("viMoDe") or {}
    deb, fin = vm.get("dateDebut") or "", vm.get("dateFin")
    if ty in ("DELEG", "OFFPAR"):
        if fin: continue
    elif deb < CTL_START: continue
    ctl_org[o["uid"]] = {"id": o["uid"], "ch": "AN", "ty": ty, "tl": CTL_LABEL[ty], "t": cap(clean(o.get("libelle"), 400)),
                         "court": o.get("libelleAbrege"), "par": org_name(o.get("organeParent")), "deb": deb[:10] or None, "fin": (fin or "")[:10] or None,
                         "pres": [], "rap": [], "nm": 0, "ev": [], "rp": []}
# Composition (président, rapporteurs) depuis l'historique AMO30
for f in glob.glob(f"{RAW}/organes/**/acteur/*.json", recursive=True):
    a = load(f)["acteur"]
    uid = a["uid"]["#text"] if isinstance(a["uid"], dict) else a["uid"]
    for m in aslist((a.get("mandats") or {}).get("mandat")):
        ref = next((x for x in aslist((m.get("organes") or {}).get("organeRef")) if x in ctl_org), None)
        if not ref: continue
        mf = s(m.get("dateFin"))
        if mf and (not ctl_org[ref]["fin"] or mf[:10] < ctl_org[ref]["fin"]): continue
        q = ((m.get("infosQualite") or {}).get("codeQualite") or "").lower()
        nom = acteurs.get(uid)
        if not nom: continue
        mo = ctl_org[ref]
        if q.startswith("président"): mo["pres"].append({"n": nom, "id": uid})
        elif "rapporteu" in q: mo["rap"].append({"n": nom, "id": uid})
        elif q == "membre": mo["nm"] += 1
# Réunions (auditions, tables rondes, comptes rendus)
for f in glob.glob(f"{RAW}/agenda/json/reunion/*.json"):
    r = load(f)["reunion"]
    mo = ctl_org.get(r.get("organeReuniRef"))
    if not mo: continue
    start = r.get("timeStampDebut") or ""
    if start[:10] < CTL_START: continue
    etat = (r.get("cycleDeVie") or {}).get("etat")
    if etat == "Supprimé": continue
    odj = r.get("ODJ") or {}
    resume = txt((odj.get("resumeODJ") or {}).get("item"))
    conv = txt((odj.get("convocationODJ") or {}).get("item"))
    points = aslist((odj.get("pointsODJ") or {}).get("pointODJ"))
    blob = " ".join([resume, conv] + [p.get("objet") or "" for p in points])
    titre = cap(re.sub(r"^[\s\-–•]+", "", clean(resume or " · ".join(p.get("objet") or "" for p in points) or conv, 500))) or "Réunion"
    e = {"d": start[:16], "k": "audition" if re.search(r"audition|table ronde|entendre", blob, re.I) else "reunion", "t": titre}
    if etat == "Annulé": e["x"] = 1
    if r.get("compteRenduRef"): e["cr"] = f"{AN}/dyn/opendata/{r['compteRenduRef']}.html"
    if r.get("captationVideo") == "true": e["v"] = 1
    if r.get("ouverturePresse") == "false": e["hc"] = 1
    mo["ev"].append(e)
# Dossiers et rapports rattachés (commissions d'enquête, missions avec dossier)
for f in glob.glob(f"{RAW}/dossiers/json/dossierParlementaire/*.json"):
    raw = open(f, encoding="utf-8").read()
    refs = set(re.findall(r'"(PO\d+)"', raw)) & set(ctl_org)
    if not refs: continue
    dp = json.loads(raw)["dossierParlementaire"]
    tl = []; walk_actes((dp.get("actesLegislatifs") or {}).get("acteLegislatif"), tl)
    for ref in refs:
        mo = ctl_org[ref]
        if ref and dp["uid"] in dossiers: mo["ds"] = dp["uid"]
        mo["url"] = f"{AN}/dyn/17/dossiers/{dp['uid']}"
        for it in tl:
            if it.get("tx") and re.search(r"RAPPORT", it["c"]):
                doc = documents.get(it["tx"]) or {}
                num = (doc.get("notice") or {}).get("numNotice")
                mo["rp"].append({"d": it["d"][:10], "t": f"Rapport n° {num}" if num else "Rapport",
                                 "url": f"{AN}/dyn/opendata/{it['tx']}.html"})
            elif re.search(r"COMENQ-CREA|MISINF-CREA|CREA$", it["c"]) and not mo.get("crea"): mo["crea"] = it["d"][:10]
# Rapports d'information sans dossier : rapprochement par le titre
def _toks(t): return {w for w in re.findall(r"[a-zàâçéèêëîïôûùüÿœ]{4,}", (t or "").lower())} - {"mission", "information", "commission", "enquête", "rapport", "dans", "pour", "avec", "leurs", "sous", "entre", "relative", "déposé", "application", "article", "règlement", "conclusion", "travaux", "nationale", "assemblée"}
rinf = []
for uid, doc in documents.items():
    if not uid.startswith("RINF") or "L17" not in uid: continue
    t = (doc.get("titres") or {}).get("titrePrincipal") or ""
    rinf.append((uid, (doc.get("notice") or {}).get("numNotice"), _toks(t), ((doc.get("cycleDeVie") or {}).get("chrono") or {}).get("dateDepot") or ""))
for mo in ctl_org.values():
    if mo["rp"] or mo["ty"] in ("DELEG", "OFFPAR"): continue
    mt = _toks(re.sub(r"^(mission|commission)[^:]*?\b(sur|relative à|consacrée à)\b", "", mo["t"], flags=re.I))
    if len(mt) < 2: continue
    best = max(((len(mt & tt) / len(mt), uid, t, dd) for uid, t, tt, dd in rinf if dd[:10] >= (mo["deb"] or "")), default=None)
    if best and best[0] >= 0.75:
        mo["rp"].append({"d": best[3][:10], "t": f"Rapport d'information n° {best[2]}" if best[2] else "Rapport d'information", "url": f"{AN}/dyn/opendata/{best[1]}.html"})
# Sénat : commissions d'enquête et missions d'information communes
MOISL = {m: i + 1 for i, m in enumerate(["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"])}
def _frd(t):
    m = re.search(r"(\d{1,2})(?:er)?\s+(janvier|février|mars|avril|mai|juin|juillet|août|septembre|octobre|novembre|décembre)\s+(20\d\d)", t or "")
    return dt.date(int(m.group(3)), MOISL[m.group(2)], int(m.group(1))).isoformat() if m else None
try: ctl_idx = load(f"{SEN}/controle/index.json")
except Exception: ctl_idx = []
for it in ctl_idx:
    try: h = open(f"{SEN}/controle/{it['slug']}.html", encoding="utf-8", errors="replace").read()
    except OSError: continue
    main = (re.search(r"<main.*?</main>", h, re.S) or re.search(r".*", h, re.S)).group(0)
    main = re.sub(r"<script.*?</script>|<style.*?</style>|<svg.*?</svg>", "", main, flags=re.S)
    plain = clean(main)
    h1 = re.search(r"<h1[^>]*>(.*?)</h1>", main, re.S)
    title = clean(h1.group(1)) if h1 else it["slug"]
    k = plain.find("informations clés")
    info = plain[k:k + 1500] if k >= 0 else plain[:1500]
    def who(lbl):
        m = re.search(lbl + r"s?\s+(.{3,80}?)\s+(?=Président|Rapporteu|Créée|Crée|À l|A l|La commission|La mission|Le Sénat|Les |Pourquoi|Constitu|Sur |En |Dans |Composée|Saisie|Mission|Commission)", info)
        if not m: return []
        return [{"n": x.strip()} for x in re.split(r",\s*|\s+et\s+", m.group(1)) if x.strip()][:4]
    mo = {"id": "SN-" + it["slug"][:80], "ch": "SN", "ty": "CNPE" if it["kind"] == "CE" else "MISINFOCOM",
          "tl": "Commission d'enquête" if it["kind"] == "CE" else "Mission d'information commune", "t": cap(title[:400]),
          "par": None, "deb": None, "fin": None, "pres": who(r"Présidente?"), "rap": who(r"Rapporteure?"), "nm": 0, "ev": [], "rp": [], "url": it["url"]}
    m = re.search(r"s'est réunie? (?:le )?(\w+ \d{1,2}(?:er)? \w+ 20\d\d)", info)
    mo["deb"] = _frd(m.group(1)) if m else None
    m = re.search(r"(?:achever|s'achever) au plus tard le (\d{1,2}(?:er)? \w+ 20\d\d)", info)
    if m: mo["ech"] = _frd(m.group(1))
    m = re.search(r"rapport a été adopté (?:le )?(\w+ \d{1,2}(?:er)? \w+ 20\d\d)", info, re.I)
    rdate = _frd(m.group(1)) if m else None
    seen = set()
    for a in re.finditer(r'href="(https?://www\.senat\.fr/notice-rapport/[^"]+)"[^>]*>(.*?)</a>', main, re.S):
        if a.group(1) in seen: continue
        seen.add(a.group(1))
        tm = re.search(r"r\d\d-(\d+)(?:-(\d+))?-notice", a.group(1))
        lab = (f"Rapport n° {int(tm.group(1))}" + (f", tome {tm.group(2)}" if tm.group(2) else "")) if tm else (clean(a.group(2)) or "Rapport")
        mo["rp"].append({"d": rdate, "t": lab, "url": a.group(1)})
    if rdate: mo["fin"] = rdate
    try:
        crh = open(f"{SEN}/controle/{it['slug']}__cr.html", encoding="utf-8", errors="replace").read()
        for a in re.finditer(r'href="(/compte-rendu-commissions/(\d{8})/[^"]+\.html)"[^>]*>(.*?)</a>', crh, re.S):
            d8 = a.group(2)
            mo["ev"].append({"d": f"{d8[:4]}-{d8[4:6]}-{d8[6:]}", "k": "cr", "t": "Compte rendu · " + clean(a.group(3)), "cr": "https://www.senat.fr" + a.group(1)})
    except OSError: pass
    ctl_org[mo["id"]] = mo
# Sénat : programme de contrôle (missions d'information des commissions, contrôle budgétaire, délégations, office)
try: prog = load(f"{SEN}/controle/programme.json")
except Exception: prog = []
sn_titles = {re.sub(r"\W+", " ", m["t"].lower()).strip() for m in ctl_org.values() if m["ch"] == "SN"}
for p in prog:
    title = clean(p["t"])
    if not title or re.sub(r"\W+", " ", title.lower()).strip() in sn_titles: continue
    u_ = (p.get("url") or "").rstrip("/").replace(".html", "")
    sl = ("dossier-" + u_.rsplit("/", 1)[-1]) if "/dossier/" in u_ else (u_.rsplit("/", 1)[-1] if u_ else re.sub(r"[^a-z0-9]+", "-", title.lower()))
    sl = re.sub(r"[^a-z0-9-]+", "-", sl.lower()).strip("-")
    pid = "SN-p-" + sl[:110].rstrip("-")
    if pid in ctl_org: continue
    h = ""
    if p.get("slug"):
        try: h = open(f"{SEN}/controle/p_{p['slug']}.html", encoding="utf-8", errors="replace").read()
        except OSError: pass
    main = re.sub(r"<script.*?</script>|<style.*?</style>|<svg.*?</svg>", "", h, flags=re.S)
    plain = clean(main) if main else ""
    k = plain.find("NATURE ")
    info = plain[k:k + 1200] if k >= 0 else ""
    tab = p.get("tab")
    if re.search(r"prérogatives (?:dévolues|attribuées|des|d.une|de)\s*(?:aux|à une|des)?\s*commissions? d.enquête", plain, re.I):
        ty, tl = "MISINFO", "Mission d'information (prérogatives d'enquête)"
    elif tab == "FINC": ty, tl = "MISINFO", "Contrôle budgétaire"
    elif title.lower().startswith("groupe de suivi"): ty, tl = "MISINFO", "Groupe de suivi"
    elif tab == "OPES": ty, tl = "MISINFO", "Étude de l'Office parlementaire"
    elif tab in ("DDRO", "ENTR", "OUTR", "AFEU") and not title.lower().startswith(("mission", "mi ")): ty, tl = "MISINFO", "Rapport d'information"
    else: ty, tl = "MISINFO", "Mission d'information"
    rap = [{"n": a["n"]} for a in p.get("act", []) if a["r"].lower().startswith("rapporteu")]
    pres = [{"n": a["n"]} for a in p.get("act", []) if a["r"].lower().startswith("président")]
    nm = sum(1 for a in p.get("act", []) if a["r"].lower().startswith("membre"))
    if not nm and info:
        m = re.search(r"Membres de la mission d'information (.*?)(?: À | Le | La | Les | Lors | En | Depuis | Face | Dans | Afin |$)", info)
        if m: nm = len(re.findall(r"[A-ZÉ][\w'’-]+(?: (?:de |du |d'|La |Le )?[A-ZÉ][\w'’-]+)+", m.group(1)))
    mo = {"id": pid, "ch": "SN", "ty": ty, "tl": tl, "t": cap(title[:400]), "par": p.get("struct"), "deb": None, "fin": None,
          "pres": pres, "rap": rap, "nm": nm, "ev": [], "rp": [], "url": p.get("url")}
    rdate = _frd(p.get("ech"))
    for r in p.get("rp", []):
        tm = re.search(r"r\d\d-(\d+)(?:-(\d+))?-notice", r["url"])
        lab = (f"Rapport n° {int(tm.group(1))}" + (f", tome {tm.group(2)}" if tm.group(2) else "")) if tm else "Rapport"
        if r.get("t"): lab += " · " + clean(r["t"])[:160]
        mo["rp"].append({"d": rdate, "t": lab, "url": r["url"]})
    if mo["rp"] and rdate: mo["fin"] = rdate
    elif not mo["rp"]:
        e = clean(p.get("ech") or "")
        if e: mo["echl"] = e
    for b, body in re.findall(r'<button[^>]*class="accordion-button[^"]*"[^>]*>(.*?)</button>(.*?)(?=<button[^>]*class="accordion-button|$)', h, re.S):
        bt = clean(b)
        d = _frd(bt)
        if not d: continue
        lab = re.sub(r"^\s*\w+\s+\d{1,2}(?:er)?\s+\w+\s+20\d\d\s*[-–:]\s*", "", bt).strip() or bt
        kk = "audition" if re.search(r"audition|table ronde|entend", lab, re.I) else "reunion"
        ev = {"d": d, "k": kk, "t": cap(lab[:300])}
        cm = re.search(r'href="((?:https://www\.senat\.fr)?/compte-rendu-commissions/[^"]+)"', body)
        if cm: ev["cr"] = cm.group(1) if cm.group(1).startswith("http") else "https://www.senat.fr" + cm.group(1)
        if re.search(r"videos\.senat\.fr|vid[ée]o", body, re.I): ev["v"] = 1
        mo["ev"].append(ev)
    ctl_org[pid] = mo
controle = []
for mo in ctl_org.values():
    mo["ev"].sort(key=lambda e: e["d"])
    mo["rp"].sort(key=lambda r: r.get("d") or "")
    act = [e for e in mo["ev"] if not e.get("x")]
    fut = [e for e in act if e["d"][:10] >= TODAY_S]
    past = [e for e in act if e["d"][:10] < TODAY_S]
    mo["nx"] = fut[0]["d"] if fut else None
    mo["la"] = max([e["d"][:10] for e in past] + [r["d"] for r in mo["rp"] if r.get("d")] + [mo["deb"] or ""]) or None
    mo["na"] = sum(1 for e in act if e["k"] == "audition")
    mo["ncr"] = sum(1 for e in mo["ev"] if e.get("cr"))
    if mo["rp"]: mo["st"] = "Rapport publié"
    elif mo["fin"] and mo["fin"] < TODAY_S: mo["st"] = "Terminée"
    else: mo["st"] = "En cours"
    if mo["ty"] in ("DELEG", "OFFPAR"): mo["st"] = "Permanente"
    if mo["ty"] in ("DELEG", "OFFPAR") and not mo["ev"]: continue
    mo["th"] = themes_of(mo["t"], mo.get("par"))
    for k in ("pres", "rap"):
        u = {}; [u.setdefault(x["n"], x) for x in mo[k]]; mo[k] = list(u.values())
    controle.append({k: v for k, v in mo.items() if v not in (None, [], "")})
controle.sort(key=lambda m: (m["st"] in ("Terminée", "Rapport publié"), m["st"] == "Permanente", -(int((m.get("nx") or m.get("la") or "0000-00-00").replace("-", "")[:8] or 0))))
dump({"genere": NOW_ISO, "items": controle}, f"{OUT}/controle.json")
print("contrôle :", len(controle), "structures,", sum(len(m.get("ev", [])) for m in controle), "réunions")

# ---------------------------------------------------------------- détail des dossiers et noyau
NDS = 40
dshards = defaultdict(dict)
light = []
dep_ids = {d["id"] for d in deputes}
for d in dossiers.values():
    lab, cls = status(d)
    fut = [events[i] for i in d["ech"] if events[i]["d"][:10] >= TODAY_S]
    nx = fut[0] if fut else None
    last = d["timeline"][-1] if d["timeline"] else None
    actif = bool(fut) or bool(last and last["d"][:10] >= (TODAY - dt.timedelta(days=120)).isoformat()) or (d.get("amdt") or {}).get("r7", 0) > 0
    sh = f"d{shard(d['id'], NDS):02d}"
    ch = "AN+SN" if (d["origine"] == "Assemblée" and d.get("senat")) else ("SN" if d["origine"] == "Sénat" else "AN")
    light.append({"id": d["id"], "t": d["titre"][:220], "ty": d["type"], "th": d["themes"], "ch": ch, "st": lab, "sc": cls,
                  "dep": d["depot"], "ld": last["d"][:10] if last else None, "ll": (last or {}).get("l"), "nx": {"d": nx["d"], "k": nx["k"]} if nx else None,
                  "na": (d.get("amdt") or {}).get("t", 0), "nr": (d.get("amdt") or {}).get("r7", 0), "ns": len(d.get("scr", [])),
                  "num": d["numero"], "au": (d["auteurs"][:2] + ([f"+{len(d['auteurs'])-2}"] if len(d["auteurs"]) > 2 else [])), "ai": [x for x in d.get("auteurs_id", []) if x in dep_ids][:6], "ac": 1 if actif else 0, "f": sh})
    dshards[sh][d["id"]] = {k: d.get(k) for k in ("url", "senat", "auteurs", "auteurs_id", "commission", "rapporteurs", "timeline", "documents", "etat_senat", "procedure", "amdt", "scr", "ech")}
    dshards[sh][d["id"]]["auteurs_id"] = [a for a in d.get("auteurs_id", []) if a in dep_ids]
for fn, obj in dshards.items(): dump(obj, f"{OUT}/dos/{fn}.json")
light.sort(key=lambda x: ((x["nx"] or {}).get("d") or "9999", -(int((x["ld"] or "0000")[:4]))))
dump(events, f"{OUT}/agenda.json")
counts = {"dossiers": len(light), "actifs": sum(x["ac"] for x in light), "events": len(events), "questions": len(questions), "rapports": len(rapports),
          "amendements": sum(x["na"] for x in light), "scrutins": len(scrutins), "deputes": len(deputes), "senateurs": len(senateurs),
          "cc": sum(1 for r in rapports if r["src"] == "CC"), "controle": len(controle)}
dump({"genere": NOW_ISO, "aujourdhui": TODAY_S, "themes": [{"id": k, "l": l} for k, l, _ in THEMES], "dossiers": light, "counts": counts,
      "groupes": {k: GCOL.get(k, "#7f8c8d") for k in sorted({d["g"] for d in deputes})},
      "sources": [{"nom": "Assemblée nationale (open data)", "url": "https://data.assemblee-nationale.fr/"},
                  {"nom": "Sénat (open data et ordre du jour)", "url": "https://data.senat.fr/"},
                  {"nom": "Cour des comptes (publications)", "url": "https://www.ccomptes.fr/fr/publications"}]}, f"{OUT}/core.json")
print(json.dumps(counts, ensure_ascii=False))
