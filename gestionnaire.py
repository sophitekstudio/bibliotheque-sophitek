"""
╔══════════════════════════════════════════════════════════════╗
║       SOPHITEK STUDIO — GESTIONNAIRE v2 (RENDER READY)      ║
║       Auteur : Japhet Arcade Sophiano ASSOGBA                ║
║       Compatible Render + Interface graphique locale         ║
╚══════════════════════════════════════════════════════════════╝
"""

import os
import sys
import sqlite3
import hashlib
import shutil
import json
import threading
import logging
import base64
import webbrowser
from datetime import datetime
from pathlib import Path
from functools import wraps

# ── DÉTECTION DE L'ENVIRONNEMENT ──────────────────────────────────────
ON_RENDER = os.environ.get('RENDER', False) or os.path.exists('/etc/render')

# Imports conditionnels (évite tkinter sur Render)
if not ON_RENDER:
    import tkinter as tk
    from tkinter import ttk, messagebox, filedialog
    import requests as req
else:
    import requests as req
    # Sur Render, on définit des placeholders pour éviter les erreurs
    tk = None
    ttk = None
    messagebox = None
    filedialog = None

# ── CHARGEMENT DES VARIABLES D'ENVIRONNEMENT ─────────────────────────
def _load_env():
    """Charge les variables depuis .env si le fichier existe"""
    env_path = Path(__file__).parent / ".env"
    if env_path.exists():
        with open(env_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, val = line.partition("=")
                    os.environ.setdefault(key.strip(), val.strip())

_load_env()

# ═════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ═════════════════════════════════════════════════════════════════════
CONFIG = {
    "GITHUB_TOKEN": os.environ.get("GITHUB_TOKEN", ""),
    "GITHUB_REPO":  "sophitekstudio/bibliotheque-sophitek",
    "RENDER_URL":   os.environ.get("RENDER_URL", "https://bibliotheque-sophitek.onrender.com"),
    "WHATSAPP":     os.environ.get("WHATSAPP", "2290143678355"),
    "PRIX_DEFAUT":  1000,
    "ADMIN_KEY":    os.environ.get("ADMIN_KEY", "sophitek2026"),
    "PORT":         int(os.environ.get("PORT", 5000)),
    "SITE_URL":     os.environ.get("SITE_URL", "https://sophitekstudio.github.io/bibliotheque-sophitek/"),
}

# ═════════════════════════════════════════════════════════════════════
# CHEMINS
# ═════════════════════════════════════════════════════════════════════
BASE_DIR   = Path(__file__).parent
SITE_DIR   = BASE_DIR / "site"
COVERS_DIR = SITE_DIR / "covers"
DB_PATH    = BASE_DIR / "data" / "sophitek.db"
JSON_PATH  = SITE_DIR / "data.json"
HTML_PATH  = SITE_DIR / "index.html"

# Création des dossiers nécessaires
COVERS_DIR.mkdir(parents=True, exist_ok=True)
(BASE_DIR / "data").mkdir(parents=True, exist_ok=True)
SITE_DIR.mkdir(parents=True, exist_ok=True)

# Configuration du logging
logging.basicConfig(
    filename=str(BASE_DIR / "sophitek.log"),
    level=logging.INFO,
    format="%(asctime)s — %(levelname)s — %(message)s"
)

# ═════════════════════════════════════════════════════════════════════
# BASE DE DONNÉES
# ═════════════════════════════════════════════════════════════════════
def init_db():
    """Initialise la base de données SQLite"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # Table des contenus (livres, apps, audios, vidéos)
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
    
    # Table des commentaires
    c.execute("""CREATE TABLE IF NOT EXISTS commentaires (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        contenu_id INTEGER NOT NULL,
        nom        TEXT NOT NULL,
        texte      TEXT NOT NULL,
        date_com   TEXT DEFAULT '',
        approuve   INTEGER DEFAULT 1
    )""")
    
    # Table des commandes
    c.execute("""CREATE TABLE IF NOT EXISTS commandes (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        contenu_id INTEGER,
        telephone  TEXT,
        montant    INTEGER,
        statut     TEXT DEFAULT 'en_attente',
        token_dl   TEXT UNIQUE,
        telecharge INTEGER DEFAULT 0,
        date_cmd   TEXT DEFAULT ''
    )""")
    
    conn.commit()
    conn.close()

def get_db():
    """Retourne une connexion à la base de données"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def get_contenus(type_filtre=None):
    """Récupère tous les contenus actifs, éventuellement filtrés par type"""
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
    """Récupère les commentaires approuvés pour un contenu"""
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM commentaires WHERE contenu_id=? AND approuve=1 ORDER BY id DESC",
        (contenu_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def add_contenu(data):
    """Ajoute un nouveau contenu"""
    conn = get_db()
    c = conn.execute("""INSERT INTO contenus
        (type, titre, auteur, genre, description, extrait, prix, gratuit,
         couverture, lien_drive, lien_media, date_ajout)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
        (data["type"], data["titre"], data["auteur"], data["genre"],
         data["description"], data["extrait"], data["prix"], data["gratuit"],
         data["couverture"], data["lien_drive"], data["lien_media"],
         datetime.now().strftime("%Y-%m-%d")))
    lid = c.lastrowid
    conn.commit()
    conn.close()
    logging.info(f"Contenu ajouté : {data['titre']} ({data['type']})")
    return lid

def update_contenu(lid, data):
    """Met à jour un contenu existant"""
    conn = get_db()
    conn.execute("""UPDATE contenus SET
        type=?, titre=?, auteur=?, genre=?, description=?, extrait=?, prix=?,
        gratuit=?, couverture=?, lien_drive=?, lien_media=? WHERE id=?""",
        (data["type"], data["titre"], data["auteur"], data["genre"],
         data["description"], data["extrait"], data["prix"], data["gratuit"],
         data["couverture"], data["lien_drive"], data["lien_media"], lid))
    conn.commit()
    conn.close()

def delete_contenu(lid):
    """Désactive un contenu (suppression logique)"""
    conn = get_db()
    conn.execute("UPDATE contenus SET actif=0 WHERE id=?", (lid,))
    conn.commit()
    conn.close()

def add_commentaire(contenu_id, nom, texte):
    """Ajoute un commentaire"""
    conn = get_db()
    conn.execute("""INSERT INTO commentaires (contenu_id, nom, texte, date_com)
        VALUES(?,?,?,?)""",
        (contenu_id, nom, texte, datetime.now().strftime("%Y-%m-%d %H:%M")))
    conn.commit()
    conn.close()

def delete_commentaire(com_id):
    """Supprime un commentaire"""
    conn = get_db()
    conn.execute("DELETE FROM commentaires WHERE id=?", (com_id,))
    conn.commit()
    conn.close()

def get_stats():
    """Récupère les statistiques"""
    conn = get_db()
    total   = conn.execute("SELECT COUNT(*) FROM contenus WHERE actif=1").fetchone()[0]
    gratuit = conn.execute("SELECT COUNT(*) FROM contenus WHERE actif=1 AND gratuit=1").fetchone()[0]
    ventes  = conn.execute("SELECT COUNT(*) FROM commandes WHERE statut='paye'").fetchone()[0]
    revenus = conn.execute("SELECT SUM(montant) FROM commandes WHERE statut='paye'").fetchone()[0] or 0
    coms    = conn.execute("SELECT COUNT(*) FROM commentaires WHERE approuve=1").fetchone()[0]
    conn.close()
    return {
        "total": total,
        "gratuit": gratuit,
        "ventes": ventes,
        "revenus": revenus,
        "commentaires": coms
    }

def ajouter_commande(contenu_id, telephone, montant):
    """Crée une nouvelle commande"""
    conn = get_db()
    token = hashlib.sha256(f"{contenu_id}{telephone}{datetime.now()}".encode()).hexdigest()[:16]
    c = conn.execute("""INSERT INTO commandes
        (contenu_id, telephone, montant, token_dl, date_cmd)
        VALUES(?,?,?,?,?)""",
        (contenu_id, telephone, montant, token, datetime.now().isoformat()))
    cmd_id = c.lastrowid
    conn.commit()
    conn.close()
    return cmd_id, token

def valider_paiement(commande_id):
    """Valide un paiement (simulation)"""
    conn = get_db()
    conn.execute("UPDATE commandes SET statut='paye' WHERE id=?", (commande_id,))
    conn.commit()
    conn.close()

def get_commande(commande_id):
    """Récupère une commande"""
    conn = get_db()
    row = conn.execute("SELECT * FROM commandes WHERE id=?", (commande_id,)).fetchone()
    conn.close()
    return dict(row) if row else None

# ═════════════════════════════════════════════════════════════════════
# GÉNÉRATEUR HTML
# ═════════════════════════════════════════════════════════════════════
def generer_html(contenus):
    """Génère le HTML du site à partir des contenus"""
    cartes = ""
    
    for b in contenus:
        cover = f"covers/{Path(b['couverture']).name}" if b["couverture"] else "covers/placeholder.jpg"
        badge = "GRATUIT" if b["gratuit"] else (f"{b['prix']} FCFA" if b["prix"] else "")
        badge_cls = "free" if b["gratuit"] else ("paid" if b["prix"] else "")

        # Boutons selon type et mode
        btns = ""
        if b["extrait"]:
            extrait_safe = b["extrait"].replace("\\","\\\\").replace("`","'").replace("\n","\\n").replace("\r","")
            titre_safe   = b["titre"].replace("'","\\'")
            btns += f'<button class="btn-card ext-btn" onclick="ouvrirExtrait(\'{extrait_safe}\',\'{titre_safe}\')">📖 Lire un extrait</button>'

        msg_disc = req.utils.quote("Bonjour, je voudrais discuter du contenu : " + b["titre"])
        wa_discuter = f"https://wa.me/{CONFIG['WHATSAPP']}?text={msg_disc}"
        btns += f'<a href="{wa_discuter}" target="_blank" class="btn-card disc-btn">💬 Discuter</a>'

        if b["gratuit"] and b["lien_drive"]:
            btns += f'<a href="{b["lien_drive"]}" target="_blank" class="btn-card free-btn">↓ Télécharger</a>'
        elif b["lien_media"] and b["type"] in ("audio","video"):
            if b["prix"] and not b["gratuit"]:
                wa_msg = f"Bonjour, je souhaite accéder à « {b['titre']} » à {b['prix']} FCFA."
                wa = f"https://wa.me/{CONFIG['WHATSAPP']}?text={req.utils.quote(wa_msg)}"
                btns += f'<a href="{wa}" target="_blank" class="btn-card buy-btn">🛒 Commander</a>'
            else:
                btns += f'<a href="{b["lien_media"]}" target="_blank" class="btn-card free-btn">▶ Écouter / Voir</a>'
        elif b["type"] == "app":
            if b["gratuit"] and b["lien_drive"]:
                btns += f'<a href="{b["lien_drive"]}" target="_blank" class="btn-card free-btn">↓ Télécharger</a>'
            else:
                wa_msg = f"Bonjour, je souhaite acquérir l'application « {b['titre']} » à {b['prix']} FCFA."
                wa = f"https://wa.me/{CONFIG['WHATSAPP']}?text={req.utils.quote(wa_msg)}"
                btns += f'<a href="{wa}" target="_blank" class="btn-card buy-btn">🛒 Commander</a>'
        elif not b["gratuit"] and b["prix"]:
            btns += ('<button class="btn-card buy-btn" onclick="acheter(' +
                str(b['id']) + ',' + str(b['prix']) + ',\'' + b['titre'].replace("'","\\'") + '\')">'
                '🛒 Acheter — ' + str(b['prix']) + ' FCFA</button>')

        # Commentaires
        coms = get_commentaires(b["id"])
        coms_html = ""
        for com in coms[:3]:
            coms_html += f"""<div class="com-item">
              <span class="com-nom">{com['nom']}</span>
              <span class="com-date">{com['date_com'][:10]}</span>
              <p class="com-txt">{com['texte']}</p>
            </div>"""
        nb_coms = len(coms)

        type_icon = {"livre":"📚","app":"💻","audio":"🎵","video":"🎬","autre":"📦"}.get(b["type"],"📦")

        badge_html = f'<span class="badge {badge_cls}">{badge}</span>' if badge else ""

        cartes += f"""<div class="card" data-type="{b['type']}" data-id="{b['id']}">
          <div class="cover-wrap">
            <img src="{cover}" alt="{b['titre']}" loading="lazy"/>
            {badge_html}
            <span class="type-icon">{type_icon}</span>
          </div>
          <div class="card-body">
            <span class="genre-tag">{b['genre']}</span>
            <h3>{b['titre']}</h3>
            <p class="auteur">{b['auteur']}</p>
            <p class="desc">{b['description'][:150]}{'...' if len(b['description'])>150 else ''}</p>
            <div class="btns">{btns}</div>
            <div class="coms-section">
              <div class="coms-toggle" onclick="toggleComs(this)">
                💬 {nb_coms} commentaire{'s' if nb_coms!=1 else ''}
              </div>
              <div class="coms-body" style="display:none">
                {coms_html}
                <div class="com-form">
                  <input class="com-input" placeholder="Votre nom" id="nom-{b['id']}"/>
                  <textarea class="com-input" placeholder="Votre commentaire..." id="txt-{b['id']}" rows="2"></textarea>
                  <button class="btn-com" onclick="envoyerCom({b['id']})">Envoyer</button>
                </div>
              </div>
            </div>
          </div>
        </div>"""

    types  = sorted(set(b["type"] for b in contenus))
    filtres = '<button class="filter active" data-f="tous">Tous</button>'
    labels  = {"livre":"📚 Livres","app":"💻 Applications","audio":"🎵 Audios",
               "video":"🎬 Vidéos","autre":"📦 Autres"}
    for t in types:
        filtres += f'<button class="filter" data-f="{t}">{labels.get(t,t)}</button>'

    s = get_stats()

    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1.0"/>
<title>Sophitek Studio — Boutique</title>
<link href="https://fonts.googleapis.com/css2?family=Playfair+Display:wght@700;900&family=Cormorant+Garamond:wght@300;400;600&family=Space+Mono&display=swap" rel="stylesheet"/>
<style>
:root{{--n:#0a0a0a;--g:#1a1a1a;--g2:#2a2a2a;--g3:#333;--r:#c0392b;--r2:#e74c3c;
      --b:#f5f0e8;--t:#d4cfc7;--v:#27ae60;--or:#b8960c;--bl:#2980b9;}}
*{{margin:0;padding:0;box-sizing:border-box;}}
body{{background:var(--n);color:var(--b);font-family:'Cormorant Garamond',serif;}}
header{{text-align:center;padding:50px 20px 28px;border-bottom:1px solid rgba(192,57,43,.3);}}
.label{{font-family:'Space Mono',monospace;font-size:10px;letter-spacing:5px;
        color:var(--r);text-transform:uppercase;margin-bottom:12px;}}
h1{{font-family:'Playfair Display',serif;font-size:clamp(36px,7vw,80px);
    font-weight:900;line-height:.9;}}
h1 span{{color:var(--r);}}
.sub{{font-size:14px;color:var(--t);letter-spacing:2px;margin-top:14px;}}
.stats{{display:flex;justify-content:center;gap:40px;padding:18px;
        background:var(--g);border-bottom:1px solid rgba(192,57,43,.2);flex-wrap:wrap;}}
.stat{{text-align:center;}}
.sn{{font-family:'Playfair Display',serif;font-size:24px;font-weight:700;
     color:var(--r);display:block;}}
.sl{{font-family:'Space Mono',monospace;font-size:9px;letter-spacing:3px;
     color:var(--t);text-transform:uppercase;}}
.filters{{display:flex;justify-content:center;gap:8px;padding:24px 16px;flex-wrap:wrap;}}
.filter{{font-family:'Space Mono',monospace;font-size:10px;letter-spacing:2px;
         text-transform:uppercase;padding:7px 16px;
         border:1px solid rgba(192,57,43,.4);background:transparent;
         color:var(--t);cursor:pointer;transition:.3s;}}
.filter:hover,.filter.active{{background:var(--r);color:var(--b);border-color:var(--r);}}
main{{max-width:1300px;margin:0 auto;padding:8px 24px 80px;}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:32px;}}
.card.hidden{{display:none;}}
.card{{background:var(--g);border:1px solid rgba(255,255,255,.06);transition:.3s;}}
.card:hover{{border-color:rgba(192,57,43,.3);transform:translateY(-2px);}}
.cover-wrap{{position:relative;aspect-ratio:2/3;overflow:hidden;background:var(--g2);}}
.cover-wrap img{{width:100%;height:100%;object-fit:cover;transition:.5s;}}
.card:hover .cover-wrap img{{transform:scale(1.04);}}
.badge{{position:absolute;top:10px;right:10px;font-family:'Space Mono',monospace;
        font-size:10px;font-weight:700;padding:3px 8px;color:#fff;}}
.badge.free{{background:var(--v);}}
.badge.paid{{background:var(--r);}}
.type-icon{{position:absolute;top:10px;left:10px;font-size:18px;
            background:rgba(0,0,0,.6);padding:4px 6px;border-radius:4px;}}
.card-body{{padding:14px;}}
.genre-tag{{font-family:'Space Mono',monospace;font-size:9px;letter-spacing:3px;
            color:var(--r);text-transform:uppercase;}}
h3{{font-family:'Playfair Display',serif;font-size:17px;font-weight:700;
    color:var(--b);line-height:1.2;margin:5px 0 3px;}}
.auteur{{font-size:12px;color:var(--t);margin-bottom:6px;}}
.desc{{font-size:12px;color:var(--t);line-height:1.5;margin-bottom:10px;}}
.btns{{display:flex;flex-direction:column;gap:6px;margin-bottom:10px;}}
.btn-card{{display:block;width:100%;padding:9px;font-family:'Space Mono',monospace;
           font-size:10px;letter-spacing:2px;text-transform:uppercase;text-align:center;
           text-decoration:none;border:none;cursor:pointer;transition:.2s;}}
.buy-btn{{background:var(--r);color:#fff;}}
.buy-btn:hover{{background:var(--r2);}}
.free-btn{{background:var(--v);color:#fff;}}
.free-btn:hover{{background:#2ecc71;}}
.disc-btn{{background:var(--g3);color:var(--b);border:1px solid rgba(255,255,255,.15);}}
.disc-btn:hover{{background:#25D366;border-color:#25D366;}}
.ext-btn{{background:var(--or);color:#fff;}}
.ext-btn:hover{{background:#d4a017;}}
/* Commentaires */
.coms-section{{border-top:1px solid rgba(255,255,255,.08);padding-top:10px;margin-top:4px;}}
.coms-toggle{{font-family:'Space Mono',monospace;font-size:10px;color:var(--t);
              cursor:pointer;padding:4px 0;}}
.coms-toggle:hover{{color:var(--b);}}
.com-item{{padding:8px 0;border-bottom:1px solid rgba(255,255,255,.06);}}
.com-nom{{font-family:'Space Mono',monospace;font-size:10px;color:var(--r);font-weight:700;}}
.com-date{{font-family:'Space Mono',monospace;font-size:9px;color:rgba(255,255,255,.3);
           margin-left:8px;}}
.com-txt{{font-size:12px;color:var(--t);margin-top:4px;line-height:1.5;}}
.com-form{{margin-top:10px;display:flex;flex-direction:column;gap:6px;}}
.com-input{{background:var(--g2);border:1px solid rgba(255,255,255,.1);color:var(--b);
            font-family:'Cormorant Garamond',serif;font-size:13px;
            padding:7px 10px;outline:none;resize:none;}}
.com-input:focus{{border-color:var(--r);}}
.btn-com{{background:var(--bl);color:#fff;border:none;
          font-family:'Space Mono',monospace;font-size:10px;letter-spacing:2px;
          padding:8px;cursor:pointer;transition:.2s;}}
.btn-com:hover{{background:#3498db;}}
/* Modal extrait */
.modal-ov{{display:none;position:fixed;inset:0;background:rgba(0,0,0,.92);
           z-index:1000;align-items:center;justify-content:center;padding:20px;}}
.modal-ov.open{{display:flex;}}
.modal{{background:var(--g);border:1px solid rgba(192,57,43,.4);
        max-width:640px;width:100%;max-height:85vh;overflow-y:auto;padding:32px;
        position:relative;}}
.modal h2{{font-family:'Playfair Display',serif;font-size:22px;color:var(--b);
           margin-bottom:16px;padding-right:30px;}}
.modal-txt{{font-size:15px;color:var(--t);line-height:1.9;white-space:pre-wrap;}}
.modal-close{{position:absolute;top:14px;right:14px;background:none;border:none;
              color:var(--t);font-size:22px;cursor:pointer;}}
/* Modal paiement */
.pay-modal{{background:var(--g);border:1px solid rgba(192,57,43,.4);
            max-width:420px;width:100%;padding:32px;position:relative;}}
.pay-titre{{font-family:'Playfair Display',serif;font-size:20px;
            color:var(--b);margin-bottom:6px;}}
.pay-prix{{font-family:'Playfair Display',serif;font-size:28px;
           color:var(--r);margin-bottom:16px;}}
.pay-label{{font-family:'Space Mono',monospace;font-size:10px;letter-spacing:2px;
            color:var(--t);text-transform:uppercase;margin-bottom:6px;display:block;}}
.pay-input{{width:100%;background:var(--g2);border:1px solid rgba(255,255,255,.1);
            color:var(--b);font-size:18px;padding:12px;outline:none;margin-bottom:14px;}}
.pay-input:focus{{border-color:var(--r);}}
.pay-btn{{width:100%;background:var(--r);color:#fff;border:none;
          font-family:'Space Mono',monospace;font-size:12px;letter-spacing:3px;
          text-transform:uppercase;padding:14px;cursor:pointer;transition:.2s;}}
.pay-btn:hover{{background:var(--r2);}}
.pay-status{{text-align:center;padding:10px 0;font-size:13px;color:var(--t);}}
.spinner{{width:36px;height:36px;border:3px solid rgba(192,57,43,.3);
          border-top-color:var(--r);border-radius:50%;
          animation:spin 1s linear infinite;margin:10px auto;}}
@keyframes spin{{to{{transform:rotate(360deg);}}}}
.empty{{text-align:center;padding:80px 20px;color:rgba(255,255,255,.3);
        font-size:18px;grid-column:1/-1;font-family:'Space Mono',monospace;
        letter-spacing:2px;}}
footer{{text-align:center;padding:32px;border-top:1px solid rgba(192,57,43,.2);}}
footer p{{font-family:'Space Mono',monospace;font-size:10px;letter-spacing:3px;
          color:rgba(255,255,255,.3);text-transform:uppercase;}}
footer span{{color:var(--r);}}
@media(max-width:600px){{
  .grid{{grid-template-columns:repeat(2,1fr);gap:14px;}}
  .stats{{gap:20px;}}
  .cover-wrap{{aspect-ratio:2/3;}}
}}
</style>
</head>
<body>
<header>
  <div class="label">Sophitek Studio — Boutique Officielle</div>
  <h1>SOPHITEK<br/><span>STUDIO</span></h1>
  <p class="sub">Japhet Arcade Sophiano ASSOGBA</p>
</header>
<div class="stats">
  <div class="stat"><span class="sn">{s['total']}</span><span class="sl">Contenus</span></div>
  <div class="stat"><span class="sn">{s['gratuit']}</span><span class="sl">Gratuits</span></div>
  <div class="stat"><span class="sn">{s['ventes']}</span><span class="sl">Ventes</span></div>
  <div class="stat"><span class="sn">{s['revenus']:,}</span><span class="sl">FCFA</span></div>
  <div class="stat"><span class="sn">{s['commentaires']}</span><span class="sl">Avis</span></div>
</div>
<div class="filters" id="filters">{filtres}</div>
<main><div class="grid" id="grid">
{"".join([cartes]) if contenus else '<div class="empty">Aucun contenu disponible.</div>'}
</div></main>
<footer><p>© 2026 <span>Sophitek Studio</span> — Tous droits réservés</p></footer>

<!-- Modal Extrait -->
<div class="modal-ov" id="modal-ext">
  <div class="modal">
    <button class="modal-close" onclick="fermerModal('modal-ext')">✕</button>
    <h2 id="ext-titre"></h2>
    <div class="modal-txt" id="ext-txt"></div>
  </div>
</div>

<!-- Modal Paiement -->
<div class="modal-ov" id="modal-pay">
  <div class="pay-modal">
    <button class="modal-close" onclick="fermerModal('modal-pay')">✕</button>
    <div class="pay-titre" id="pay-titre"></div>
    <div class="pay-prix" id="pay-prix"></div>
    <div id="pay-step1">
      <span class="pay-label">Votre numéro MTN / Moov</span>
      <input class="pay-input" id="pay-tel" placeholder="ex: 67000000" maxlength="12"/>
      <button class="pay-btn" onclick="confirmerPaiement()">💳 Payer maintenant</button>
    </div>
    <div id="pay-step2" style="display:none;text-align:center;">
      <div class="spinner"></div>
      <p class="pay-status">Validez le paiement sur votre téléphone...<br/>
      Vérification automatique en cours.</p>
    </div>
    <div id="pay-step3" style="display:none;text-align:center;">
      <p style="font-size:40px;margin:10px 0">✅</p>
      <p style="font-family:'Playfair Display',serif;font-size:20px;color:#27ae60;margin-bottom:12px">
        Paiement confirmé !</p>
      <a id="pay-lien" href="#" class="pay-btn" style="background:#27ae60;display:block;
         text-decoration:none;text-align:center;" target="_blank">↓ Télécharger</a>
      <p style="font-family:'Space Mono',monospace;font-size:10px;color:rgba(255,255,255,.4);
         margin-top:8px;">⚠ Lien valide pour 1 seul téléchargement</p>
    </div>
    <div id="pay-step4" style="display:none;text-align:center;">
      <p style="font-size:36px;margin:10px 0">❌</p>
      <p style="color:#e74c3c;margin-bottom:16px;">Paiement non abouti. Réessayez.</p>
      <button class="pay-btn" onclick="resetPaiement()" style="background:var(--g3)">↺ Réessayer</button>
    </div>
  </div>
</div>

<script>
const API = "{CONFIG['RENDER_URL']}";
let payContenuid=null, payCommandeid=null, payInterval=null;

// ── FILTRES
document.querySelectorAll('.filter').forEach(btn=>{{
  btn.addEventListener('click',()=>{{
    document.querySelectorAll('.filter').forEach(b=>b.classList.remove('active'));
    btn.classList.add('active');
    const f=btn.dataset.f;
    document.querySelectorAll('.card').forEach(c=>{{
      c.classList.toggle('hidden',f!=='tous'&&c.dataset.type!==f);
    }});
  }});
}});

// ── EXTRAIT
function ouvrirExtrait(txt, titre){{
  document.getElementById('ext-titre').textContent=titre;
  document.getElementById('ext-txt').textContent=txt;
  document.getElementById('modal-ext').classList.add('open');
}}

// ── COMMENTAIRES
function toggleComs(el){{
  const body=el.nextElementSibling;
  body.style.display=body.style.display==='none'?'block':'none';
}}

async function envoyerCom(id){{
  const nom=document.getElementById('nom-'+id).value.trim();
  const txt=document.getElementById('txt-'+id).value.trim();
  if(!nom||!txt){{alert('Remplissez votre nom et votre commentaire.');return;}}
  try{{
    const r=await fetch(API+'/commentaire',{{
      method:'POST',headers:{{'Content-Type':'application/json'}},
      body:JSON.stringify({{contenu_id:id,nom,texte:txt}})
    }});
    if(r.ok){{
      document.getElementById('nom-'+id).value='';
      document.getElementById('txt-'+id).value='';
      alert('Merci pour votre commentaire ! Il sera affiché après validation.');
    }}
  }}catch(e){{alert('Erreur. Réessayez.');}}
}}

// ── PAIEMENT
function acheter(id, prix, titre){{
  payContenuid=id;
  document.getElementById('pay-titre').textContent=titre;
  document.getElementById('pay-prix').textContent=prix+' FCFA';
  resetPaiement();
  document.getElementById('modal-pay').classList.add('open');
}}

async function confirmerPaiement(){{
  const tel=document.getElementById('pay-tel').value.trim();
  if(!tel||tel.length<8){{alert('Entrez un numéro valide.');return;}}
  document.getElementById('pay-step1').style.display='none';
  document.getElementById('pay-step2').style.display='block';
  try{{
    const r=await fetch(API+'/acheter/'+payContenuid,{{
      method:'POST',headers:{{'Content-Type':'application/json'}},
      body:JSON.stringify({{telephone:tel}})
    }});
    const d=await r.json();
    if(!d.success)throw new Error(d.erreur);
    payCommandeid=d.commande_id;
    demarrerVerification();
  }}catch(e){{
    document.getElementById('pay-step2').style.display='none';
    document.getElementById('pay-step4').style.display='block';
  }}
}}

function demarrerVerification(){{
  let n=0;
  payInterval=setInterval(async()=>{{
    n++;
    if(n>60){{clearInterval(payInterval);showPayStep(4);return;}}
    try{{
      const r=await fetch(API+'/verifier/'+payCommandeid);
      const d=await r.json();
      if(d.statut==='paye'){{
        clearInterval(payInterval);
        document.getElementById('pay-lien').href=d.lien;
        showPayStep(3);
      }}else if(d.statut==='echec'){{
        clearInterval(payInterval);showPayStep(4);
      }}
    }}catch(e){{}}
  }},5000);
}}

function showPayStep(n){{
  [1,2,3,4].forEach(i=>{{
    document.getElementById('pay-step'+i).style.display=i===n?'block':'none';
  }});
}}

function resetPaiement(){{
  if(payInterval)clearInterval(payInterval);
  payCommandeid=null;
  document.getElementById('pay-tel').value='';
  showPayStep(1);
}}

function fermerModal(id){{
  document.getElementById(id).classList.remove('open');
  if(id==='modal-pay')resetPaiement();
}}
document.querySelectorAll('.modal-ov').forEach(m=>{{
  m.addEventListener('click',e=>{{if(e.target===m)fermerModal(m.id);}});
}});
document.addEventListener('keydown',e=>{{
  if(e.key==='Escape')document.querySelectorAll('.modal-ov.open').forEach(m=>fermerModal(m.id));
}});
</script>
</body></html>"""

# ═════════════════════════════════════════════════════════════════════
# GITHUB
# ═════════════════════════════════════════════════════════════════════
def github_push(contenu_bytes, chemin_repo, message):
    """Pousse un fichier vers GitHub"""
    token   = CONFIG["GITHUB_TOKEN"]
    repo    = CONFIG["GITHUB_REPO"]
    url     = f"https://api.github.com/repos/{repo}/contents/{chemin_repo}"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github+json"
    }
    
    if not token:
        return False, "Token GitHub manquant"
    
    b64 = base64.b64encode(contenu_bytes).decode()
    
    # Vérifier si le fichier existe déjà pour obtenir le SHA
    sha = None
    try:
        r = req.get(url, headers=headers, timeout=15)
        if r.status_code == 200:
            sha = r.json().get("sha")
    except Exception as e:
        return False, f"Erreur de vérification : {str(e)}"
    
    payload = {"message": message, "content": b64}
    if sha:
        payload["sha"] = sha
    
    try:
        r = req.put(url, json=payload, headers=headers, timeout=20)
        if r.status_code in (200, 201):
            return True, f"✓ {chemin_repo}"
        else:
            error_msg = r.json().get('message', 'Erreur inconnue')
            return False, f"✗ {chemin_repo} : {error_msg}"
    except Exception as e:
        return False, f"✗ {chemin_repo} : {str(e)}"

def github_get(chemin_repo):
    """Récupère un fichier depuis GitHub"""
    token   = CONFIG["GITHUB_TOKEN"]
    repo    = CONFIG["GITHUB_REPO"]
    url     = f"https://api.github.com/repos/{repo}/contents/{chemin_repo}"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github+json"
    }
    
    if not token:
        return None
    
    try:
        r = req.get(url, headers=headers, timeout=15)
        if r.status_code == 200:
            content = r.json().get("content", "")
            return base64.b64decode(content)
    except Exception:
        pass
    return None

def publier_site(callback):
    """Publie le site sur GitHub Pages"""
    contenus = get_contenus()
    msgs, errors = [], []
    
    # Générer et pousser HTML
    html = generer_html(contenus)
    HTML_PATH.write_text(html, encoding="utf-8")
    ok, msg = github_push(html.encode("utf-8"), "index.html",
                          f"Mise à jour — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    (msgs if ok else errors).append(msg)
    
    # Générer et pousser JSON
    data = [{**b, "gratuit": bool(b["gratuit"])} for b in contenus]
    json_str = json.dumps(data, ensure_ascii=False, indent=2)
    JSON_PATH.write_text(json_str, encoding="utf-8")
    ok, msg = github_push(json_str.encode("utf-8"), "data.json",
                          f"Données — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    (msgs if ok else errors).append(msg)
    
    # Pousser les couvertures
    for cover in COVERS_DIR.iterdir():
        if cover.is_file() and cover.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp"):
            ok, msg = github_push(cover.read_bytes(), f"covers/{cover.name}",
                                  f"Cover : {cover.name}")
            (msgs if ok else errors).append(msg)
    
    logging.info(f"Publication : {len(msgs)} succès, {len(errors)} erreurs")
    callback(msgs, errors)

def synchroniser(callback):
    """Télécharge data.json depuis GitHub et met à jour la DB locale"""
    try:
        data_bytes = github_get("data.json")
        if not data_bytes:
            callback(False, "Fichier data.json introuvable sur GitHub")
            return
        
        data = json.loads(data_bytes.decode("utf-8"))
        conn = get_db()
        
        for b in data:
            exists = conn.execute(
                "SELECT id FROM contenus WHERE id=?", (b["id"],)).fetchone()
            
            if exists:
                conn.execute("""UPDATE contenus SET
                    type=?, titre=?, auteur=?, genre=?, description=?, extrait=?,
                    prix=?, gratuit=?, couverture=?, lien_drive=?, lien_media=?, actif=?
                    WHERE id=?""",
                    (b.get("type", "livre"), b["titre"], b.get("auteur", ""),
                     b.get("genre", ""), b.get("description", ""), b.get("extrait", ""),
                     b.get("prix", 0), int(b.get("gratuit", False)),
                     b.get("couverture", ""), b.get("lien_drive", ""),
                     b.get("lien_media", ""), b.get("actif", 1), b["id"]))
            else:
                conn.execute("""INSERT OR IGNORE INTO contenus
                    (id, type, titre, auteur, genre, description, extrait, prix, gratuit,
                     couverture, lien_drive, lien_media, actif, date_ajout)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (b["id"], b.get("type", "livre"), b["titre"], b.get("auteur", ""),
                     b.get("genre", ""), b.get("description", ""), b.get("extrait", ""),
                     b.get("prix", 0), int(b.get("gratuit", False)),
                     b.get("couverture", ""), b.get("lien_drive", ""),
                     b.get("lien_media", ""), b.get("actif", 1),
                     b.get("date_ajout", "")))
        
        conn.commit()
        conn.close()
        logging.info(f"Synchronisation : {len(data)} contenus mis à jour")
        callback(True, f"✓ {len(data)} contenus synchronisés depuis GitHub")
    
    except Exception as e:
        logging.error(f"Erreur synchro : {e}")
        callback(False, str(e))

def sauvegarder_drive():
    """Sauvegarde le fichier Python sur GitHub"""
    try:
        script = Path(__file__).read_bytes()
        ok, msg = github_push(script, "backup/gestionnaire.py",
                              f"Backup — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        return ok, msg
    except Exception as e:
        return False, str(e)

# ═════════════════════════════════════════════════════════════════════
# FLASK
# ═════════════════════════════════════════════════════════════════════
from flask import Flask, request, jsonify, redirect, send_file

flask_app = Flask(__name__)

@flask_app.route("/")
def api_home():
    return jsonify({
        "status": "Sophitek Studio",
        "version": "2.0",
        "message": "API de la boutique Sophitek"
    })

@flask_app.route("/contenus")
def api_contenus():
    t = request.args.get("type")
    contenus = get_contenus(t)
    return jsonify([{**b, "gratuit": bool(b["gratuit"])} for b in contenus])

@flask_app.route("/commentaire", methods=["POST"])
def api_commentaire():
    d = request.get_json(silent=True) or {}
    cid = d.get("contenu_id")
    nom = str(d.get("nom", "")).strip()[:60]
    txt = str(d.get("texte", "")).strip()[:500]
    
    if not cid or not nom or not txt:
        return jsonify({"erreur": "Données manquantes"}), 400
    
    add_commentaire(cid, nom, txt)
    return jsonify({"success": True})

@flask_app.route("/acheter/<int:cid>", methods=["POST"])
def api_acheter(cid):
    conn = get_db()
    item = conn.execute(
        "SELECT * FROM contenus WHERE id=? AND actif=1", (cid,)).fetchone()
    conn.close()
    
    if not item:
        return jsonify({"erreur": "Contenu introuvable"}), 404
    
    item = dict(item)
    d = request.get_json(silent=True) or {}
    tel = str(d.get("telephone", "")).strip()
    
    if not tel or len(tel) < 8:
        return jsonify({"erreur": "Numéro invalide"}), 400
    
    cmd_id, token = ajouter_commande(cid, tel, item["prix"])
    
    return jsonify({
        "success": True,
        "commande_id": cmd_id,
        "message": "Commande créée. En attente de paiement."
    })

@flask_app.route("/verifier/<int:cmd_id>")
def api_verifier(cmd_id):
    cmd = get_commande(cmd_id)
    
    if not cmd:
        return jsonify({"erreur": "Commande introuvable"}), 404
    
    if cmd["statut"] == "paye" and cmd["token_dl"]:
        return jsonify({
            "statut": "paye",
            "lien": f"{CONFIG['RENDER_URL']}/dl/{cmd['token_dl']}"
        })
    elif cmd["statut"] == "echec":
        return jsonify({"statut": "echec"})
    
    return jsonify({"statut": "en_attente"})

@flask_app.route("/dl/<token>")
def api_dl(token):
    conn = get_db()
    row = conn.execute("""SELECT c.*, co.lien_drive FROM commandes c
        JOIN contenus co ON c.contenu_id=co.id
        WHERE c.token_dl=?""", (token,)).fetchone()
    conn.close()
    
    if not row:
        return "<h2 style='color:red;text-align:center;padding:60px;font-family:Georgia'>Lien invalide</h2>", 404
    
    row = dict(row)
    
    if row["telecharge"] >= 1:
        return "<h2 style='color:red;text-align:center;padding:60px;font-family:Georgia'>Lien déjà utilisé</h2>", 400
    
    conn = get_db()
    conn.execute("UPDATE commandes SET telecharge=telecharge+1 WHERE token_dl=?", (token,))
    conn.commit()
    conn.close()
    
    return redirect(row["lien_drive"])

@flask_app.route("/admin/stats")
def api_stats():
    if request.args.get("key") != CONFIG["ADMIN_KEY"]:
        return jsonify({"erreur": "Non autorisé"}), 403
    return jsonify(get_stats())

@flask_app.route("/webhook/paiement", methods=["POST"])
def webhook_paiement():
    """Simule un webhook de confirmation de paiement"""
    data = request.get_json(silent=True) or {}
    commande_id = data.get("commande_id")
    
    if commande_id:
        valider_paiement(commande_id)
        return jsonify({"success": True})
    
    return jsonify({"erreur": "Données manquantes"}), 400

# ═════════════════════════════════════════════════════════════════════
# INTERFACE TKINTER (uniquement en local)
# ═════════════════════════════════════════════════════════════════════
if not ON_RENDER:
    # Constantes de couleurs
    N = "#0a0a0a"
    G = "#1a1a1a"
    G2 = "#2a2a2a"
    G3 = "#333"
    R = "#c0392b"
    B = "#f5f0e8"
    T = "#d4cfc7"
    V = "#27ae60"
    OR = "#b8960c"
    BL = "#2980b9"
    
    TYPES = [
        ("livre", "📚 Livre"),
        ("app", "💻 Application"),
        ("audio", "🎵 Audio"),
        ("video", "🎬 Vidéo"),
        ("autre", "📦 Autre")
    ]
    
    class App:
        def __init__(self, root):
            self.root = root
            self.root.title("Sophitek Studio v2 — Gestionnaire")
            self.root.geometry("1150x720")
            self.root.configure(bg=N)
            self.sel_id = None
            self.cover_var = tk.StringVar()
            self.data = []
            self.coms_data = []
            self.coms_lb = None
            self.flds = {}
            
            init_db()
            self._ui()
            self._charger()
            
            # Démarrer Flask dans un thread séparé
            threading.Thread(target=demarrer_flask, daemon=True).start()
        
        def _btn(self, p, txt, cmd, bg, sz=11, fg=None):
            return tk.Button(p, text=txt, command=cmd, bg=bg, fg=fg or B,
                             font=("Courier", sz, "bold"), borderwidth=0,
                             padx=8, pady=5, cursor="hand2",
                             activebackground=R, activeforeground=B)
        
        def _entry(self, parent, key, label, multi=False):
            row = tk.Frame(parent, bg=N)
            row.pack(fill="x", padx=12, pady=3)
            tk.Label(row, text=label, font=("Courier", 9),
                     fg=T, bg=N, anchor="w").pack(fill="x")
            
            if multi:
                w = tk.Text(row, height=3, bg=G2, fg=B, insertbackground=B,
                            font=("Georgia", 11), borderwidth=0, padx=6, pady=4)
            else:
                w = tk.Entry(row, bg=G2, fg=B, insertbackground=B,
                             font=("Georgia", 12), borderwidth=0,
                             highlightthickness=1,
                             highlightbackground=G2, highlightcolor=R)
            
            w.pack(fill="x", ipady=0 if multi else 4)
            self.flds[key] = w
        
        def _ui(self):
            # Header
            hdr = tk.Frame(self.root, bg=G, pady=10)
            hdr.pack(fill="x")
            tk.Label(hdr, text="SOPHITEK STUDIO v2",
                     font=("Courier", 10), fg=R, bg=G).pack()
            tk.Label(hdr, text="Gestionnaire de Boutique",
                     font=("Georgia", 16, "bold"), fg=B, bg=G).pack()
            
            body = tk.Frame(self.root, bg=N)
            body.pack(fill="both", expand=True, padx=10, pady=8)
            
            # ── GAUCHE — Liste
            left = tk.Frame(body, bg=G2, width=280)
            left.pack(side="left", fill="y", padx=(0, 10))
            left.pack_propagate(False)
            
            tk.Label(left, text="📦  CONTENUS", font=("Courier", 10, "bold"),
                     fg=R, bg=G2, pady=6).pack(fill="x", padx=8)
            
            self.stats_lbl = tk.Label(left, text="", font=("Courier", 8),
                                      fg=T, bg=G2, anchor="w")
            self.stats_lbl.pack(fill="x", padx=8, pady=(0, 4))
            
            # Filtre type dans liste
            ff = tk.Frame(left, bg=G2)
            ff.pack(fill="x", padx=6, pady=4)
            self.type_filtre = tk.StringVar(value="tous")
            types_opts = [("Tous", "tous")] + [(t[1], t[0]) for t in TYPES]
            
            for lbl, val in types_opts:
                tk.Radiobutton(ff, text=lbl, variable=self.type_filtre,
                               value=val, command=self._charger,
                               bg=G2, fg=T, selectcolor=R,
                               activebackground=G2,
                               font=("Courier", 8)).pack(anchor="w", padx=4)
            
            sf = tk.Frame(left, bg=G2)
            sf.pack(fill="both", expand=True, padx=6)
            sb = ttk.Scrollbar(sf)
            sb.pack(side="right", fill="y")
            
            self.lb = tk.Listbox(sf, bg=G, fg=B, selectbackground=R,
                                  font=("Georgia", 11), borderwidth=0,
                                  highlightthickness=0, activestyle="none",
                                  yscrollcommand=sb.set, cursor="hand2")
            self.lb.pack(side="left", fill="both", expand=True)
            sb.config(command=self.lb.yview)
            self.lb.bind("<<ListboxSelect>>", self._on_sel)
            
            bf = tk.Frame(left, bg=G2, pady=4)
            bf.pack(fill="x", padx=6)
            self._btn(bf, "＋ Nouveau",  self._nouveau,   V, 10).pack(fill="x", pady=2)
            self._btn(bf, "✕ Supprimer", self._supprimer, R, 10).pack(fill="x", pady=2)
            self._btn(bf, "🗨 Commentaires", self._voir_coms, BL, 10).pack(fill="x", pady=2)
            
            # ── DROITE — Formulaire + Actions
            right = tk.Frame(body, bg=N)
            right.pack(side="left", fill="both", expand=True)
            
            frm = tk.LabelFrame(right, text="  DÉTAILS DU CONTENU  ",
                                 font=("Courier", 10), fg=R, bg=N,
                                 bd=1, relief="solid", labelanchor="n")
            frm.pack(fill="both", expand=True, pady=(0, 6))
            
            # Type
            tr = tk.Frame(frm, bg=N)
            tr.pack(fill="x", padx=12, pady=4)
            tk.Label(tr, text="Type *", font=("Courier", 9),
                     fg=T, bg=N, anchor="w").pack(fill="x")
            
            self.type_var = tk.StringVar(value="livre")
            type_row = tk.Frame(tr, bg=N)
            type_row.pack(fill="x")
            
            for lbl, val in TYPES:
                tk.Radiobutton(type_row, text=lbl, variable=self.type_var,
                               value=val, bg=N, fg=B, selectcolor=R,
                               activebackground=N,
                               font=("Courier", 9)).pack(side="left", padx=4)
            
            self.flds = {}
            self._entry(frm, "titre",       "Titre *")
            self._entry(frm, "auteur",      "Auteur")
            self._entry(frm, "genre",       "Genre / Catégorie")
            self._entry(frm, "prix",        "Prix (FCFA) — 0 si gratuit")
            self._entry(frm, "lien_drive",  "Lien Google Drive (téléchargement)")
            self._entry(frm, "lien_media",  "Lien média (audio/vidéo YouTube ou Drive)")
            self._entry(frm, "description", "Description", multi=True)
            self._entry(frm, "extrait",     "Extrait lisible (texte)", multi=True)
            
            ex = tk.Frame(frm, bg=N)
            ex.pack(fill="x", padx=12, pady=4)
            self.grat_var = tk.BooleanVar()
            tk.Checkbutton(ex, text="✓ Accès gratuit",
                           variable=self.grat_var,
                           bg=N, fg=B, selectcolor=R,
                           activebackground=N,
                           font=("Courier", 10)).pack(side="left")
            self._btn(ex, "🖼 Couverture", self._couverture, G2, 9).pack(side="left", padx=8)
            tk.Label(ex, textvariable=self.cover_var,
                     font=("Courier", 8), fg=OR, bg=N).pack(side="left")
            
            sr = tk.Frame(frm, bg=N, pady=5)
            sr.pack(fill="x", padx=12)
            self._btn(sr, "💾  ENREGISTRER", self._enregistrer, V, 11).pack(side="left", padx=(0, 6))
            self._btn(sr, "✕  ANNULER",      self._vider,       G2, 11).pack(side="left")
            
            # ── ACTIONS
            act = tk.LabelFrame(right, text="  ACTIONS  ",
                                 font=("Courier", 10), fg=R, bg=N,
                                 bd=1, relief="solid", labelanchor="n")
            act.pack(fill="x")
            ai = tk.Frame(act, bg=N, pady=6)
            ai.pack(fill="x", padx=10)
            self._btn(ai, "🌐 PUBLIER",      self._publier,    R,  11).pack(side="left", padx=(0, 6))
            self._btn(ai, "⟳ SYNCHRONISER", self._synchroniser, BL, 11).pack(side="left", padx=(0, 6))
            self._btn(ai, "💾 SAUVEGARDER",  self._sauvegarder, OR, 11).pack(side="left", padx=(0, 6))
            self._btn(ai, "👁 APERÇU",       self._apercu,      G2, 11).pack(side="left", padx=(0, 6))
            self._btn(ai, "🔗 SITE EN LIGNE", self._ouvrir_site, G2, 11).pack(side="left")
            
            self.act_lbl = tk.Label(act, text="", font=("Courier", 9),
                                    fg=V, bg=N, pady=3)
            self.act_lbl.pack()
        
        # ── LISTE
        def _charger(self):
            self.lb.delete(0, tk.END)
            t = self.type_filtre.get()
            self.data = get_contenus(None if t == "tous" else t)
            icons = {"livre": "📚", "app": "💻", "audio": "🎵", "video": "🎬", "autre": "📦"}
            
            for b in self.data:
                ic = icons.get(b["type"], "📦")
                tag = "🆓" if b["gratuit"] else f"{b['prix']}F"
                self.lb.insert(tk.END, f"  {ic} {b['titre']}  [{tag}]")
            
            s = get_stats()
            self.stats_lbl.config(
                text=f"  {s['total']} · {s['ventes']} ventes · {s['revenus']:,}F")
        
        def _on_sel(self, _):
            sel = self.lb.curselection()
            if not sel:
                return
            
            b = self.data[sel[0]]
            self.sel_id = b["id"]
            self._vider()
            self.type_var.set(b.get("type", "livre"))
            
            for k in ["titre", "auteur", "genre", "prix", "lien_drive", "lien_media"]:
                self.flds[k].insert(0, str(b.get(k, "")))
            
            self.flds["description"].insert("1.0", b.get("description", ""))
            self.flds["extrait"].insert("1.0", b.get("extrait", ""))
            self.grat_var.set(bool(b.get("gratuit", 0)))
            self.cover_var.set(b.get("couverture", ""))
        
        def _vider(self):
            self.sel_id = None
            for k, w in self.flds.items():
                if isinstance(w, tk.Text):
                    w.delete("1.0", tk.END)
                else:
                    w.delete(0, tk.END)
            self.grat_var.set(False)
            self.cover_var.set("")
            self.type_var.set("livre")
        
        def _get_data(self):
            try:
                prix = int(self.flds["prix"].get().strip() or "0")
            except:
                prix = 0
            
            return {
                "type":        self.type_var.get(),
                "titre":       self.flds["titre"].get().strip(),
                "auteur":      self.flds["auteur"].get().strip() or "Japhet Arcade Sophiano ASSOGBA",
                "genre":       self.flds["genre"].get().strip(),
                "description": self.flds["description"].get("1.0", tk.END).strip(),
                "extrait":     self.flds["extrait"].get("1.0", tk.END).strip(),
                "prix":        prix,
                "gratuit":     int(self.grat_var.get()),
                "couverture":  self.cover_var.get(),
                "lien_drive":  self.flds["lien_drive"].get().strip(),
                "lien_media":  self.flds["lien_media"].get().strip(),
            }
        
        # ── CRUD
        def _nouveau(self):
            self._vider()
            self.flds["titre"].focus()
        
        def _enregistrer(self):
            d = self._get_data()
            if not d["titre"]:
                messagebox.showerror("Erreur", "Le titre est obligatoire.")
                return
            
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
                messagebox.showinfo("Info", "Sélectionne un contenu.")
                return
            
            titre = self.data[sel[0]]["titre"]
            if messagebox.askyesno("Confirmer", f"Supprimer « {titre} » ?"):
                delete_contenu(self.sel_id)
                self._vider()
                self._charger()
        
        def _couverture(self):
            path = filedialog.askopenfilename(
                title="Choisir une image",
                filetypes=[("Images", "*.jpg *.jpeg *.png *.webp")])
            
            if path:
                nom = Path(path).name
                dest = COVERS_DIR / nom
                shutil.copy2(path, dest)
                self.cover_var.set(f"covers/{nom}")
        
        # ── COMMENTAIRES
        def _voir_coms(self):
            if not self.sel_id:
                messagebox.showinfo("Info", "Sélectionne un contenu d'abord.")
                return
            
            win = tk.Toplevel(self.root)
            win.title("Commentaires")
            win.geometry("500x420")
            win.configure(bg=N)
            
            coms = get_commentaires(self.sel_id)
            tk.Label(win, text=f"Commentaires ({len(coms)})",
                     font=("Georgia", 14, "bold"), fg=R, bg=N, pady=10).pack()
            
            sf = tk.Frame(win, bg=N)
            sf.pack(fill="both", expand=True, padx=10, pady=5)
            sb = ttk.Scrollbar(sf)
            sb.pack(side="right", fill="y")
            
            lb = tk.Listbox(sf, bg=G, fg=B, font=("Georgia", 11),
                            borderwidth=0, highlightthickness=0,
                            yscrollcommand=sb.set)
            lb.pack(side="left", fill="both", expand=True)
            sb.config(command=lb.yview)
            
            for c in coms:
                lb.insert(tk.END, f"  {c['nom']} ({c['date_com'][:10]}) : {c['texte'][:60]}")
            
            self.coms_data = coms
            self.coms_lb = lb
            
            def supprimer_com():
                sel = lb.curselection()
                if not sel:
                    return
                com = coms[sel[0]]
                if messagebox.askyesno("Confirmer", "Supprimer ce commentaire ?"):
                    delete_commentaire(com["id"])
                    lb.delete(sel[0])
            
            self._btn(win, "✕ Supprimer commentaire", supprimer_com, R, 11).pack(pady=6)
        
        # ── ACTIONS
        def _apercu(self):
            contenus = get_contenus()
            html = generer_html(contenus)
            HTML_PATH.write_text(html, encoding="utf-8")
            webbrowser.open(str(HTML_PATH))
        
        def _ouvrir_site(self):
            webbrowser.open(CONFIG["SITE_URL"])
        
        def _publier(self):
            self.act_lbl.config(text="⏳ Publication en cours...", fg=OR)
            self.root.update()
            
            def callback(msgs, errors):
                if errors and not msgs:
                    self.act_lbl.config(text=f"✗ Échec : {errors[0]}", fg=R)
                    messagebox.showerror("Erreur", "\n".join(errors[:3]))
                else:
                    self.act_lbl.config(
                        text=f"✓ Publié ! {len(msgs)} fichier(s) mis à jour", fg=V)
                    messagebox.showinfo("✓ Succès !",
                        f"Site mis à jour !\n\nVisible dans 1-2 min sur :\n{CONFIG['SITE_URL']}")
                self._charger()
            
            threading.Thread(target=publier_site, args=(callback,), daemon=True).start()
        
        def _synchroniser(self):
            if not messagebox.askyesno("Synchroniser",
                "Mettre à jour l'app depuis GitHub ?\n"
                "Les contenus locaux seront mis à niveau."):
                return
            
            self.act_lbl.config(text="⏳ Synchronisation...", fg=OR)
            self.root.update()
            
            def callback(ok, msg):
                if ok:
                    self.act_lbl.config(text=msg, fg=V)
                    messagebox.showinfo("✓ Synchronisé", msg)
                    self._charger()
                else:
                    self.act_lbl.config(text=f"✗ {msg}", fg=R)
                    messagebox.showerror("Erreur", msg)
            
            threading.Thread(target=synchroniser, args=(callback,), daemon=True).start()
        
        def _sauvegarder(self):
            self.act_lbl.config(text="⏳ Sauvegarde en cours...", fg=OR)
            self.root.update()
            
            def do():
                ok, msg = sauvegarder_drive()
                if ok:
                    self.act_lbl.config(text=f"✓ Sauvegardé sur GitHub/backup", fg=V)
                    messagebox.showinfo("✓ Sauvegardé",
                        "Fichier gestionnaire.py sauvegardé dans\n"
                        "sophitekstudio/bibliotheque-sophitek/backup/")
                else:
                    self.act_lbl.config(text=f"✗ Erreur sauvegarde", fg=R)
                    messagebox.showerror("Erreur", msg)
            
            threading.Thread(target=do, daemon=True).start()

def demarrer_flask():
    """Démarre le serveur Flask"""
    port = CONFIG["PORT"]
    flask_app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)

# ═════════════════════════════════════════════════════════════════════
# POINT D'ENTRÉE
# ═════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    # Initialiser la base de données
    init_db()
    
    if ON_RENDER:
        # Mode serveur (Render)
        print(f"Démarrage du serveur Flask sur le port {CONFIG['PORT']}...")
        port = CONFIG["PORT"]
        flask_app.run(host="0.0.0.0", port=port)
    else:
        # Mode interface graphique (local)
        print("Démarrage de l'interface graphique...")
        root = tk.Tk()
        app = App(root)
        root.mainloop()