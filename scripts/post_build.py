#!/usr/bin/env python3
"""Après la construction du site : journal des nouveautés, flux RSS et agendas .ics.

Usage : post_build.py <dossier du site> <dossier d'état>

- Le dossier d'état (gardé en cache entre deux exécutions) contient l'instantané de la
  veille (snapshot.json) et le journal des changements (journal.json).
- Sorties dans le site :
    changes.json            journal des nouveautés des 21 derniers jours
    feeds/tout.xml          flux RSS de toutes les nouveautés
    feeds/<thème>.xml       un flux par thématique
    feeds/t/<texte>.xml     un flux par texte actif ou récemment modifié
    ics/tout.ics            agenda complet (délais, séances, commissions, auditions)
    ics/<thème>.ics         un agenda par thématique
    ics/t/<texte>.ics       un agenda par texte ayant des événements
Variables : SITE_URL (adresse publique du site ; déduite de GITHUB_REPOSITORY à défaut).
"""
import glob
import hashlib
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from xml.sax.saxutils import escape

try:
    from zoneinfo import ZoneInfo
    PARIS = ZoneInfo("Europe/Paris")
except Exception:  # pragma: no cover
    PARIS = timezone(timedelta(hours=1))

GARDE_JOURS = 21          # durée de conservation du journal
MAX_PAR_TEXTE = 4         # étapes ou documents signalés au plus par texte et par exécution
MAX_FLUX = 120            # articles par flux RSS

KIND_L = {
    "dl_com": "Délai de dépôt des amendements en commission",
    "dl_seance": "Délai de dépôt des amendements en séance",
    "seance": "Séance publique",
    "commission": "Examen en commission",
    "audition": "Audition",
    "reunion": "Réunion",
}
TYPE_L = {
    "etape": "Nouvelle étape",
    "doc": "Nouveau document",
    "amdt": "Amendements déposés",
    "sort": "Amendements examinés",
    "agenda": "Inscrit à l'agenda",
    "delai": "Délai d'amendement",
    "rapport": "Publication",
    "question": "Question",
    "reponse": "Réponse du Gouvernement",
}


def site_url():
    u = os.environ.get("SITE_URL", "").strip()
    if not u:
        repo = os.environ.get("GITHUB_REPOSITORY", "")
        if "/" in repo:
            owner, name = repo.split("/", 1)
            u = f"https://{owner.lower()}.github.io/{name}/"
    if u and not u.endswith("/"):
        u += "/"
    return u


def load(p, d=None):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return d


def save(p, obj, compact=True):
    os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":") if compact else None)
    os.replace(tmp, p)


def write(p, text):
    os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
    with open(p, "w", encoding="utf-8", newline="") as f:
        f.write(text)


def h(*parts):
    return hashlib.sha1("|".join(str(x) for x in parts).encode()).hexdigest()[:12]


def ev_key(e):
    return h(e.get("d", "")[:10], e.get("k"), e.get("ds") or "", e.get("t", "")[:120], e.get("org") or "")


def plur(n, s, p=None):
    return f"{n} {s if n == 1 else (p or s + 's')}"


def fr_date(s):
    try:
        d = datetime.strptime(s[:10], "%Y-%m-%d")
    except (TypeError, ValueError):
        return ""
    mois = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
            "septembre", "octobre", "novembre", "décembre"]
    jours = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
    out = f"{jours[d.weekday()]} {d.day} {mois[d.month - 1]}"
    if len(s) >= 16 and s[11:16] != "00:00":
        hh, mm = int(s[11:13]), s[14:16]
        out += f" à {hh} h" + ("" if mm == "00" else f" {mm}")
    return out


# ---------------------------------------------------------------- instantané

def snapshot(site):
    core = load(os.path.join(site, "core.json"), {})
    dossiers = {d["id"]: d for d in core.get("dossiers", [])}
    det = {}
    for f in glob.glob(os.path.join(site, "dos", "*.json")):
        det.update(load(f, {}) or {})
    snap = {"genere": core.get("genere"), "dos": {}, "ag": {}, "rap": [], "q": {}}
    for i, d in dossiers.items():
        x = det.get(i, {})
        am = x.get("amdt") or {}
        snap["dos"][i] = {
            "na": d.get("na", 0),
            "s": am.get("s", {}),
            "tl": [h(t.get("d"), t.get("c"), t.get("l")) for t in x.get("timeline", [])],
            "doc": [h(o.get("url"), o.get("num"), o.get("n")) for o in x.get("documents", [])],
        }
    for e in load(os.path.join(site, "agenda.json"), []) or []:
        snap["ag"][ev_key(e)] = 1
    snap["rap"] = sorted({r.get("url") or h(r.get("t"), r.get("d")) for r in load(os.path.join(site, "rapports.json"), []) or []})
    for q in load(os.path.join(site, "questions.json"), []) or []:
        snap["q"][q.get("id") or h(q.get("ch"), q.get("n"))] = q.get("st") or "a"
    return snap, core, dossiers, det


def diff(prev, cur, core, dossiers, det, site, now_iso):
    """Événements nouveaux entre deux instantanés."""
    out = []
    today = core.get("aujourdhui") or now_iso[:10]

    def base(i):
        d = dossiers.get(i, {})
        return {"ds": i, "th": d.get("th", []), "ch": d.get("ch", "AN"), "t": d.get("t", "")}

    for i, c in cur["dos"].items():
        p = prev["dos"].get(i)
        x = det.get(i, {})
        if p is None:
            d = dossiers.get(i, {})
            if (d.get("dep") or "") >= (datetime.fromisoformat(today) - timedelta(days=10)).date().isoformat():
                out.append({**base(i), "k": "etape", "s": f"Nouveau texte déposé : {d.get('ty', '')}".strip(" :"), "d": d.get("dep")})
            continue
        seen = set(p["tl"])
        new = [t for t in x.get("timeline", []) if (t.get("d") or "")[:10] <= today
               and h(t.get("d"), t.get("c"), t.get("l")) not in seen]
        for t in new[-MAX_PAR_TEXTE:]:
            lab = (t.get("l") or "").rstrip(".")
            org = t.get("o") or ""
            s = lab + (f" ({org})" if org and org not in lab and org not in ("Assemblée", "Sénat") else "")
            out.append({**base(i), "k": "etape", "s": s, "d": (t.get("d") or "")[:16]})
        seen = set(p["doc"])
        newd = [o for o in x.get("documents", []) if h(o.get("url"), o.get("num"), o.get("n")) not in seen]
        for o in newd[-MAX_PAR_TEXTE:]:
            s = (o.get("n") or "Document") + (f" n° {o['num']}" if o.get("num") else "") + (f", {o['ch']}" if o.get("ch") else "")
            out.append({**base(i), "k": "doc", "s": s, "d": o.get("d"), "u": o.get("url")})
        dn = c["na"] - p["na"]
        if dn > 0:
            out.append({**base(i), "k": "amdt", "n": dn, "s": f"{plur(dn, 'nouvel amendement', 'nouveaux amendements')} publié{'s' if dn > 1 else ''}"})
        parts = []
        for so, lab in (("Adopté", "adopté"), ("Rejeté", "rejeté"), ("Tombé", "tombé"), ("Retiré", "retiré")):
            k = c["s"].get(so, 0) - p["s"].get(so, 0)
            if k > 0:
                parts.append(f"{k} {lab}{'s' if k > 1 else ''}")
        if parts:
            out.append({**base(i), "k": "sort", "s": "Amendements : " + ", ".join(parts)})

    for e in load(os.path.join(site, "agenda.json"), []) or []:
        k = ev_key(e)
        if k in prev["ag"] or (e.get("d") or "")[:10] < today:
            continue
        d = dossiers.get(e.get("ds") or "", {})
        kind = e.get("k")
        lab = KIND_L.get(kind, "Réunion")
        out.append({
            "k": "delai" if kind.startswith("dl_") else "agenda",
            "ds": e.get("ds"), "th": e.get("th") or d.get("th", []), "ch": e.get("ch", "AN"),
            "t": d.get("t") or e.get("t", ""),
            "s": f"{lab}, {fr_date(e.get('d', ''))}" + ("" if d else f" · {e.get('org') or ''}".rstrip(" ·")),
            "e": e.get("d"),
        })

    prev_r = set(prev["rap"])
    for r in load(os.path.join(site, "rapports.json"), []) or []:
        k = r.get("url") or h(r.get("t"), r.get("d"))
        if k in prev_r:
            continue
        src = r.get("src")
        who = r.get("jur") or {"AN": "Assemblée nationale", "SN": "Sénat", "CC": "Cour des comptes"}.get(src, "")
        out.append({"k": "rapport", "th": r.get("th", []), "ch": src or "CC", "t": r.get("t", ""),
                    "s": " · ".join(x for x in (r.get("ty"), who) if x), "u": r.get("url"), "d": r.get("d")})

    for q in load(os.path.join(site, "questions.json"), []) or []:
        k = q.get("id") or h(q.get("ch"), q.get("n"))
        was = prev["q"].get(k)
        st = q.get("st") or "a"
        if was is None or (st == "r" and was != "r"):
            kind = "question" if was is None else "reponse"
            out.append({"k": kind, "th": q.get("th", []), "ch": q.get("ch", "AN"), "t": q.get("an") or q.get("rub") or "",
                        "s": f"{q.get('ty')} n° {q.get('n')} · {q.get('au', '')}" + (f" · {q['m']}" if q.get("m") else ""),
                        "u": q.get("url") or f"https://www.assemblee-nationale.fr/dyn/17/questions/{q.get('id')}",
                        "ai": q.get("ai"), "d": q.get("r") if kind == "reponse" else q.get("d")})
    uniq, seen_k = [], set()
    for o in out:
        key = (o["k"], o.get("ds"), o.get("t") if not o.get("ds") else "", o.get("s"), o.get("u"))
        if key in seen_k:
            continue
        seen_k.add(key)
        uniq.append(o)
    out = uniq
    for o in out:
        o["ts"] = now_iso
        o["id"] = h(o["k"], o.get("ds"), o.get("t"), o.get("s"), o.get("u"), o.get("d"), o.get("e"))
        for f in ("ds", "u", "ai", "d", "e", "n"):
            if not o.get(f):
                o.pop(f, None)
    return out


def seed(core, dossiers, det, site, now):
    """Première exécution : reconstitue les nouveautés des 3 derniers jours à partir des dates."""
    lim = (now - timedelta(days=3)).date().isoformat()
    empty = {"dos": {}, "ag": {}, "rap": [], "q": {}}
    for i in dossiers:
        x = det.get(i, {})
        am = x.get("amdt") or {}
        empty["dos"][i] = {
            "na": dossiers[i].get("na", 0) - dossiers[i].get("nr", 0) if dossiers[i].get("nr") else dossiers[i].get("na", 0),
            "s": am.get("s", {}),
            "tl": [h(t.get("d"), t.get("c"), t.get("l")) for t in x.get("timeline", []) if (t.get("d") or "")[:10] < lim],
            "doc": [h(o.get("url"), o.get("num"), o.get("n")) for o in x.get("documents", []) if (o.get("d") or "")[:10] < lim],
        }
    empty["rap"] = [r.get("url") or h(r.get("t"), r.get("d")) for r in load(os.path.join(site, "rapports.json"), []) or [] if (r.get("d") or "") < lim]
    for q in load(os.path.join(site, "questions.json"), []) or []:
        k = q.get("id") or h(q.get("ch"), q.get("n"))
        if (q.get("d") or "") < lim:
            empty["q"][k] = "r" if q.get("st") == "r" and (q.get("r") or "") < lim else "a"
    for e in load(os.path.join(site, "agenda.json"), []) or []:
        empty["ag"][ev_key(e)] = 1  # pas d'agenda rétroactif
    evs = diff(empty, snapshot(site)[0], core, dossiers, det, site, now.isoformat(timespec="minutes"))
    for o in evs:  # date réelle de l'événement quand elle est connue
        if o.get("d") and o["d"][:10] >= lim:
            o["ts"] = (o["d"][:10] + "T08:00") if len(o["d"]) < 16 else o["d"][:16]
            o["ts"] = min(datetime.fromisoformat(o["ts"]).replace(tzinfo=PARIS), now).isoformat(timespec="minutes")
    return evs


# ---------------------------------------------------------------- RSS

def rss(title, desc, link, items, base):
    now = format_datetime(datetime.now(timezone.utc))
    out = ['<?xml version="1.0" encoding="utf-8"?>',
           '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom"><channel>',
           f"<title>{escape(title)}</title><link>{escape(link)}</link><description>{escape(desc)}</description>",
           f"<language>fr</language><lastBuildDate>{now}</lastBuildDate>"]
    for o in items[:MAX_FLUX]:
        lk = (base + "#texte-" + o["ds"]) if o.get("ds") and base else (o.get("u") or link)
        lab = TYPE_L.get(o["k"], "Nouveauté")
        try:
            pub = format_datetime(datetime.fromisoformat(o["ts"]))
        except ValueError:
            pub = now
        body = f"<p><b>{escape(lab)}</b> : {escape(o.get('s', ''))}</p>"
        if o.get("u") and o.get("ds"):
            body += f'<p><a href="{escape(o["u"])}">Document officiel</a></p>'
        out.append("<item>"
                   f"<title>{escape(lab + ' · ' + (o.get('t') or '')[:180])}</title>"
                   f"<link>{escape(lk)}</link>"
                   f'<guid isPermaLink="false">{o["id"]}-{o["ts"][:10]}</guid>'
                   f"<pubDate>{pub}</pubDate>"
                   f"<description>{escape(body)}</description></item>")
    out.append("</channel></rss>")
    return "\n".join(out)


# ---------------------------------------------------------------- iCalendar

VTZ = ("BEGIN:VTIMEZONE\r\nTZID:Europe/Paris\r\nBEGIN:DAYLIGHT\r\nTZOFFSETFROM:+0100\r\nTZOFFSETTO:+0200\r\n"
       "TZNAME:CEST\r\nDTSTART:19700329T020000\r\nRRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=-1SU\r\nEND:DAYLIGHT\r\n"
       "BEGIN:STANDARD\r\nTZOFFSETFROM:+0200\r\nTZOFFSETTO:+0100\r\nTZNAME:CET\r\nDTSTART:19701025T030000\r\n"
       "RRULE:FREQ=YEARLY;BYMONTH=10;BYDAY=-1SU\r\nEND:STANDARD\r\nEND:VTIMEZONE\r\n")


def ics_text(s):
    return (s or "").replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\r", "").replace("\n", "\\n")


def fold(line):
    b = line.encode("utf-8")
    if len(b) <= 74:
        return line + "\r\n"
    parts, cur = [], b""
    for ch in line:
        c = ch.encode("utf-8")
        if len(cur) + len(c) > (74 if not parts else 73):
            parts.append(cur.decode("utf-8"))
            cur = b""
        cur += c
    parts.append(cur.decode("utf-8"))
    return "\r\n ".join(parts) + "\r\n"


def ics(name, events, dossiers, base, stamp):
    out = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Veille parlementaire//FR", "CALSCALE:GREGORIAN",
           "METHOD:PUBLISH", f"X-WR-CALNAME:{ics_text(name)}", "X-WR-TIMEZONE:Europe/Paris",
           "REFRESH-INTERVAL;VALUE=DURATION:PT6H", "X-PUBLISHED-TTL:PT6H"]
    body = "".join(fold(l) for l in out) + VTZ
    for e in events:
        d = e.get("d") or ""
        if len(d) < 10:
            continue
        dos = dossiers.get(e.get("ds") or "", {})
        kind = e.get("k", "reunion")
        lab = KIND_L.get(kind, "Réunion")
        titre = dos.get("t") or e.get("t") or lab
        short = {"dl_com": "Délai amdts commission", "dl_seance": "Délai amdts séance", "seance": "Séance",
                 "commission": "Commission", "audition": "Audition", "reunion": "Réunion"}.get(kind, "Réunion")
        ch = "Sénat" if e.get("ch") == "SN" else "AN"
        summary = f"{short} ({ch}) · {titre}"
        desc = [lab]
        if dos and e.get("t") and e.get("t") not in (titre, lab):
            desc.append(e["t"])
        if e.get("org"):
            desc.append(e["org"])
        if e.get("calc"):
            desc.append("Délai calculé selon le Règlement, à confirmer.")
        if dos and base:
            desc.append(base + "#texte-" + e["ds"])
        lines = ["BEGIN:VEVENT", f"UID:{ev_key(e)}@veille-parlementaire", f"DTSTAMP:{stamp}"]
        ymd = d[:10].replace("-", "")
        if len(d) < 16 or d[11:16] == "00:00":
            nxt = (datetime.strptime(d[:10], "%Y-%m-%d") + timedelta(days=1)).strftime("%Y%m%d")
            lines += [f"DTSTART;VALUE=DATE:{ymd}", f"DTEND;VALUE=DATE:{nxt}"]
        else:
            st = datetime.strptime(d[:16], "%Y-%m-%dT%H:%M")
            dur = timedelta(minutes=30) if kind.startswith("dl_") else timedelta(hours=2)
            lines += [f"DTSTART;TZID=Europe/Paris:{st.strftime('%Y%m%dT%H%M%S')}",
                      f"DTEND;TZID=Europe/Paris:{(st + dur).strftime('%Y%m%dT%H%M%S')}"]
        lines += [f"SUMMARY:{ics_text(summary)}", f"DESCRIPTION:{ics_text(chr(10).join(desc))}"]
        if e.get("lieu"):
            lines.append(f"LOCATION:{ics_text(e['lieu'])}")
        if dos and base:
            lines.append(f"URL:{base}#texte-{e['ds']}")
        lines.append(f"CATEGORIES:{ics_text(lab)}")
        if kind.startswith("dl_"):
            lines += ["BEGIN:VALARM", "ACTION:DISPLAY", f"DESCRIPTION:{ics_text(short)}", "TRIGGER:-P1D", "END:VALARM"]
        lines.append("END:VEVENT")
        body += "".join(fold(l) for l in lines)
    return body + "END:VCALENDAR\r\n"


# ---------------------------------------------------------------- principal

def main(site, state):
    now = datetime.now(PARIS).replace(second=0, microsecond=0)
    now_iso = now.isoformat(timespec="minutes")
    base = site_url()
    cur, core, dossiers, det = snapshot(site)
    prev = load(os.path.join(state, "snapshot.json"))
    journal = load(os.path.join(state, "journal.json"), []) or []

    if prev is None:
        new = seed(core, dossiers, det, site, now)
        print(f"Journal initialisé : {len(new)} nouveautés reconstituées")
    else:
        # une collecte incomplète ne doit pas produire de fausses nouveautés : on garde ce qui manque
        for k in ("dos", "ag", "q"):
            if not cur[k] and prev.get(k):
                cur[k] = prev[k]
        if not cur["rap"] and prev.get("rap"):
            cur["rap"] = prev["rap"]
        new = diff(prev, cur, core, dossiers, det, site, now_iso)
        print(f"{len(new)} nouveautés depuis la collecte précédente")

    known = {o["id"] for o in journal}
    fresh = []
    for o in new:
        if o["id"] not in known:
            known.add(o["id"])
            fresh.append(o)
    journal = fresh + journal
    lim = (now - timedelta(days=GARDE_JOURS)).isoformat(timespec="minutes")
    journal = sorted((o for o in journal if o["ts"] >= lim), key=lambda o: o["ts"], reverse=True)
    save(os.path.join(state, "journal.json"), journal)
    save(os.path.join(state, "snapshot.json"), cur)
    save(os.path.join(site, "changes.json"), {"genere": now_iso, "items": journal})

    # flux RSS
    themes = core.get("themes", [])
    home = base or "./"
    write(os.path.join(site, "feeds", "tout.xml"),
          rss("Veille parlementaire · toutes les nouveautés", "Nouveautés à l'Assemblée nationale, au Sénat et à la Cour des comptes", home, journal, base))
    for t in themes:
        L = [o for o in journal if t["id"] in (o.get("th") or [])]
        write(os.path.join(site, "feeds", f"{t['id']}.xml"),
              rss(f"Veille parlementaire · {t['l']}", f"Nouveautés de la thématique « {t['l']} »", home, L, base))
    by_dos = {}
    for o in journal:
        if o.get("ds"):
            by_dos.setdefault(o["ds"], []).append(o)
    n_feeds = 0
    for i, d in dossiers.items():
        if not d.get("ac") and i not in by_dos:
            continue
        write(os.path.join(site, "feeds", "t", f"{i}.xml"),
              rss(f"Veille · {d.get('t', '')[:120]}", "Nouveautés sur ce texte", (base + "#texte-" + i) if base else home, by_dos.get(i, []), base))
        n_feeds += 1

    # agendas .ics (30 jours passés et tout le futur)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    since = (now - timedelta(days=30)).date().isoformat()
    ag = sorted((e for e in load(os.path.join(site, "agenda.json"), []) or [] if (e.get("d") or "")[:10] >= since), key=lambda e: e["d"])
    for e in ag:
        if not e.get("th") and e.get("ds") in dossiers:
            e["th"] = dossiers[e["ds"]].get("th", [])
    write(os.path.join(site, "ics", "tout.ics"), ics("Veille parlementaire", ag, dossiers, base, stamp))
    for t in themes:
        write(os.path.join(site, "ics", f"{t['id']}.ics"),
              ics(f"Veille · {t['l']}", [e for e in ag if t["id"] in (e.get("th") or [])], dossiers, base, stamp))
    by_ag = {}
    for e in ag:
        if e.get("ds"):
            by_ag.setdefault(e["ds"], []).append(e)
    for i, L in by_ag.items():
        write(os.path.join(site, "ics", "t", f"{i}.ics"), ics(f"Veille · {dossiers.get(i, {}).get('t', i)[:80]}", L, dossiers, base, stamp))
    print(f"Journal : {len(journal)} nouveautés · {len(themes) + 1 + n_feeds} flux RSS · {len(themes) + 1 + len(by_ag)} agendas .ics")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])
