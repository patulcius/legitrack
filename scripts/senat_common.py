"""Fonctions partagées pour les données du Sénat."""
import csv, io, re, datetime as dt

KW = re.compile(
    r"gendarm|police nationale|policiers?\b|polices? municipales?|policiers municipaux|forces de l.ordre|forces de sécurité|"
    r"sécurité intérieure|maintien de l.ordre|refus d.obtemp|vidéoprotection|vidéosurveillance|narcotrafic|gardes? champêtres?|"
    r"légitime défense|sécurité privée|troubl\w* l.ordre public|\bSécurités\b|renseignement|contrôles? d.identité", re.I)
EXCLUDE = re.compile(r"ordre public des baux|police de l.environnement|salubrité des immeubles|sécurité sociale|sécurité civile$", re.I)
SINCE = dt.date(2024, 10, 1)

def norm_url(u):
    return re.sub(r"^http://", "https://", (u or "").strip())

def read_csv(path, sep=";"):
    with open(path, encoding="latin1") as f:
        t = f.read()
    if t.startswith("sep="):
        t = t.split("\n", 1)[1]
    return list(csv.DictReader(io.StringIO(t), delimiter=sep))

def fr_date(s):
    s = (s or "").strip()
    try:
        if re.match(r"\d{2}/\d{2}/\d{4}", s): return dt.date(int(s[6:10]), int(s[3:5]), int(s[:2]))
        if re.match(r"\d{4}-\d{2}-\d{2}", s): return dt.date.fromisoformat(s[:10])
    except ValueError:
        return None
    return None

def is_rel(text, themes=""):
    return (bool(KW.search(text)) or "Police et sécurité" in (themes or "")) and not EXCLUDE.search(text)

def relevant_senat_dossiers(folder):
    rows = []
    for r in read_csv(f"{folder}/dossiers-legislatifs.csv"):
        d = fr_date(r.get("Date initiale"))
        if d and d >= SINCE and is_rel(r["Titre"], r.get("Thèmes")):
            rows.append(r)
    return rows
