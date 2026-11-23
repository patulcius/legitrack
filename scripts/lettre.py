#!/usr/bin/env python3
"""Lettre quotidienne par e-mail : les nouveautés depuis la lettre précédente, par thématique.

Usage : lettre.py <dossier du site> <dossier d'état>

Ne fait rien si les secrets ne sont pas configurés. Secrets du dépôt (Settings > Secrets > Actions) :
  SMTP_HOST, SMTP_PORT (587 par défaut), SMTP_USER, SMTP_PASS, LETTRE_FROM
  LETTRE_DEST : destinataires et thématiques, séparés par des points-virgules, par exemple
      alice@exemple.fr:securite,justice; equipe@exemple.fr:*
      (* ou rien = toutes les thématiques)
Les adresses restent dans les secrets : elles ne sont jamais écrites dans le dépôt ni sur le site.
Variable facultative : SITE_URL (lien vers le site dans la lettre).
"""
import json
import os
import smtplib
import ssl
import sys
from datetime import datetime, timedelta
from email.message import EmailMessage
from html import escape

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from post_build import PARIS, TYPE_L, load, site_url  # noqa: E402

ORDRE = ["delai", "agenda", "etape", "sort", "amdt", "doc", "rapport", "reponse", "question"]
SECTIONS = [
    ("Échéances ajoutées à l'agenda", {"delai", "agenda"}),
    ("Textes : étapes, documents et amendements", {"etape", "sort", "amdt", "doc"}),
    ("Publications", {"rapport"}),
    ("Questions au Gouvernement", {"reponse", "question"}),
]
MAX_SECTION = 25


def parse_dest(s):
    out = []
    for part in (s or "").replace("\n", ";").split(";"):
        part = part.strip()
        if not part or "@" not in part:
            continue
        mail, _, th = part.partition(":")
        themes = [t.strip() for t in th.split(",") if t.strip() and t.strip() != "*"]
        out.append((mail.strip(), themes))
    return out


def render(items, themes_l, base, depuis):
    css_a = "color:#3d4ee0;text-decoration:none"
    head = (f'<div style="font:600 22px Georgia,serif;color:#17171a;margin:0 0 4px">Legitrack</div>'
            f'<div style="color:#7c7c86;font-size:13px;margin:0 0 18px">{escape(themes_l)} · nouveautés depuis le {escape(depuis)}</div>')
    body = ""
    for titre, ks in SECTIONS:
        L = [o for o in items if o["k"] in ks]
        if not L:
            continue
        L.sort(key=lambda o: (ORDRE.index(o["k"]), o.get("e") or "", o.get("t") or ""))
        rows = ""
        for o in L[:MAX_SECTION]:
            link = (base + "#texte-" + o["ds"]) if o.get("ds") and base else (base + "#mission-" + o["mi"]) if o.get("mi") and base else (o.get("u") or base)
            t = escape((o.get("t") or "")[:220])
            rows += ('<tr><td style="padding:10px 0;border-bottom:1px solid #e7e4dc">'
                     f'<div style="font-size:12px;font-weight:600;color:#7c7c86;text-transform:uppercase;letter-spacing:.04em">{escape(TYPE_L.get(o["k"], ""))}</div>'
                     f'<div style="font-size:15px;font-weight:600;line-height:1.35;margin:2px 0;word-break:break-word"><a href="{escape(link or "#")}" style="{css_a};color:#17171a">{t}</a></div>'
                     f'<div style="font-size:13.5px;color:#4a4a52;word-break:break-word">{escape(o.get("s") or "")}</div></td></tr>')
        more = len(L) - MAX_SECTION
        if more > 0:
            rows += f'<tr><td style="padding:10px 0;font-size:13px;color:#7c7c86">Et {more} autre{"s" if more > 1 else ""}, à retrouver sur le site.</td></tr>'
        body += (f'<h2 style="font:600 16px Arial,sans-serif;color:#17171a;margin:26px 0 4px">{escape(titre)} <span style="color:#7c7c86;font-weight:400">{len(L)}</span></h2>'
                 f'<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="border-collapse:collapse">{rows}</table>')
    foot = (f'<p style="margin:28px 0 0;font-size:13px;color:#7c7c86">Ouvrir <a href="{escape(base + "#nouveautes")}" style="{css_a}">les nouveautés sur le site</a>. '
            'Données publiques de l\'Assemblée nationale, du Sénat et de la Cour des comptes.</p>') if base else ""
    return ('<!doctype html><html lang="fr"><body style="margin:0;background:#f6f5f1">'
            '<div style="max-width:640px;margin:0 auto;padding:24px 20px;font:15px/1.5 Arial,Helvetica,sans-serif;color:#17171a;background:#ffffff">'
            f"{head}{body}{foot}</div></body></html>")


def main(site, state):
    dest = parse_dest(os.environ.get("LETTRE_DEST", ""))
    host = os.environ.get("SMTP_HOST", "").strip()
    if not dest or not host:
        print("Lettre : secrets SMTP_HOST et LETTRE_DEST absents, pas d'envoi")
        return
    ch = load(os.path.join(site, "changes.json"), {}) or {}
    core = load(os.path.join(site, "core.json"), {}) or {}
    tl = {t["id"]: t["l"] for t in core.get("themes", [])}
    mark = os.path.join(state, "lettre.json")
    last = (load(mark, {}) or {}).get("ts")
    now = datetime.now(PARIS)
    if not last:
        last = (now - timedelta(days=1)).isoformat(timespec="minutes")
    items = [o for o in ch.get("items", []) if o["ts"] > last and o["k"] != "question"]
    base = site_url()
    depuis = datetime.fromisoformat(last).strftime("%d/%m à %H h %M").replace(" 0", " ")
    port = int(os.environ.get("SMTP_PORT", "587") or 587)
    sender = os.environ.get("LETTRE_FROM") or os.environ.get("SMTP_USER", "")
    sent = 0
    ctx = ssl.create_default_context()
    with (smtplib.SMTP_SSL(host, port, context=ctx, timeout=60) if port == 465 else smtplib.SMTP(host, port, timeout=60)) as s:
        if port != 465:
            s.starttls(context=ctx)
        if os.environ.get("SMTP_USER"):
            s.login(os.environ["SMTP_USER"], os.environ.get("SMTP_PASS", ""))
        for mail, themes in dest:
            L = [o for o in items if not themes or set(themes) & set(o.get("th") or [])]
            if not L:
                continue
            lab = ", ".join(tl.get(t, t) for t in themes) if themes else "Toutes les thématiques"
            msg = EmailMessage()
            msg["Subject"] = f"Legitrack · {len(L)} nouveauté{'s' if len(L) > 1 else ''} · {now.strftime('%d/%m/%Y')}"
            msg["From"] = sender
            msg["To"] = mail
            msg.set_content("Les nouveautés de Legitrack sont lisibles dans un client de messagerie compatible HTML"
                            + (f" ou sur {base}#nouveautes" if base else "") + ".")
            msg.add_alternative(render(L, lab, base, depuis), subtype="html")
            s.send_message(msg)
            sent += 1
    os.makedirs(state, exist_ok=True)
    with open(mark, "w", encoding="utf-8") as f:
        json.dump({"ts": now.isoformat(timespec="minutes")}, f)
    print(f"Lettre envoyée à {sent} destinataire{'s' if sent > 1 else ''}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    try:
        main(sys.argv[1], sys.argv[2])
    except Exception as e:  # la lettre ne doit jamais bloquer la publication du site
        print(f"Lettre non envoyée : {e}", file=sys.stderr)
