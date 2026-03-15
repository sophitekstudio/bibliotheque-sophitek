"""
╔══════════════════════════════════════════════════════════════╗
║         SOPHITEK STUDIO — GESTIONNAIRE FINAL                 ║
║         Auteur : Japhet Arcade Sophiano ASSOGBA               ║
║         Un seul fichier. Fonctionne sur PC et sur Render.    ║
╚══════════════════════════════════════════════════════════════╝

Sur ton PC    → Lance Tkinter (manager) + Flask (API) en arrière-plan
Sur Render    → Lance Flask uniquement (serveur de paiements)
"""

import os, sys, sqlite3, hashlib, json, shutil, threading
import logging, base64
from datetime import datetime
from pathlib import Path

import requests as req
from flask import Flask, request, jsonify, redirect, abort

# ── Détection environnement ──────────────────────────────────
ON_RENDER = os.environ.get("RENDER", "").lower() == "true"

# ── Chargement .env (PC uniquement) ─────────────────────────
def _load_env():
    env_path = Path(__file__).parent / ".env"
    if env_path.exists():
        with open(env_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, val = line.partition("=")
                    os.environ.setdefault(key.strip(), val.strip())
_load_env()

# ════════════════════════════════════════════════════════════
# CONFIGURATION
# ════════════════════════════════════════════════════════════
CONFIG = {
    "GITHUB_TOKEN":  os.environ.get("GITHUB_TOKEN", ""),
    "GITHUB_REPO":   "sophitekstudio/bibliotheque-sophitek",
    "RENDER_URL":    "https://bibliotheque-sophitek.onrender.com",
    "FEDAPAY_KEY":   os.environ.get("FEDAPAY_KEY", ""),
    "WHATSAPP":      "2290143678355",
    "PRIX_DEFAUT":   1000,
    "ADMIN_KEY":     os.environ.get("ADMIN_KEY", "sophitek2026"),
    "PORT":          int(os.environ.get("PORT", 5000)),
    "SITE_URL":      "https://sophitekstudio.github.io/bibliotheque-sophitek/",
}

# ════════════════════════════════════════════════════════════
# CHEMINS
# ════════════════════════════════════════════════════════════
BASE_DIR   = Path(__file__).parent
SITE_DIR   = BASE_DIR / "site"
COVERS_DIR = SITE_DIR / "covers"
DB_PATH    = BASE_DIR / "data" / "sophitek.db"
JSON_PATH  = SITE_DIR / "data.json"
HTML_PATH  = SITE_DIR / "index.html"

COVERS_DIR.mkdir(parents=True, exist_ok=True)
(BASE_DIR / "data").mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s — %(levelname)s — %(message)s",
    handlers=[
        logging.FileHandler(BASE_DIR / "sophitek.log"),
        logging.StreamHandler(sys.stdout)
    ]
)

# ════════════════════════════════════════════════════════════
# BASE DE DONNÉES
# ════════════════════════════════════════════════════════════
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS contenus (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        type        TEXT DEFAULT 'livre',
        titre       TEXT NOT NULL,
        auteur      TEXT DEFAULT 'Japhet Arcade Sophiano ASSOGBA',
        genre       TEXT DEFAULT '',
        description TEXT DEFAULT '',
        extrait     TEXT DEFAULT '',
        prix        INTEGER DEFAULT 1000,
        gratuit     INTEGER DEFAULT 0,
        couverture  TEXT DEFAULT '',
        lien_drive  TEXT DEFAULT '',
        lien_media  TEXT DEFAULT '',
        actif       INTEGER DEFAULT 1,
        date_ajout  TEXT DEFAULT ''
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS commentaires (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        contenu_id INTEGER NOT NULL,
        nom        TEXT NOT NULL,
        texte      TEXT NOT NULL,
        date_com   TEXT DEFAULT '',
        approuve   INTEGER DEFAULT 1
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS commandes (
        id             INTEGER PRIMARY KEY AUTOINCREMENT,
        contenu_id     INTEGER,
        transaction_id TEXT UNIQUE,
        telephone      TEXT,
        montant        INTEGER,
        statut         TEXT DEFAULT 'en_attente',
        token_dl       TEXT UNIQUE,
        telecharge     INTEGER DEFAULT 0,
        date_cmd       TEXT DEFAULT '',
        date_paiement  TEXT DEFAULT ''
    )""")
    conn.commit()
    conn.close()
    logging.info("Base de données initialisée")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def get_contenus(type_filtre=None):
    conn = get_db()
    if type_filtre:
        rows = conn.execute(
            "SELECT * FROM contenus WHERE actif=1 AND type=? ORDER BY id DESC",
            (type_filtre,)).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM contenus WHERE actif=1 ORDER BY id DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_commentaires(contenu_id):
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM commentaires WHERE contenu_id=? AND approuve=1 ORDER BY id DESC",
        (contenu_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def add_contenu(d):
    conn = get_db()
    c = conn.execute("""INSERT INTO contenus
        (type,titre,auteur,genre,description,extrait,prix,gratuit,
         couverture,lien_drive,lien_media,date_ajout)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
        (d["type"], d["titre"], d["auteur"], d["genre"],
         d["description"], d["extrait"], d["prix"], d["gratuit"],
         d["couverture"], d["lien_drive"], d["lien_media"],
         datetime.now().strftime("%Y-%m-%d")))
    lid = c.lastrowid
    conn.commit()
    conn.close()
    logging.info(f"Contenu ajouté : {d['titre']}")
    return lid

def update_contenu(lid, d):
    conn = get_db()
    conn.execute("""UPDATE contenus SET
        type=?,titre=?,auteur=?,genre=?,description=?,extrait=?,prix=?,
        gratuit=?,couverture=?,lien_drive=?,lien_media=? WHERE id=?""",
        (d["type"], d["titre"], d["auteur"], d["genre"],
         d["description"], d["extrait"], d["prix"], d["gratuit"],
         d["couverture"], d["lien_drive"], d["lien_media"], lid))
    conn.commit()
    conn.close()

def delete_contenu(lid):
    conn = get_db()
    conn.execute("UPDATE contenus SET actif=0 WHERE id=?", (lid,))
    conn.commit()
    conn.close()

def add_commentaire(contenu_id, nom, texte):
    conn = get_db()
    conn.execute(
        "INSERT INTO commentaires (contenu_id,nom,texte,date_com) VALUES(?,?,?,?)",
        (contenu_id, nom, texte, datetime.now().strftime("%Y-%m-%d %H:%M")))
    conn.commit()
    conn.close()

def delete_commentaire(com_id):
    conn = get_db()
    conn.execute("DELETE FROM commentaires WHERE id=?", (com_id,))
    conn.commit()
    conn.close()

def get_stats():
    conn = get_db()
    total   = conn.execute("SELECT COUNT(*) FROM contenus WHERE actif=1").fetchone()[0]
    gratuit = conn.execute("SELECT COUNT(*) FROM contenus WHERE actif=1 AND gratuit=1").fetchone()[0]
    ventes  = conn.execute("SELECT COUNT(*) FROM commandes WHERE statut='paye'").fetchone()[0]
    revenus = conn.execute("SELECT SUM(montant) FROM commandes WHERE statut='paye'").fetchone()[0] or 0
    coms    = conn.execute("SELECT COUNT(*) FROM commentaires WHERE approuve=1").fetchone()[0]
    conn.close()
    return {"total": total, "gratuit": gratuit, "ventes": ventes,
            "revenus": revenus, "commentaires": coms}

def token_unique(cid):
    raw = f"{cid}{datetime.now().isoformat()}{os.urandom(16).hex()}"
    return hashlib.sha256(raw.encode()).hexdigest()

# ════════════════════════════════════════════════════════════
# GÉNÉRATEUR HTML
# ════════════════════════════════════════════════════════════
def generer_html(contenus):
    cartes = ""
    ICONS = {"livre":"📚","app":"💻","audio":"🎵","video":"🎬","autre":"📦"}

    for b in contenus:
        cover  = ("covers/" + Path(b["couverture"]).name) if b["couverture"] else "covers/placeholder.jpg"
        badge  = "GRATUIT" if b["gratuit"] else (str(b["prix"]) + " FCFA" if b["prix"] else "")
        bcls   = "free" if b["gratuit"] else ("paid" if b["prix"] else "")
        icon   = ICONS.get(b["type"], "📦")
        coms   = get_commentaires(b["id"])
        nb_com = len(coms)

        # Bouton extrait
        btns = ""
        if b["extrait"]:
            ext_safe = b["extrait"].replace("\\","\\\\").replace("'","\\'").replace("\n","\\n").replace("\r","")
            tit_safe = b["titre"].replace("'","\\'")
            btns += f'<button class="btn ext-btn" onclick="voirExtrait(\'{ext_safe}\',\'{tit_safe}\')">📖 Lire un extrait</button>'

        # Bouton discuter
        msg_disc = req.utils.quote("Bonjour, je voudrais en savoir plus sur : " + b["titre"])
        btns += f'<a href="https://wa.me/{CONFIG["WHATSAPP"]}?text={msg_disc}" target="_blank" class="btn disc-btn">💬 Discuter</a>'

        # Bouton action principal
        if b["gratuit"] and b["lien_drive"]:
            btns += f'<a href="{b["lien_drive"]}" target="_blank" class="btn free-btn">↓ Télécharger gratuitement</a>'
        elif b["type"] in ("audio","video") and b["lien_media"]:
            if b["gratuit"]:
                btns += f'<a href="{b["lien_media"]}" target="_blank" class="btn free-btn">▶ Écouter / Voir</a>'
            else:
                msg_cmd = req.utils.quote("Bonjour, je souhaite accéder à : " + b["titre"] + " (" + str(b["prix"]) + " FCFA)")
                btns += f'<a href="https://wa.me/{CONFIG["WHATSAPP"]}?text={msg_cmd}" target="_blank" class="btn buy-btn">🛒 Commander</a>'
        elif b["type"] == "app":
            if b["gratuit"] and b["lien_drive"]:
                btns += f'<a href="{b["lien_drive"]}" target="_blank" class="btn free-btn">↓ Télécharger</a>'
            elif b["prix"]:
                msg_app = req.utils.quote("Bonjour, je veux acquérir : " + b["titre"] + " (" + str(b["prix"]) + " FCFA)")
                btns += f'<a href="https://wa.me/{CONFIG["WHATSAPP"]}?text={msg_app}" target="_blank" class="btn buy-btn">🛒 Commander</a>'
        elif not b["gratuit"] and b["prix"]:
            btns += '<button class="btn buy-btn" onclick="acheter(' + str(b["id"]) + ',' + str(b["prix"]) + ',\'' + b["titre"].replace("'","\\'") + '\')">🛒 Acheter — ' + str(b["prix"]) + ' FCFA</button>'

        # Commentaires HTML
        coms_html = ""
        for cm in coms[:3]:
            coms_html += f'<div class="ci"><span class="cn">{cm["nom"]}</span><span class="cd">{cm["date_com"][:10]}</span><p class="ct">{cm["texte"]}</p></div>'

        badge_html = f'<span class="badge {bcls}">{badge}</span>' if badge else ""
        desc_court = b["description"][:150] + ("..." if len(b["description"]) > 150 else "")

        cartes += f"""<div class="card" data-type="{b['type']}">
<div class="cw"><img src="{cover}" alt="{b['titre']}" loading="lazy"/>{badge_html}<span class="ti">{icon}</span></div>
<div class="cb">
<span class="gt">{b['genre']}</span><h3>{b['titre']}</h3>
<p class="au">{b['auteur']}</p><p class="de">{desc_court}</p>
<div class="btns">{btns}</div>
<div class="cs"><div class="ct2" onclick="this.nextElementSibling.style.display=this.nextElementSibling.style.display=='none'?'block':'none'">💬 {nb_com} commentaire{'s' if nb_com!=1 else ''}</div>
<div class="cb2" style="display:none">{coms_html}
<div class="cf"><input class="ci2" placeholder="Votre nom" id="n{b['id']}"/><textarea class="ci2" placeholder="Votre commentaire..." id="t{b['id']}" rows="2"></textarea>
<button class="bc" onclick="envoyerCom({b['id']})">Envoyer</button></div></div></div>
</div></div>"""

    genres  = sorted(set(b["type"] for b in contenus))
    LABELS  = {"livre":"📚 Livres","app":"💻 Apps","audio":"🎵 Audios","video":"🎬 Vidéos","autre":"📦 Autres"}
    filtres = '<button class="f active" data-f="tous">Tous</button>'
    for g in genres:
        filtres += f'<button class="f" data-f="{g}">{LABELS.get(g,g)}</button>'

    s = get_stats()
    vide = '<div class="empty">Aucun contenu disponible pour le moment.<br/>Revenez bientôt !</div>' if not contenus else ""

    return """<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1.0"/>
<title>Sophitek Studio — Boutique</title>
<link href="https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,700;0,900;1,400&family=Cormorant+Garamond:wght@300;400;600&family=Space+Mono:wght@400;700&display=swap" rel="stylesheet"/>
<style>
:root{--n:#0a0a0a;--g:#141414;--g2:#1e1e1e;--g3:#2a2a2a;--r:#c0392b;--r2:#e74c3c;--b:#f5f0e8;--t:#b8b0a8;--v:#27ae60;--or:#b8960c;--bl:#2471a3;}
*{margin:0;padding:0;box-sizing:border-box;}
html{scroll-behavior:smooth;}
body{background:var(--n);color:var(--b);font-family:'Cormorant Garamond',serif;min-height:100vh;}
/* ── HEADER */
header{text-align:center;padding:70px 20px 40px;position:relative;overflow:hidden;border-bottom:1px solid rgba(192,57,43,.25);}
header::before{content:'';position:absolute;inset:0;background:radial-gradient(ellipse at 50% 0%,rgba(192,57,43,.15) 0%,transparent 70%);pointer-events:none;}
.stag{font-family:'Space Mono',monospace;font-size:10px;letter-spacing:6px;color:var(--r);text-transform:uppercase;margin-bottom:16px;opacity:.9;}
h1{font-family:'Playfair Display',serif;font-size:clamp(44px,9vw,96px);font-weight:900;line-height:.88;letter-spacing:-2px;color:var(--b);}
h1 em{color:var(--r);font-style:normal;}
.hsub{font-size:15px;font-weight:300;color:var(--t);letter-spacing:3px;margin-top:18px;}
/* ── STATS */
.stats{display:flex;justify-content:center;gap:0;background:var(--g);border-bottom:1px solid rgba(255,255,255,.06);flex-wrap:wrap;}
.stat{text-align:center;padding:18px 32px;border-right:1px solid rgba(255,255,255,.06);}
.stat:last-child{border-right:none;}
.sn{font-family:'Playfair Display',serif;font-size:28px;font-weight:700;color:var(--r);display:block;line-height:1;}
.sl{font-family:'Space Mono',monospace;font-size:9px;letter-spacing:3px;color:var(--t);text-transform:uppercase;margin-top:4px;display:block;}
/* ── FILTRES */
.filters{display:flex;justify-content:center;gap:8px;padding:28px 16px;flex-wrap:wrap;}
.f{font-family:'Space Mono',monospace;font-size:10px;letter-spacing:2px;text-transform:uppercase;padding:8px 18px;border:1px solid rgba(192,57,43,.3);background:transparent;color:var(--t);cursor:pointer;transition:all .25s;border-radius:0;}
.f:hover,.f.active{background:var(--r);color:#fff;border-color:var(--r);}
/* ── GRILLE */
main{max-width:1380px;margin:0 auto;padding:0 24px 100px;}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(270px,1fr));gap:28px;}
.card{background:var(--g);border:1px solid rgba(255,255,255,.06);transition:all .3s;position:relative;}
.card:hover{border-color:rgba(192,57,43,.35);transform:translateY(-3px);box-shadow:0 12px 40px rgba(0,0,0,.4);}
.card.hidden{display:none;}
/* Cover */
.cw{position:relative;aspect-ratio:2/3;overflow:hidden;background:var(--g3);}
.cw img{width:100%;height:100%;object-fit:cover;transition:.6s;}
.card:hover .cw img{transform:scale(1.05);}
.badge{position:absolute;top:12px;right:12px;font-family:'Space Mono',monospace;font-size:10px;font-weight:700;padding:4px 10px;color:#fff;letter-spacing:1px;}
.badge.free{background:var(--v);}
.badge.paid{background:var(--r);}
.ti{position:absolute;top:12px;left:12px;font-size:16px;background:rgba(0,0,0,.65);padding:4px 7px;backdrop-filter:blur(4px);}
/* Body */
.cb{padding:16px;}
.gt{font-family:'Space Mono',monospace;font-size:9px;letter-spacing:3px;color:var(--r);text-transform:uppercase;}
h3{font-family:'Playfair Display',serif;font-size:18px;font-weight:700;color:var(--b);line-height:1.2;margin:6px 0 4px;}
.au{font-size:12px;color:var(--t);margin-bottom:8px;font-style:italic;}
.de{font-size:13px;color:var(--t);line-height:1.6;margin-bottom:12px;}
/* Boutons */
.btns{display:flex;flex-direction:column;gap:6px;margin-bottom:12px;}
.btn{display:block;width:100%;padding:10px 14px;font-family:'Space Mono',monospace;font-size:10px;letter-spacing:2px;text-transform:uppercase;text-align:center;text-decoration:none;border:none;cursor:pointer;transition:all .2s;font-weight:700;}
.buy-btn{background:var(--r);color:#fff;}
.buy-btn:hover{background:var(--r2);}
.free-btn{background:var(--v);color:#fff;}
.free-btn:hover{background:#2ecc71;}
.disc-btn{background:transparent;color:var(--t);border:1px solid rgba(255,255,255,.15);}
.disc-btn:hover{background:#25D366;color:#fff;border-color:#25D366;}
.ext-btn{background:var(--g3);color:var(--b);border:1px solid rgba(255,255,255,.12);}
.ext-btn:hover{background:var(--or);border-color:var(--or);}
/* Commentaires */
.cs{border-top:1px solid rgba(255,255,255,.07);padding-top:10px;}
.ct2{font-family:'Space Mono',monospace;font-size:9px;color:var(--t);cursor:pointer;padding:4px 0;letter-spacing:2px;}
.ct2:hover{color:var(--b);}
.cb2{margin-top:8px;}
.ci{padding:8px 0;border-bottom:1px solid rgba(255,255,255,.05);}
.cn{font-family:'Space Mono',monospace;font-size:10px;color:var(--r);font-weight:700;}
.cd{font-family:'Space Mono',monospace;font-size:9px;color:rgba(255,255,255,.3);margin-left:8px;}
.ct{font-size:12px;color:var(--t);margin-top:4px;line-height:1.5;}
.cf{margin-top:10px;display:flex;flex-direction:column;gap:6px;}
.ci2{background:var(--g3);border:1px solid rgba(255,255,255,.1);color:var(--b);font-family:'Cormorant Garamond',serif;font-size:13px;padding:8px 10px;outline:none;resize:none;width:100%;}
.ci2:focus{border-color:var(--r);}
.bc{background:var(--bl);color:#fff;border:none;font-family:'Space Mono',monospace;font-size:10px;letter-spacing:2px;padding:8px;cursor:pointer;transition:.2s;width:100%;}
.bc:hover{background:#2980b9;}
/* Empty */
.empty{text-align:center;padding:100px 20px;color:rgba(255,255,255,.25);font-family:'Space Mono',monospace;font-size:12px;letter-spacing:3px;line-height:2;grid-column:1/-1;}
/* ── MODALS */
.mov{display:none;position:fixed;inset:0;background:rgba(0,0,0,.93);z-index:1000;align-items:center;justify-content:center;padding:20px;backdrop-filter:blur(6px);}
.mov.open{display:flex;}
/* Modal extrait */
.mext{background:var(--g);border:1px solid rgba(192,57,43,.35);max-width:680px;width:100%;max-height:88vh;overflow-y:auto;padding:36px;position:relative;}
.mext h2{font-family:'Playfair Display',serif;font-size:24px;color:var(--b);margin-bottom:20px;padding-right:32px;border-bottom:1px solid rgba(192,57,43,.2);padding-bottom:14px;}
.mtxt{font-size:16px;color:var(--t);line-height:2;white-space:pre-wrap;}
/* Modal paiement */
.mpay{background:var(--g);border:1px solid rgba(192,57,43,.35);max-width:440px;width:100%;padding:36px;position:relative;}
.mclose{position:absolute;top:14px;right:16px;background:none;border:none;color:var(--t);font-size:24px;cursor:pointer;line-height:1;}
.mclose:hover{color:var(--b);}
.ptit{font-family:'Playfair Display',serif;font-size:22px;color:var(--b);margin-bottom:6px;}
.pprix{font-family:'Playfair Display',serif;font-size:32px;font-weight:900;color:var(--r);margin-bottom:20px;}
.plbl{font-family:'Space Mono',monospace;font-size:10px;letter-spacing:2px;color:var(--t);text-transform:uppercase;display:block;margin-bottom:6px;}
.pinp{width:100%;background:var(--g3);border:1px solid rgba(255,255,255,.1);color:var(--b);font-size:20px;padding:12px 14px;outline:none;margin-bottom:16px;font-family:'Cormorant Garamond',serif;}
.pinp:focus{border-color:var(--r);}
.pbtn{width:100%;background:var(--r);color:#fff;border:none;font-family:'Space Mono',monospace;font-size:12px;letter-spacing:3px;text-transform:uppercase;padding:15px;cursor:pointer;transition:.2s;font-weight:700;}
.pbtn:hover{background:var(--r2);}
.pstat{text-align:center;padding:8px 0;font-size:13px;color:var(--t);line-height:1.7;}
.spin{width:44px;height:44px;border:3px solid rgba(192,57,43,.25);border-top-color:var(--r);border-radius:50%;animation:sp 1s linear infinite;margin:12px auto;}
@keyframes sp{to{transform:rotate(360deg);}}
.pok{font-size:52px;margin:8px 0;}
.psucc{font-family:'Playfair Display',serif;font-size:22px;color:var(--v);margin-bottom:12px;}
.pdl{display:block;width:100%;background:var(--v);color:#fff;text-decoration:none;text-align:center;font-family:'Space Mono',monospace;font-size:11px;letter-spacing:3px;text-transform:uppercase;padding:15px;transition:.2s;font-weight:700;}
.pdl:hover{background:#2ecc71;}
.pwarn{font-family:'Space Mono',monospace;font-size:9px;color:rgba(255,255,255,.3);text-align:center;margin-top:8px;letter-spacing:2px;}
.perr{font-size:40px;margin:8px 0;}
.perrt{color:var(--r2);margin-bottom:16px;font-family:'Playfair Display',serif;font-size:18px;}
.pret{background:transparent;border:1px solid var(--r);color:var(--r);font-family:'Space Mono',monospace;font-size:10px;letter-spacing:2px;padding:10px 24px;cursor:pointer;transition:.2s;}
.pret:hover{background:var(--r);color:#fff;}
/* ── FOOTER */
footer{text-align:center;padding:40px;border-top:1px solid rgba(255,255,255,.06);}
footer p{font-family:'Space Mono',monospace;font-size:10px;letter-spacing:4px;color:rgba(255,255,255,.25);text-transform:uppercase;}
footer em{color:var(--r);font-style:normal;}
/* ── RESPONSIVE */
@media(max-width:640px){
  h1{font-size:clamp(36px,11vw,60px);}
  .grid{grid-template-columns:repeat(2,1fr);gap:14px;}
  .stat{padding:14px 20px;}
  .sn{font-size:22px;}
  main{padding:0 12px 80px;}
}
</style>
</head>
<body>

<header>
  <div class="stag">Sophitek Studio — Boutique Officielle</div>
  <h1>SOPHITEK<br/><em>STUDIO</em></h1>
  <p class="hsub">Japhet Arcade Sophiano ASSOGBA</p>
</header>

<div class="stats">""" + f"""
  <div class="stat"><span class="sn">{s['total']}</span><span class="sl">Contenus</span></div>
  <div class="stat"><span class="sn">{s['gratuit']}</span><span class="sl">Gratuits</span></div>
  <div class="stat"><span class="sn">{s['ventes']}</span><span class="sl">Ventes</span></div>
  <div class="stat"><span class="sn">{s['revenus']:,}</span><span class="sl">FCFA</span></div>
  <div class="stat"><span class="sn">{s['commentaires']}</span><span class="sl">Avis</span></div>
</div>

<div class="filters">{filtres}</div>
<main><div class="grid" id="grid">{cartes}{vide}</div></main>

<footer><p>© 2026 <em>Sophitek Studio</em> — Tous droits réservés</p></footer>

<!-- Modal Extrait -->
<div class="mov" id="mext-ov">
  <div class="mext">
    <button class="mclose" onclick="ferm('mext-ov')">✕</button>
    <h2 id="ext-tit"></h2>
    <div class="mtxt" id="ext-txt"></div>
  </div>
</div>

<!-- Modal Paiement -->
<div class="mov" id="mpay-ov">
  <div class="mpay">
    <button class="mclose" onclick="ferm('mpay-ov')">✕</button>
    <div class="ptit" id="p-tit"></div>
    <div class="pprix" id="p-prix"></div>
    <div id="ps1">
      <span class="plbl">Votre numéro MTN / Moov Money</span>
      <input class="pinp" id="p-tel" placeholder="ex : 67 00 00 00" maxlength="12"/>
      <button class="pbtn" onclick="payerNow()">💳 &nbsp;Payer maintenant</button>
    </div>
    <div id="ps2" style="display:none;text-align:center">
      <div class="spin"></div>
      <p class="pstat">Un message de validation a été envoyé<br/>sur votre téléphone.<br/>Validez et patientez...</p>
    </div>
    <div id="ps3" style="display:none;text-align:center">
      <div class="pok">✅</div>
      <div class="psucc">Paiement confirmé !</div>
      <a class="pdl" id="p-dl" href="#" target="_blank">↓ &nbsp;Télécharger mon livre</a>
      <p class="pwarn">⚠ Lien valide pour 1 seul téléchargement</p>
    </div>
    <div id="ps4" style="display:none;text-align:center">
      <div class="perr">❌</div>
      <div class="perrt">Paiement non abouti</div>
      <p class="pstat">Vérifiez votre solde et réessayez.</p>
      <button class="pret" onclick="rstPay()">↺ Réessayer</button>
    </div>
  </div>
</div>

<script>
const API='{CONFIG['RENDER_URL']}';
let payId=null,cmdId=null,pollT=null;

// Filtres
document.querySelectorAll('.f').forEach(b=>b.addEventListener('click',()=>{{
  document.querySelectorAll('.f').forEach(x=>x.classList.remove('active'));
  b.classList.add('active');
  const f=b.dataset.f;
  document.querySelectorAll('.card').forEach(c=>c.classList.toggle('hidden',f!=='tous'&&c.dataset.type!==f));
}}));

// Extrait
function voirExtrait(txt,tit){{document.getElementById('ext-tit').textContent=tit;document.getElementById('ext-txt').textContent=txt;document.getElementById('mext-ov').classList.add('open');}}

// Commentaires
async function envoyerCom(id){{
  const nom=document.getElementById('n'+id).value.trim();
  const txt=document.getElementById('t'+id).value.trim();
  if(!nom||!txt){{alert('Remplissez votre nom et commentaire.');return;}}
  try{{
    await fetch(API+'/commentaire',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{contenu_id:id,nom,texte:txt}})}});
    document.getElementById('n'+id).value='';document.getElementById('t'+id).value='';
    alert('Merci ! Votre commentaire a bien été envoyé.');
  }}catch(e){{alert('Erreur réseau. Réessayez.');}}
}}

// Paiement
function acheter(id,prix,titre){{
  payId=id;
  document.getElementById('p-tit').textContent=titre;
  document.getElementById('p-prix').textContent=prix+' FCFA';
  rstPay();
  document.getElementById('mpay-ov').classList.add('open');
}}

async function payerNow(){{
  const tel=document.getElementById('p-tel').value.trim();
  if(!tel||tel.length<8){{alert('Entrez un numéro valide.');return;}}
  showPs(2);
  try{{
    const r=await fetch(API+'/acheter/'+payId,{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{telephone:tel}})}});
    const d=await r.json();
    if(!d.success)throw new Error(d.erreur||'Erreur');
    cmdId=d.commande_id;
    let n=0;
    pollT=setInterval(async()=>{{
      if(++n>72){{clearInterval(pollT);showPs(4);return;}}
      const rv=await fetch(API+'/verifier/'+cmdId);
      const dv=await rv.json();
      if(dv.statut==='paye'){{clearInterval(pollT);document.getElementById('p-dl').href=dv.lien;showPs(3);}}
      else if(dv.statut==='echec'){{clearInterval(pollT);showPs(4);}}
    }},5000);
  }}catch(e){{showPs(4);}}
}}

function showPs(n){{[1,2,3,4].forEach(i=>document.getElementById('ps'+i).style.display=i===n?'block':'none');}}
function rstPay(){{if(pollT)clearInterval(pollT);cmdId=null;document.getElementById('p-tel').value='';showPs(1);}}
function ferm(id){{document.getElementById(id).classList.remove('open');if(id==='mpay-ov')rstPay();}}
document.querySelectorAll('.mov').forEach(m=>m.addEventListener('click',e=>{{ if(e.target===m)ferm(m.id); }}));
document.addEventListener('keydown',e=>{{ if(e.key==='Escape')document.querySelectorAll('.mov.open').forEach(m=>ferm(m.id)); }});
</script>
</body></html>"""

# ════════════════════════════════════════════════════════════
# GITHUB
# ════════════════════════════════════════════════════════════
def github_push(contenu_bytes, chemin_repo, message):
    token   = CONFIG["GITHUB_TOKEN"]
    repo    = CONFIG["GITHUB_REPO"]
    url     = f"https://api.github.com/repos/{repo}/contents/{chemin_repo}"
    headers = {"Authorization": f"token {token}", "Accept": "application/vnd.github+json"}
    b64 = base64.b64encode(contenu_bytes).decode()
    sha = None
    r = req.get(url, headers=headers, timeout=15)
    if r.status_code == 200:
        sha = r.json().get("sha")
    payload = {"message": message, "content": b64}
    if sha:
        payload["sha"] = sha
    r = req.put(url, json=payload, headers=headers, timeout=20)
    if r.status_code in (200, 201):
        return True, f"✓ {chemin_repo}"
    return False, f"✗ {chemin_repo} : {r.json().get('message','Erreur')}"

def github_get_json(chemin_repo):
    token   = CONFIG["GITHUB_TOKEN"]
    repo    = CONFIG["GITHUB_REPO"]
    url     = f"https://api.github.com/repos/{repo}/contents/{chemin_repo}"
    headers = {"Authorization": f"token {token}", "Accept": "application/vnd.github+json"}
    r = req.get(url, headers=headers, timeout=15)
    if r.status_code == 200:
        return base64.b64decode(r.json().get("content",""))
    return None

def publier_site(callback):
    contenus = get_contenus()
    msgs, errors = [], []
    # HTML
    html = generer_html(contenus)
    HTML_PATH.write_text(html, encoding="utf-8")
    ok, msg = github_push(html.encode("utf-8"), "index.html",
                          f"Mise à jour — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    (msgs if ok else errors).append(msg)
    # JSON
    data = [{**b, "gratuit": bool(b["gratuit"])} for b in contenus]
    json_str = json.dumps(data, ensure_ascii=False, indent=2)
    JSON_PATH.write_text(json_str, encoding="utf-8")
    ok, msg = github_push(json_str.encode("utf-8"), "data.json",
                          f"Données — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    (msgs if ok else errors).append(msg)
    # Couvertures
    for cover in COVERS_DIR.iterdir():
        if cover.is_file() and cover.suffix.lower() in (".jpg",".jpeg",".png",".webp"):
            ok, msg = github_push(cover.read_bytes(), f"covers/{cover.name}",
                                  f"Cover : {cover.name}")
            (msgs if ok else errors).append(msg)
    logging.info(f"Publication : {len(msgs)} ok, {len(errors)} erreurs")
    callback(msgs, errors)

def synchroniser(callback):
    try:
        data_bytes = github_get_json("data.json")
        if not data_bytes:
            callback(False, "Fichier data.json introuvable sur GitHub")
            return
        data = json.loads(data_bytes.decode("utf-8"))
        conn = get_db()
        for b in data:
            exists = conn.execute("SELECT id FROM contenus WHERE id=?", (b["id"],)).fetchone()
            if exists:
                conn.execute("""UPDATE contenus SET type=?,titre=?,auteur=?,genre=?,
                    description=?,extrait=?,prix=?,gratuit=?,couverture=?,
                    lien_drive=?,lien_media=?,actif=? WHERE id=?""",
                    (b.get("type","livre"),b["titre"],b.get("auteur",""),b.get("genre",""),
                     b.get("description",""),b.get("extrait",""),b.get("prix",0),
                     int(b.get("gratuit",False)),b.get("couverture",""),
                     b.get("lien_drive",""),b.get("lien_media",""),b.get("actif",1),b["id"]))
            else:
                conn.execute("""INSERT OR IGNORE INTO contenus
                    (id,type,titre,auteur,genre,description,extrait,prix,gratuit,
                     couverture,lien_drive,lien_media,actif,date_ajout)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (b["id"],b.get("type","livre"),b["titre"],b.get("auteur",""),
                     b.get("genre",""),b.get("description",""),b.get("extrait",""),
                     b.get("prix",0),int(b.get("gratuit",False)),b.get("couverture",""),
                     b.get("lien_drive",""),b.get("lien_media",""),b.get("actif",1),
                     b.get("date_ajout","")))
        conn.commit()
        conn.close()
        callback(True, f"✓ {len(data)} contenus synchronisés depuis GitHub")
    except Exception as e:
        callback(False, str(e))

def sauvegarder(callback):
    try:
        script = Path(__file__).read_bytes()
        ok, msg = github_push(script, "backup/gestionnaire.py",
                              f"Backup — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        callback(ok, msg)
    except Exception as e:
        callback(False, str(e))

# ════════════════════════════════════════════════════════════
# FLASK — API PAIEMENTS
# ════════════════════════════════════════════════════════════
flask_app = Flask(__name__)

@flask_app.route("/")
def home():
    return jsonify({"status": "Sophitek Studio API v2", "ok": True})

@flask_app.route("/contenus")
def api_contenus():
    t = request.args.get("type")
    data = get_contenus(t)
    return jsonify([{**b, "gratuit": bool(b["gratuit"])} for b in data])

@flask_app.route("/commentaire", methods=["POST"])
def api_commentaire():
    d   = request.get_json(silent=True) or {}
    cid = d.get("contenu_id")
    nom = str(d.get("nom","")).strip()[:60]
    txt = str(d.get("texte","")).strip()[:500]
    if not cid or not nom or not txt:
        return jsonify({"erreur": "Données manquantes"}), 400
    add_commentaire(cid, nom, txt)
    return jsonify({"success": True})

@flask_app.route("/acheter/<int:cid>", methods=["POST"])
def api_acheter(cid):
    conn = get_db()
    item = conn.execute("SELECT * FROM contenus WHERE id=? AND actif=1", (cid,)).fetchone()
    conn.close()
    if not item:
        return jsonify({"erreur": "Introuvable"}), 404
    item = dict(item)
    d    = request.get_json(silent=True) or {}
    tel  = str(d.get("telephone","")).strip()
    if not tel or len(tel) < 8:
        return jsonify({"erreur": "Numéro invalide"}), 400
    conn = get_db()
    c = conn.execute("""INSERT INTO commandes (contenu_id,telephone,montant,statut,date_cmd)
        VALUES(?,?,?,'en_attente',?)""",
        (cid, tel, item["prix"], datetime.now().isoformat()))
    cmd_id = c.lastrowid
    conn.commit()
    conn.close()
    # Créer transaction FedaPay
    try:
        headers = {"Authorization": f"Bearer {CONFIG['FEDAPAY_KEY']}",
                   "Content-Type": "application/json"}
        payload = {
            "description": f"Achat — {item['titre']}",
            "amount": item["prix"],
            "currency": {"iso": "XOF"},
            "callback_url": f"{CONFIG['RENDER_URL']}/webhook",
            "customer": {"phone_number": {"number": tel, "country": "BJ"}},
            "meta": {"commande_id": cmd_id, "contenu_id": cid}
        }
        r = req.post("https://api.fedapay.com/v1/transactions",
                     json=payload, headers=headers, timeout=15)
        r.raise_for_status()
        tid = str(r.json()["v1/transaction"]["id"])
        conn = get_db()
        conn.execute("UPDATE commandes SET transaction_id=? WHERE id=?", (tid, cmd_id))
        conn.commit()
        conn.close()
        logging.info(f"Transaction FedaPay créée : {tid}")
        return jsonify({"success": True, "commande_id": cmd_id})
    except Exception as e:
        logging.error(f"Erreur FedaPay : {e}")
        conn = get_db()
        conn.execute("DELETE FROM commandes WHERE id=?", (cmd_id,))
        conn.commit()
        conn.close()
        return jsonify({"erreur": "Erreur paiement. Réessayez."}), 500

@flask_app.route("/verifier/<int:cmd_id>")
def api_verifier(cmd_id):
    conn = get_db()
    cmd  = conn.execute("SELECT * FROM commandes WHERE id=?", (cmd_id,)).fetchone()
    conn.close()
    if not cmd:
        return jsonify({"erreur": "Introuvable"}), 404
    cmd = dict(cmd)
    if cmd["statut"] == "paye" and cmd["token_dl"]:
        return jsonify({"statut": "paye",
                        "lien": f"{CONFIG['RENDER_URL']}/dl/{cmd['token_dl']}"})
    elif cmd["statut"] == "echec":
        return jsonify({"statut": "echec"})
    return jsonify({"statut": "en_attente"})

@flask_app.route("/webhook", methods=["POST"])
def api_webhook():
    data   = request.get_json(silent=True) or {}
    obj    = data.get("object", {})
    statut = obj.get("status","")
    tid    = str(obj.get("id",""))
    meta   = obj.get("meta", {})
    cid    = meta.get("commande_id")
    if not cid:
        return "OK", 200
    conn = get_db()
    if statut == "approved":
        tok = token_unique(cid)
        conn.execute("""UPDATE commandes SET statut='paye',transaction_id=?,
            token_dl=?,date_paiement=? WHERE id=?""",
            (tid, tok, datetime.now().isoformat(), cid))
        logging.info(f"Paiement confirmé commande {cid}")
    elif statut in ("declined","canceled","expired"):
        conn.execute("UPDATE commandes SET statut='echec' WHERE id=?", (cid,))
        logging.info(f"Paiement échoué commande {cid}")
    conn.commit()
    conn.close()
    return "OK", 200

@flask_app.route("/dl/<token>")
def api_dl(token):
    conn = get_db()
    row  = conn.execute("""SELECT c.*,co.lien_drive FROM commandes c
        JOIN contenus co ON c.contenu_id=co.id WHERE c.token_dl=?""", (token,)).fetchone()
    conn.close()
    if not row:
        return "<h2 style='color:red;text-align:center;padding:60px;font-family:Georgia'>Lien invalide.</h2>", 404
    row = dict(row)
    if row["telecharge"] >= 1:
        return "<h2 style='color:red;text-align:center;padding:60px;font-family:Georgia'>Ce lien a déjà été utilisé.</h2>", 400
    if row["statut"] != "paye":
        return "<h2 style='color:orange;text-align:center;padding:60px;font-family:Georgia'>Paiement non confirmé.</h2>", 400
    conn = get_db()
    conn.execute("UPDATE commandes SET telecharge=telecharge+1 WHERE token_dl=?", (token,))
    conn.commit()
    conn.close()
    logging.info(f"Téléchargement effectué — commande {row['id']}")
    return redirect(row["lien_drive"])

@flask_app.route("/admin/stats")
def api_stats():
    if request.args.get("key") != CONFIG["ADMIN_KEY"]:
        abort(403)
    return jsonify(get_stats())

def demarrer_flask():
    flask_app.run(host="0.0.0.0", port=CONFIG["PORT"],
                  debug=False, use_reloader=False)

# ════════════════════════════════════════════════════════════
# TKINTER — MANAGER (PC uniquement)
# ════════════════════════════════════════════════════════════
if not ON_RENDER:
    import tkinter as tk
    from tkinter import ttk, messagebox, filedialog

    N="#0a0a0a"; G="#141414"; G2="#1e1e1e"; G3="#2a2a2a"
    R="#c0392b"; B="#f5f0e8"; T="#b8b0a8"; V="#27ae60"; OR="#b8960c"; BL="#2471a3"
    TYPES = [("livre","📚 Livre"),("app","💻 Application"),
             ("audio","🎵 Audio"),("video","🎬 Vidéo"),("autre","📦 Autre")]

    class App:
        def __init__(self, root):
            self.root = root
            self.root.title("Sophitek Studio — Gestionnaire v2")
            self.root.geometry("1150x730")
            self.root.configure(bg=N)
            self.sel_id    = None
            self.cover_var = tk.StringVar()
            init_db()
            self._ui()
            self._charger()
            threading.Thread(target=demarrer_flask, daemon=True).start()

        def _btn(self, p, txt, cmd, bg, sz=11):
            return tk.Button(p, text=txt, command=cmd, bg=bg, fg=B,
                             font=("Courier",sz,"bold"), borderwidth=0,
                             padx=8, pady=5, cursor="hand2",
                             activebackground=R, activeforeground=B)

        def _field(self, parent, key, label, multi=False):
            row = tk.Frame(parent, bg=N)
            row.pack(fill="x", padx=12, pady=3)
            tk.Label(row, text=label, font=("Courier",9), fg=T, bg=N, anchor="w").pack(fill="x")
            if multi:
                w = tk.Text(row, height=3, bg=G2, fg=B, insertbackground=B,
                            font=("Georgia",11), borderwidth=0, padx=6, pady=4)
            else:
                w = tk.Entry(row, bg=G2, fg=B, insertbackground=B,
                             font=("Georgia",12), borderwidth=0,
                             highlightthickness=1, highlightbackground=G2, highlightcolor=R)
            w.pack(fill="x", ipady=0 if multi else 4)
            self.flds[key] = w

        def _ui(self):
            # Header
            hdr = tk.Frame(self.root, bg=G, pady=10)
            hdr.pack(fill="x")
            tk.Label(hdr, text="SOPHITEK STUDIO",
                     font=("Courier",10), fg=R, bg=G).pack()
            tk.Label(hdr, text="Gestionnaire de Boutique v2",
                     font=("Georgia",16,"bold"), fg=B, bg=G).pack()

            body = tk.Frame(self.root, bg=N)
            body.pack(fill="both", expand=True, padx=10, pady=8)

            # Gauche — liste
            left = tk.Frame(body, bg=G2, width=280)
            left.pack(side="left", fill="y", padx=(0,10))
            left.pack_propagate(False)

            tk.Label(left, text="📦  CONTENUS", font=("Courier",10,"bold"),
                     fg=R, bg=G2, pady=6).pack(fill="x", padx=8)
            self.stats_lbl = tk.Label(left, text="", font=("Courier",8), fg=T, bg=G2, anchor="w")
            self.stats_lbl.pack(fill="x", padx=8, pady=(0,4))

            ff = tk.Frame(left, bg=G2)
            ff.pack(fill="x", padx=6, pady=2)
            self.type_filtre = tk.StringVar(value="tous")
            for lbl, val in [("Tous","tous")] + [(t[1],t[0]) for t in TYPES]:
                tk.Radiobutton(ff, text=lbl, variable=self.type_filtre,
                               value=val, command=self._charger,
                               bg=G2, fg=T, selectcolor=R,
                               activebackground=G2, font=("Courier",8)).pack(anchor="w", padx=4)

            sf = tk.Frame(left, bg=G2)
            sf.pack(fill="both", expand=True, padx=6)
            sb = ttk.Scrollbar(sf)
            sb.pack(side="right", fill="y")
            self.lb = tk.Listbox(sf, bg=G, fg=B, selectbackground=R,
                                  font=("Georgia",11), borderwidth=0,
                                  highlightthickness=0, activestyle="none",
                                  yscrollcommand=sb.set, cursor="hand2")
            self.lb.pack(side="left", fill="both", expand=True)
            sb.config(command=self.lb.yview)
            self.lb.bind("<<ListboxSelect>>", self._on_sel)

            bf = tk.Frame(left, bg=G2, pady=4)
            bf.pack(fill="x", padx=6)
            self._btn(bf,"＋ Nouveau",      self._nouveau,   V,  10).pack(fill="x",pady=2)
            self._btn(bf,"✕ Supprimer",     self._supprimer, R,  10).pack(fill="x",pady=2)
            self._btn(bf,"🗨 Commentaires", self._voir_coms, BL, 10).pack(fill="x",pady=2)

            # Droite — formulaire
            right = tk.Frame(body, bg=N)
            right.pack(side="left", fill="both", expand=True)

            frm = tk.LabelFrame(right, text="  DÉTAILS  ",
                                 font=("Courier",10), fg=R, bg=N,
                                 bd=1, relief="solid", labelanchor="n")
            frm.pack(fill="both", expand=True, pady=(0,6))

            # Type
            tr = tk.Frame(frm, bg=N)
            tr.pack(fill="x", padx=12, pady=4)
            tk.Label(tr, text="Type *", font=("Courier",9), fg=T, bg=N, anchor="w").pack(fill="x")
            self.type_var = tk.StringVar(value="livre")
            type_row = tk.Frame(tr, bg=N)
            type_row.pack(fill="x")
            for lbl, val in TYPES:
                tk.Radiobutton(type_row, text=lbl, variable=self.type_var,
                               value=val, bg=N, fg=B, selectcolor=R,
                               activebackground=N, font=("Courier",9)).pack(side="left", padx=4)

            self.flds = {}
            self._field(frm,"titre",      "Titre *")
            self._field(frm,"auteur",     "Auteur")
            self._field(frm,"genre",      "Genre / Catégorie")
            self._field(frm,"prix",       "Prix (FCFA) — 0 si gratuit")
            self._field(frm,"lien_drive", "Lien Google Drive")
            self._field(frm,"lien_media", "Lien audio / vidéo")
            self._field(frm,"description","Description", multi=True)
            self._field(frm,"extrait",    "Extrait lisible", multi=True)

            ex = tk.Frame(frm, bg=N)
            ex.pack(fill="x", padx=12, pady=4)
            self.grat_var = tk.BooleanVar()
            tk.Checkbutton(ex, text="✓ Accès gratuit", variable=self.grat_var,
                           bg=N, fg=B, selectcolor=R,
                           activebackground=N, font=("Courier",10)).pack(side="left")
            self._btn(ex,"🖼 Couverture", self._couverture, G3, 9).pack(side="left", padx=8)
            tk.Label(ex, textvariable=self.cover_var,
                     font=("Courier",8), fg=OR, bg=N).pack(side="left")

            sr = tk.Frame(frm, bg=N, pady=5)
            sr.pack(fill="x", padx=12)
            self._btn(sr,"💾  ENREGISTRER", self._enregistrer, V,  11).pack(side="left",padx=(0,6))
            self._btn(sr,"✕  ANNULER",      self._vider,       G3, 11).pack(side="left")

            # Actions
            act = tk.LabelFrame(right, text="  ACTIONS  ",
                                 font=("Courier",10), fg=R, bg=N,
                                 bd=1, relief="solid", labelanchor="n")
            act.pack(fill="x")
            ai = tk.Frame(act, bg=N, pady=6)
            ai.pack(fill="x", padx=10)
            self._btn(ai,"🌐 PUBLIER",      self._publier,     R,  11).pack(side="left",padx=(0,6))
            self._btn(ai,"⟳ SYNCHRONISER", self._sync,        BL, 11).pack(side="left",padx=(0,6))
            self._btn(ai,"💾 SAUVEGARDER",  self._sauvegarder, OR, 11).pack(side="left",padx=(0,6))
            self._btn(ai,"👁 APERÇU",       self._apercu,      G3, 11).pack(side="left",padx=(0,6))
            self._btn(ai,"🔗 SITE EN LIGNE",self._site,        G3, 11).pack(side="left")
            self.act_lbl = tk.Label(act, text="", font=("Courier",9), fg=V, bg=N, pady=3)
            self.act_lbl.pack()

        def _charger(self):
            self.lb.delete(0, tk.END)
            t = self.type_filtre.get()
            self.data = get_contenus(None if t == "tous" else t)
            IC = {"livre":"📚","app":"💻","audio":"🎵","video":"🎬","autre":"📦"}
            for b in self.data:
                ic  = IC.get(b["type"],"📦")
                tag = "🆓" if b["gratuit"] else f"{b['prix']}F"
                self.lb.insert(tk.END, f"  {ic} {b['titre']}  [{tag}]")
            s = get_stats()
            self.stats_lbl.config(
                text=f"  {s['total']} contenus · {s['ventes']} ventes · {s['revenus']:,} FCFA")

        def _on_sel(self, _):
            sel = self.lb.curselection()
            if not sel: return
            b = self.data[sel[0]]
            self.sel_id = b["id"]
            self._vider()
            self.type_var.set(b.get("type","livre"))
            for k in ["titre","auteur","genre","prix","lien_drive","lien_media"]:
                self.flds[k].insert(0, str(b.get(k,"")))
            self.flds["description"].insert("1.0", b.get("description",""))
            self.flds["extrait"].insert("1.0", b.get("extrait",""))
            self.grat_var.set(bool(b.get("gratuit",0)))
            self.cover_var.set(b.get("couverture",""))

        def _vider(self):
            self.sel_id = None
            for k, w in self.flds.items():
                if isinstance(w, tk.Text): w.delete("1.0",tk.END)
                else: w.delete(0, tk.END)
            self.grat_var.set(False)
            self.cover_var.set("")
            self.type_var.set("livre")

        def _get_data(self):
            try: prix = int(self.flds["prix"].get().strip() or "0")
            except: prix = 0
            return {
                "type":        self.type_var.get(),
                "titre":       self.flds["titre"].get().strip(),
                "auteur":      self.flds["auteur"].get().strip() or "Japhet Arcade Sophiano ASSOGBA",
                "genre":       self.flds["genre"].get().strip(),
                "description": self.flds["description"].get("1.0",tk.END).strip(),
                "extrait":     self.flds["extrait"].get("1.0",tk.END).strip(),
                "prix":        prix,
                "gratuit":     int(self.grat_var.get()),
                "couverture":  self.cover_var.get(),
                "lien_drive":  self.flds["lien_drive"].get().strip(),
                "lien_media":  self.flds["lien_media"].get().strip(),
            }

        def _nouveau(self):
            self._vider()
            self.flds["titre"].focus()

        def _enregistrer(self):
            d = self._get_data()
            if not d["titre"]:
                messagebox.showerror("Erreur","Le titre est obligatoire."); return
            if self.sel_id:
                update_contenu(self.sel_id, d)
                messagebox.showinfo("✓", f"Modifié : {d['titre']}")
            else:
                add_contenu(d)
                messagebox.showinfo("✓", f"Ajouté : {d['titre']}")
            self._vider()
            self._charger()

        def _supprimer(self):
            sel = self.lb.curselection()
            if not sel or not self.sel_id:
                messagebox.showinfo("Info","Sélectionne un contenu."); return
            titre = self.data[sel[0]]["titre"]
            if messagebox.askyesno("Confirmer", f"Supprimer « {titre} » ?"):
                delete_contenu(self.sel_id)
                self._vider()
                self._charger()

        def _couverture(self):
            path = filedialog.askopenfilename(
                title="Choisir une image",
                filetypes=[("Images","*.jpg *.jpeg *.png *.webp")])
            if path:
                nom  = Path(path).name
                dest = COVERS_DIR / nom
                shutil.copy2(path, dest)
                self.cover_var.set(f"covers/{nom}")

        def _voir_coms(self):
            if not self.sel_id:
                messagebox.showinfo("Info","Sélectionne un contenu d'abord."); return
            win = tk.Toplevel(self.root)
            win.title("Commentaires")
            win.geometry("500x400")
            win.configure(bg=N)
            coms = get_commentaires(self.sel_id)
            tk.Label(win, text=f"Commentaires ({len(coms)})",
                     font=("Georgia",14,"bold"), fg=R, bg=N, pady=10).pack()
            sf = tk.Frame(win, bg=N)
            sf.pack(fill="both", expand=True, padx=10, pady=5)
            sb = ttk.Scrollbar(sf)
            sb.pack(side="right", fill="y")
            lb = tk.Listbox(sf, bg=G, fg=B, font=("Georgia",11),
                            borderwidth=0, highlightthickness=0, yscrollcommand=sb.set)
            lb.pack(side="left", fill="both", expand=True)
            sb.config(command=lb.yview)
            for cm in coms:
                lb.insert(tk.END, f"  {cm['nom']} ({cm['date_com'][:10]}) : {cm['texte'][:60]}")
            def sup():
                sel2 = lb.curselection()
                if not sel2: return
                if messagebox.askyesno("Confirmer","Supprimer ce commentaire ?"):
                    delete_commentaire(coms[sel2[0]]["id"])
                    lb.delete(sel2[0])
            self._btn(win,"✕ Supprimer", sup, R, 11).pack(pady=6)

        def _apercu(self):
            html = generer_html(get_contenus())
            HTML_PATH.write_text(html, encoding="utf-8")
            import webbrowser
            webbrowser.open(str(HTML_PATH))

        def _site(self):
            import webbrowser
            webbrowser.open(CONFIG["SITE_URL"])

        def _publier(self):
            self.act_lbl.config(text="⏳ Publication en cours...", fg=OR)
            self.root.update()
            def cb(msgs, errors):
                if errors and not msgs:
                    self.act_lbl.config(text=f"✗ Échec : {errors[0]}", fg=R)
                    messagebox.showerror("Erreur", "\n".join(errors[:3]))
                else:
                    self.act_lbl.config(text=f"✓ Publié — {len(msgs)} fichier(s)", fg=V)
                    messagebox.showinfo("✓ Succès !",
                        f"Site mis à jour !\n\nVisible dans 1-2 min sur :\n{CONFIG['SITE_URL']}")
                self._charger()
            threading.Thread(target=publier_site, args=(cb,), daemon=True).start()

        def _sync(self):
            if not messagebox.askyesno("Synchroniser",
                "Mettre l'app à jour depuis GitHub ?\nLes contenus locaux seront mis à niveau."):
                return
            self.act_lbl.config(text="⏳ Synchronisation...", fg=OR)
            self.root.update()
            def cb(ok, msg):
                self.act_lbl.config(text=msg, fg=V if ok else R)
                if ok:
                    messagebox.showinfo("✓", msg)
                    self._charger()
                else:
                    messagebox.showerror("Erreur", msg)
            threading.Thread(target=synchroniser, args=(cb,), daemon=True).start()

        def _sauvegarder(self):
            self.act_lbl.config(text="⏳ Sauvegarde...", fg=OR)
            self.root.update()
            def cb(ok, msg):
                self.act_lbl.config(text=msg, fg=V if ok else R)
                if ok:
                    messagebox.showinfo("✓ Sauvegardé",
                        "Fichier Python sauvegardé dans :\nsophitekstudio/bibliotheque-sophitek/backup/")
                else:
                    messagebox.showerror("Erreur", msg)
            threading.Thread(target=sauvegarder, args=(cb,), daemon=True).start()

# ════════════════════════════════════════════════════════════
# POINT D'ENTRÉE
# ════════════════════════════════════════════════════════════
if __name__ == "__main__":
    init_db()
    if ON_RENDER:
        # Sur Render : Flask uniquement
        logging.info("Démarrage en mode serveur (Render)")
        demarrer_flask()
    else:
        # Sur PC : Tkinter + Flask en arrière-plan
        logging.info("Démarrage en mode gestionnaire (PC)")
        root = tk.Tk()
        App(root)
        root.mainloop()
