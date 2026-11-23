#!/usr/bin/env python3
"""Alertes e-mail personnalisées des comptes Legitrack (Supabase + Brevo).

Usage : alertes.py <dossier du site>

À chaque collecte (complète ou horaire), après post_build.py :
  1. prévient les administrateurs des nouvelles demandes de compte ;
  2. prévient chaque demandeur de la décision (compte validé ou refusé) ;
  3. envoie à chaque compte validé les nouveautés qui correspondent à ses alertes
     (mission, texte, thématique ou tout), soit dès la collecte, soit dans un
     récapitulatif quotidien envoyé à la première collecte après 8 h (heure de Paris).
Un même événement n'est jamais envoyé deux fois à la même personne (table envois).

Ne fait rien si la configuration manque. Variables :
  SUPABASE_URL                 adresse du projet (variable du dépôt)
  SUPABASE_SERVICE_ROLE_KEY    clé secrète du projet (secret du dépôt, jamais dans le code)
  BREVO_API_KEY                clé d'API Brevo (secret du dépôt)
  ALERTES_FROM                 expéditeur validé dans Brevo, « Legitrack <adresse@domaine> »
  SITE_URL                     facultatif, adresse publique du site
"""
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from email.utils import parseaddr
from html import escape

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from post_build import PARIS, TYPE_L, load, site_url  # noqa: E402

FENETRE_JOURS = 3        # ancienneté maximale d'une nouveauté envoyée
GARDE_ENVOIS_JOURS = 30  # durée de conservation de l'historique d'envoi
MAX_MAILS = 250          # plafond par exécution (offre gratuite Brevo : 300 e-mails par jour)
MAX_LIGNES = 40          # nouveautés détaillées au plus par alerte dans un e-mail
HEURE_QUOTIDIEN = 8      # récapitulatif quotidien à la première collecte après 8 h

CIBLE_L = {"mission": "Mission ou commission", "texte": "Texte suivi", "theme": "Thématique", "tout": "Toutes les nouveautés"}


class Supa:
    def __init__(self, url, key):
        self.url = url.rstrip("/") + "/rest/v1/"
        self.h = {"apikey": key, "Content-Type": "application/json"}
        if not key.startswith("sb_"):
            self.h["Authorization"] = "Bearer " + key

    def req(self, method, path, body=None, extra=None):
        data = json.dumps(body).encode() if body is not None else None
        r = urllib.request.Request(self.url + path, data=data, method=method, headers={**self.h, **(extra or {})})
        with urllib.request.urlopen(r, timeout=60) as resp:
            raw = resp.read()
            return json.loads(raw) if raw else None

    def all(self, path):
        out, step = [], 1000
        while True:
            page = self.req("GET", path, extra={"Range-Unit": "items", "Range": f"{len(out)}-{len(out) + step - 1}"}) or []
            out += page
            if len(page) < step:
                return out

    def patch(self, table, ident, values):
        self.req("PATCH", f"{table}?id=eq.{urllib.parse.quote(ident)}", values, {"Prefer": "return=minimal"})


class Brevo:
    def __init__(self, key, sender):
        name, mail = parseaddr(sender)
        self.key, self.sender = key, {"email": mail, "name": name or "Legitrack"}
        self.sent = 0

    def send(self, to, name, subject, html, text):
        if self.sent >= MAX_MAILS:
            raise RuntimeError("plafond d'envoi atteint pour cette exécution")
        body = {"sender": self.sender, "to": [{"email": to, **({"name": name} if name else {})}],
                "subject": subject, "htmlContent": html, "textContent": text}
        r = urllib.request.Request("https://api.brevo.com/v3/smtp/email", data=json.dumps(body).encode(), method="POST",
                                   headers={"api-key": self.key, "Content-Type": "application/json", "Accept": "application/json"})
        with urllib.request.urlopen(r, timeout=60):
            pass
        self.sent += 1


# ------------------------------------------------------------------ mise en page
A = "color:#3d4ee0;text-decoration:none"


def page(titre, sous_titre, corps, base):
    foot = ('<p style="margin:28px 0 0;font-size:12.5px;line-height:1.5;color:#7c7c86">'
            + (f'Vous recevez cet e-mail parce que vous avez un compte Legitrack. <a href="{escape(base)}#compte" style="{A}">Gérer mes alertes ou supprimer mon compte</a>. ' if base else "")
            + "Données publiques de l'Assemblée nationale, du Sénat et de la Cour des comptes.</p>")
    return ('<!doctype html><html lang="fr"><body style="margin:0;background:#f6f5f1">'
            '<div style="max-width:640px;margin:0 auto;padding:24px 20px;font:15px/1.5 Arial,Helvetica,sans-serif;color:#17171a;background:#ffffff">'
            '<div style="font:600 22px Georgia,serif;color:#17171a;margin:0 0 4px">Legitrack</div>'
            f'<div style="color:#7c7c86;font-size:13px;margin:0 0 18px">{escape(sous_titre)}</div>'
            f'<h1 style="font:600 19px Arial,sans-serif;margin:0 0 12px">{escape(titre)}</h1>{corps}{foot}</div></body></html>')


def bouton(href, label):
    return (f'<p style="margin:20px 0"><a href="{escape(href)}" style="display:inline-block;background:#17171a;color:#ffffff;'
            f'padding:10px 18px;border-radius:10px;font-weight:600;text-decoration:none">{escape(label)}</a></p>')


def lien(o, base):
    if o.get("ds") and base:
        return base + "#texte-" + o["ds"]
    if o.get("mi") and base:
        return base + "#mission-" + o["mi"]
    return o.get("u") or base or "#"


def bloc(alerte, items, base):
    rows = ""
    for o in items[:MAX_LIGNES]:
        ext = o.get("u") if o.get("u") and o.get("k") in ("cr", "rapport", "doc") else None
        rows += ('<tr><td style="padding:10px 0;border-bottom:1px solid #e7e4dc">'
                 f'<div style="font-size:12px;font-weight:600;color:#7c7c86;text-transform:uppercase;letter-spacing:.04em">{escape(TYPE_L.get(o["k"], ""))}</div>'
                 f'<div style="font-size:15px;font-weight:600;line-height:1.35;margin:2px 0;word-break:break-word"><a href="{escape(lien(o, base))}" style="{A};color:#17171a">{escape((o.get("t") or "")[:220])}</a></div>'
                 f'<div style="font-size:13.5px;color:#4a4a52;word-break:break-word">{escape(o.get("s") or "")}'
                 + (f' · <a href="{escape(ext)}" style="{A}">ouvrir le document</a>' if ext else "")
                 + "</div></td></tr>")
    more = len(items) - MAX_LIGNES
    if more > 0:
        rows += f'<tr><td style="padding:10px 0;font-size:13px;color:#7c7c86">Et {more} autre{"s" if more > 1 else ""}, à retrouver sur le site.</td></tr>'
    lab = alerte.get("libelle") or CIBLE_L.get(alerte["cible"], "")
    return (f'<h2 style="font:600 16px Arial,sans-serif;color:#17171a;margin:24px 0 2px;word-break:break-word">{escape(lab)} '
            f'<span style="color:#7c7c86;font-weight:400">{len(items)}</span></h2>'
            + (f'<div style="font-size:12.5px;color:#7c7c86">{escape(CIBLE_L.get(alerte["cible"], ""))}</div>' if lab != CIBLE_L.get(alerte["cible"]) else "")
            + f'<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="border-collapse:collapse">{rows}</table>')


def texte_brut(groupes, base):
    out = []
    for a, L in groupes:
        out.append((a.get("libelle") or CIBLE_L.get(a["cible"], "")).upper())
        for o in L[:MAX_LIGNES]:
            out.append(f"- {TYPE_L.get(o['k'], '')} : {o.get('t', '')} · {o.get('s', '')}\n  {lien(o, base)}")
        out.append("")
    if base:
        out.append(f"Gérer mes alertes : {base}#compte")
    return "\n".join(out)


# ------------------------------------------------------------------ correspondance
def correspond(a, o):
    if a.get("types") and o.get("k") not in a["types"]:
        return False
    c, i = a["cible"], a.get("cible_id") or ""
    if c == "tout":
        return True
    if c == "mission":
        return o.get("mi") == i
    if c == "texte":
        return o.get("ds") == i
    if c == "theme":
        return i in (o.get("th") or [])
    return False


def main(site):
    url = os.environ.get("SUPABASE_URL", "").strip()
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    bkey = os.environ.get("BREVO_API_KEY", "").strip()
    sender = os.environ.get("ALERTES_FROM", "").strip()
    if not (url and key and bkey and sender):
        print("Alertes : configuration Supabase ou Brevo absente, pas d'envoi")
        return
    db, mail, base = Supa(url, key), Brevo(bkey, sender), site_url()
    now = datetime.now(PARIS)
    today = now.date().isoformat()

    profils = db.all("profils?select=id,email,nom,statut,admin,admin_notifie,validation_notifiee,quotidien_le&order=cree_le")
    admins = [p for p in profils if p["admin"] and p["statut"] == "valide"]

    # 1. nouvelles demandes de compte -> administrateurs
    att = [p for p in profils if p["statut"] == "en_attente" and not p["admin_notifie"]]
    if att and admins:
        n = len(att)
        lst = "".join(f'<li style="margin:4px 0;word-break:break-word"><b>{escape(p.get("nom") or "Sans nom")}</b> · {escape(p["email"])}</li>' for p in att)
        html = page(f"{n} demande{'s' if n > 1 else ''} de compte à valider", "Administration",
                    f'<ul style="padding-left:18px;margin:0">{lst}</ul>' + (bouton(base + "#admin", "Valider ou refuser") if base else ""), base)
        txt = "\n".join(f"- {p.get('nom') or 'Sans nom'} · {p['email']}" for p in att) + (f"\n\nValider ou refuser : {base}#admin" if base else "")
        for a in admins:
            mail.send(a["email"], a.get("nom"), f"Legitrack · {n} demande{'s' if n > 1 else ''} de compte", html, txt)
        for p in att:
            db.patch("profils", p["id"], {"admin_notifie": True})
        print(f"Alertes : {n} demande(s) de compte signalée(s) à {len(admins)} administrateur(s)")

    # 2. décision -> demandeur
    for p in profils:
        if p["validation_notifiee"] or p["statut"] not in ("valide", "refuse"):
            continue
        if p["statut"] == "valide":
            html = page("Votre compte est validé", "Bienvenue",
                        "<p>Vous pouvez vous connecter, retrouver vos préférences sur tous vos postes et créer des alertes e-mail sur les missions, "
                        "les textes et les thématiques qui vous intéressent.</p>" + (bouton(base + "#compte", "Créer mes alertes") if base else ""), base)
            mail.send(p["email"], p.get("nom"), "Legitrack · votre compte est validé", html,
                      "Votre compte Legitrack est validé." + (f" Créez vos alertes : {base}#compte" if base else ""))
        else:
            html = page("Votre demande de compte n'a pas été acceptée", "Demande de compte",
                        "<p>L'administrateur de Legitrack n'a pas validé votre demande. Le site reste consultable librement, sans compte.</p>", base)
            mail.send(p["email"], p.get("nom"), "Legitrack · demande de compte", html,
                      "Votre demande de compte Legitrack n'a pas été acceptée. Le site reste consultable librement, sans compte.")
        db.patch("profils", p["id"], {"validation_notifiee": True})

    # 3. alertes
    valides = {p["id"]: p for p in profils if p["statut"] == "valide"}
    alertes = [a for a in db.all("alertes?select=id,user_id,cible,cible_id,libelle,types,frequence,cree_le") if a["user_id"] in valides]
    ch = load(os.path.join(site, "changes.json"), {}) or {}
    lim = (now - timedelta(days=FENETRE_JOURS)).isoformat(timespec="minutes")
    items = [o for o in ch.get("items", []) if o.get("ts", "") >= lim]
    deja = set()
    if alertes and items:
        since = (datetime.now(timezone.utc) - timedelta(days=FENETRE_JOURS + 1)).isoformat()
        for r in db.all("envois?select=user_id,item_id&envoye_le=gte." + urllib.parse.quote(since)):
            deja.add((r["user_id"], r["item_id"]))
    quotidien = now.hour >= HEURE_QUOTIDIEN
    par_user = {}
    for a in alertes:
        par_user.setdefault(a["user_id"], []).append(a)
    n_mails = n_items = 0
    for uid, L in par_user.items():
        p = valides[uid]
        recap = quotidien and p.get("quotidien_le") != today
        groupes, envoyes = [], set()
        # un événement pris par une alerte n'est pas répété dans une autre du même e-mail
        for a in sorted(L, key=lambda a: ({"mission": 0, "texte": 1, "theme": 2, "tout": 3}[a["cible"]], a.get("libelle") or "")):
            if a["frequence"] == "quotidienne" and not recap:
                continue
            # les événements antérieurs à la création de l'alerte ne sont pas envoyés
            cree = datetime.fromisoformat(a["cree_le"].replace("Z", "+00:00")).astimezone(PARIS).isoformat(timespec="minutes")
            M = [o for o in items if o["ts"] >= cree and (uid, o["id"]) not in deja and o["id"] not in envoyes and correspond(a, o)]
            if M:
                M.sort(key=lambda o: (o.get("e") or o.get("d") or "", o.get("t") or ""))
                groupes.append((a, M))
                envoyes.update(o["id"] for o in M)
        if recap:
            db.patch("profils", uid, {"quotidien_le": today})
        if not groupes:
            continue
        n = len(envoyes)
        cibles = [g[0].get("libelle") or CIBLE_L[g[0]["cible"]] for g in groupes]
        sujet = f"Legitrack · {n} nouveauté{'s' if n > 1 else ''} · " + (cibles[0][:70] + ("…" if len(cibles[0]) > 70 else "") if len(cibles) == 1 else f"{len(cibles)} alertes")
        html = page(f"{n} nouveauté{'s' if n > 1 else ''} pour vos alertes", f"Le {now.day}/{now.month:02d}/{now.year} à {now.hour} h {now.minute:02d}",
                    "".join(bloc(a, M, base) for a, M in groupes), base)
        try:
            mail.send(p["email"], p.get("nom"), sujet, html, texte_brut(groupes, base))
        except RuntimeError as e:
            print(f"Alertes : {e}", file=sys.stderr)
            break
        db.req("POST", "envois", [{"user_id": uid, "item_id": i} for i in envoyes], {"Prefer": "resolution=ignore-duplicates,return=minimal"})
        n_mails += 1
        n_items += n
    old = (datetime.now(timezone.utc) - timedelta(days=GARDE_ENVOIS_JOURS)).isoformat()
    db.req("DELETE", "envois?envoye_le=lt." + urllib.parse.quote(old), extra={"Prefer": "return=minimal"})
    print(f"Alertes : {len(alertes)} alertes actives · {n_mails} e-mail(s) envoyé(s) · {n_items} nouveauté(s) · {mail.sent} e-mail(s) au total")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    try:
        main(sys.argv[1])
    except urllib.error.HTTPError as e:  # les alertes ne doivent jamais bloquer la publication du site
        print(f"Alertes non envoyées : HTTP {e.code} {e.read()[:300]!r}", file=sys.stderr)
    except Exception as e:
        print(f"Alertes non envoyées : {e}", file=sys.stderr)
