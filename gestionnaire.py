"""
╔══════════════════════════════════════════════════════════════╗
║       SOPHITEK STUDIO — GESTIONNAIRE v3 (PyQt6)             ║
║       Auteur : Japhet Arcade Sophiano ASSOGBA                ║
╚══════════════════════════════════════════════════════════════╝
"""

import os, sys, sqlite3, hashlib, json, shutil, threading
import logging, base64
from datetime import datetime
from pathlib import Path

import requests as req
from flask import Flask, request, jsonify, redirect, abort

# ── Détection environnement
ON_RENDER = os.environ.get("RENDER","").lower() == "true"

# ── Chargement .env
def _load_env():
    env = Path(__file__).parent / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k,_,v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())
_load_env()

# ════════════════════════════════════════
# CONFIGURATION
# ════════════════════════════════════════
CONFIG = {
    "GITHUB_TOKEN": os.environ.get("GITHUB_TOKEN",""),
    "GITHUB_REPO":  "sophitekstudio/bibliotheque-sophitek",
    "RENDER_URL":   "https://bibliotheque-sophitek.onrender.com",
    "FEDAPAY_KEY":  os.environ.get("FEDAPAY_KEY",""),
    "WHATSAPP":     "2290143678355",
    "PRIX_DEFAUT":  1000,
    "ADMIN_KEY":    os.environ.get("ADMIN_KEY","sophitek2026"),
    "PORT":         int(os.environ.get("PORT",5000)),
    "SITE_URL":     "https://sophitekstudio.github.io/bibliotheque-sophitek/",
}

# ════════════════════════════════════════
# CHEMINS
# ════════════════════════════════════════
BASE_DIR   = Path(__file__).parent
SITE_DIR   = BASE_DIR / "site"
COVERS_DIR = SITE_DIR / "covers"
DB_PATH    = BASE_DIR / "data" / "sophitek.db"
JSON_PATH  = SITE_DIR / "data.json"
HTML_PATH  = SITE_DIR / "index.html"
LOGO_PATH  = SITE_DIR / "logo.png"

COVERS_DIR.mkdir(parents=True, exist_ok=True)
(BASE_DIR / "data").mkdir(parents=True, exist_ok=True)

logging.basicConfig(level=logging.INFO,
    format="%(asctime)s — %(levelname)s — %(message)s",
    handlers=[logging.FileHandler(BASE_DIR/"sophitek.log"),
              logging.StreamHandler(sys.stdout)])

# ════════════════════════════════════════
# BASE DE DONNÉES
# ════════════════════════════════════════
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS contenus (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        type TEXT DEFAULT 'livre',
        titre TEXT NOT NULL,
        auteur TEXT DEFAULT 'Japhet Arcade Sophiano ASSOGBA',
        genre TEXT DEFAULT '',
        description TEXT DEFAULT '',
        extrait TEXT DEFAULT '',
        prix INTEGER DEFAULT 1000,
        gratuit INTEGER DEFAULT 0,
        couverture TEXT DEFAULT '',
        lien_drive TEXT DEFAULT '',
        lien_media TEXT DEFAULT '',
        actif INTEGER DEFAULT 1,
        date_ajout TEXT DEFAULT ''
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS commentaires (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        contenu_id INTEGER NOT NULL,
        nom TEXT NOT NULL,
        texte TEXT NOT NULL,
        date_com TEXT DEFAULT '',
        approuve INTEGER DEFAULT 1
    )""")
    conn.commit(); conn.close()

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def get_contenus(type_f=None):
    conn = get_db()
    if type_f:
        rows = conn.execute("SELECT * FROM contenus WHERE actif=1 AND type=? ORDER BY id DESC",(type_f,)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM contenus WHERE actif=1 ORDER BY id DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_commentaires(cid):
    conn = get_db()
    rows = conn.execute("SELECT * FROM commentaires WHERE contenu_id=? AND approuve=1 ORDER BY id DESC",(cid,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def add_contenu(d):
    conn = get_db()
    c = conn.execute("""INSERT INTO contenus
        (type,titre,auteur,genre,description,extrait,prix,gratuit,couverture,lien_drive,lien_media,date_ajout)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
        (d["type"],d["titre"],d["auteur"],d["genre"],d["description"],d["extrait"],
         d["prix"],d["gratuit"],d["couverture"],d["lien_drive"],d["lien_media"],
         datetime.now().strftime("%Y-%m-%d")))
    lid = c.lastrowid; conn.commit(); conn.close()
    return lid

def update_contenu(lid, d):
    conn = get_db()
    conn.execute("""UPDATE contenus SET type=?,titre=?,auteur=?,genre=?,description=?,
        extrait=?,prix=?,gratuit=?,couverture=?,lien_drive=?,lien_media=? WHERE id=?""",
        (d["type"],d["titre"],d["auteur"],d["genre"],d["description"],d["extrait"],
         d["prix"],d["gratuit"],d["couverture"],d["lien_drive"],d["lien_media"],lid))
    conn.commit(); conn.close()

def delete_contenu(lid):
    conn = get_db()
    conn.execute("UPDATE contenus SET actif=0 WHERE id=?",(lid,))
    conn.commit(); conn.close()

def add_commentaire(cid, nom, texte):
    conn = get_db()
    conn.execute("INSERT INTO commentaires (contenu_id,nom,texte,date_com) VALUES(?,?,?,?)",
        (cid,nom,texte,datetime.now().strftime("%Y-%m-%d %H:%M")))
    conn.commit(); conn.close()

def delete_commentaire(cid):
    conn = get_db()
    conn.execute("DELETE FROM commentaires WHERE id=?",(cid,))
    conn.commit(); conn.close()

def get_stats():
    conn = get_db()
    t = conn.execute("SELECT COUNT(*) FROM contenus WHERE actif=1").fetchone()[0]
    g = conn.execute("SELECT COUNT(*) FROM contenus WHERE actif=1 AND gratuit=1").fetchone()[0]
    c = conn.execute("SELECT COUNT(*) FROM commentaires WHERE approuve=1").fetchone()[0]
    conn.close()
    return {"total":t,"gratuit":g,"payant":t-g,"commentaires":c}

# ════════════════════════════════════════
# JSON EXPORT
# ════════════════════════════════════════
def exporter_json():
    contenus = get_contenus()
    data = []
    for b in contenus:
        b["gratuit"] = bool(b["gratuit"])
        b["commentaires"] = get_commentaires(b["id"])
        if LOGO_PATH.exists():
            b["logo"] = "logo.png"
        data.append(b)
    JSON_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data

# ════════════════════════════════════════
# GITHUB
# ════════════════════════════════════════
def github_push(contenu_bytes, chemin, message):
    token = CONFIG["GITHUB_TOKEN"]
    repo  = CONFIG["GITHUB_REPO"]
    url   = f"https://api.github.com/repos/{repo}/contents/{chemin}"
    hdrs  = {"Authorization":f"token {token}","Accept":"application/vnd.github+json"}
    b64   = base64.b64encode(contenu_bytes).decode()
    sha   = None
    r = req.get(url, headers=hdrs, timeout=15)
    if r.status_code == 200:
        sha = r.json().get("sha")
    payload = {"message":message,"content":b64}
    if sha: payload["sha"] = sha
    r = req.put(url, json=payload, headers=hdrs, timeout=20)
    if r.status_code in (200,201):
        return True, f"✓ {chemin}"
    return False, f"✗ {chemin} : {r.json().get('message','Erreur')}"

def github_get(chemin):
    token = CONFIG["GITHUB_TOKEN"]
    repo  = CONFIG["GITHUB_REPO"]
    url   = f"https://api.github.com/repos/{repo}/contents/{chemin}"
    hdrs  = {"Authorization":f"token {token}","Accept":"application/vnd.github+json"}
    r = req.get(url, headers=hdrs, timeout=15)
    if r.status_code == 200:
        return base64.b64decode(r.json().get("content",""))
    return None

def publier(callback):
    msgs, errors = [], []
    # HTML
    ok,msg = github_push(HTML_PATH.read_bytes(),"index.html",
        f"Mise à jour — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    (msgs if ok else errors).append(msg)
    # JSON
    data = exporter_json()
    ok,msg = github_push(JSON_PATH.read_bytes(),"data.json",
        f"Données — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    (msgs if ok else errors).append(msg)
    # Logo
    if LOGO_PATH.exists():
        ok,msg = github_push(LOGO_PATH.read_bytes(),"logo.png","Logo Sophitek Studio")
        (msgs if ok else errors).append(msg)
    # Couvertures
    for cover in COVERS_DIR.iterdir():
        if cover.is_file() and cover.suffix.lower() in (".jpg",".jpeg",".png",".webp"):
            ok,msg = github_push(cover.read_bytes(),f"covers/{cover.name}",f"Cover:{cover.name}")
            (msgs if ok else errors).append(msg)
    callback(msgs, errors)

def synchroniser(callback):
    try:
        data_bytes = github_get("data.json")
        if not data_bytes:
            callback(False,"Fichier data.json introuvable"); return
        data = json.loads(data_bytes.decode("utf-8"))
        conn = get_db()
        for b in data:
            exists = conn.execute("SELECT id FROM contenus WHERE id=?",(b["id"],)).fetchone()
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
        conn.commit(); conn.close()
        callback(True,f"✓ {len(data)} contenus synchronisés")
    except Exception as e:
        callback(False,str(e))

def sauvegarder(callback):
    try:
        script = Path(__file__).read_bytes()
        ok,msg = github_push(script,"backup/gestionnaire.py",
            f"Backup — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        callback(ok,msg)
    except Exception as e:
        callback(False,str(e))

# ════════════════════════════════════════
# FLASK
# ════════════════════════════════════════
flask_app = Flask(__name__)

@flask_app.route("/")
def home():
    return jsonify({"status":"Sophitek Studio API","version":"3.0"})

@flask_app.route("/contenus")
def api_contenus():
    data = get_contenus(request.args.get("type"))
    return jsonify([{**b,"gratuit":bool(b["gratuit"])} for b in data])

@flask_app.route("/commentaire",methods=["POST"])
def api_com():
    d = request.get_json(silent=True) or {}
    cid = d.get("contenu_id")
    nom = str(d.get("nom","")).strip()[:60]
    txt = str(d.get("texte","")).strip()[:500]
    if not cid or not nom or not txt:
        return jsonify({"erreur":"Données manquantes"}),400
    add_commentaire(cid,nom,txt)
    return jsonify({"success":True})

@flask_app.route("/admin/stats")
def api_stats():
    if request.args.get("key") != CONFIG["ADMIN_KEY"]:
        abort(403)
    return jsonify(get_stats())

def demarrer_flask():
    flask_app.run(host="0.0.0.0",port=CONFIG["PORT"],debug=False,use_reloader=False)

# ════════════════════════════════════════
# PYQT6 — INTERFACE
# ════════════════════════════════════════
if not ON_RENDER:
    from PyQt6.QtWidgets import (
        QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
        QLabel, QPushButton, QListWidget, QListWidgetItem, QLineEdit,
        QTextEdit, QCheckBox, QComboBox, QFileDialog, QMessageBox,
        QFrame, QScrollArea, QSplitter, QTabWidget, QGridLayout,
        QGroupBox, QDialog, QDialogButtonBox
    )
    from PyQt6.QtCore import Qt, QThread, pyqtSignal, QSize
    from PyQt6.QtGui import QFont, QIcon, QPixmap, QColor, QPalette

    # ── COULEURS
    V  = "#6c3fc5"   # violet
    VC = "#8b5cf6"   # violet clair
    VP = "#ede9fe"   # violet pale
    OR = "#c9951a"   # or
    OC = "#f5c842"   # or clair
    OP = "#fef9e7"   # or pale
    BL = "#ffffff"   # blanc
    GC = "#f7f5ff"   # gris clair
    TX = "#1a1035"   # texte
    TD = "#6b7280"   # texte doux

    STYLE = f"""
    QMainWindow, QWidget {{ background: {GC}; color: {TX}; font-family: 'Segoe UI'; }}
    QLabel {{ color: {TX}; }}
    QLineEdit, QTextEdit, QComboBox {{
        background: {BL}; border: 1.5px solid {VP}; border-radius: 8px;
        padding: 8px 12px; color: {TX}; font-size: 13px;
    }}
    QLineEdit:focus, QTextEdit:focus {{ border-color: {VC}; }}
    QComboBox::drop-down {{ border: none; width: 24px; }}
    QListWidget {{
        background: {BL}; border: 1.5px solid {VP}; border-radius: 10px;
        padding: 4px; color: {TX}; font-size: 13px;
    }}
    QListWidget::item {{ padding: 10px 12px; border-radius: 8px; margin: 2px; }}
    QListWidget::item:selected {{ background: {VP}; color: {V}; font-weight: bold; }}
    QListWidget::item:hover {{ background: {GC}; }}
    QGroupBox {{
        background: {BL}; border: 1.5px solid {VP}; border-radius: 12px;
        margin-top: 12px; padding: 16px; font-weight: bold; color: {V};
    }}
    QGroupBox::title {{ subcontrol-position: top left; padding: 0 8px; left: 12px; }}
    QCheckBox {{ color: {TX}; font-size: 13px; }}
    QCheckBox::indicator:checked {{ background: {V}; border-radius: 4px; }}
    QScrollBar:vertical {{ background: {GC}; width: 8px; border-radius: 4px; }}
    QScrollBar::handle:vertical {{ background: {VP}; border-radius: 4px; }}
    QTabWidget::pane {{ border: 1.5px solid {VP}; border-radius: 10px; background: {BL}; }}
    QTabBar::tab {{
        background: {GC}; padding: 8px 20px; border-radius: 8px 8px 0 0;
        color: {TD}; font-size: 13px; margin-right: 2px;
    }}
    QTabBar::tab:selected {{ background: {BL}; color: {V}; font-weight: bold; }}
    """

    def btn(text, color=V, text_color=BL, sz=13):
        b = QPushButton(text)
        b.setStyleSheet(f"""
            QPushButton {{
                background: {color}; color: {text_color};
                border: none; border-radius: 8px; padding: 10px 16px;
                font-size: {sz}px; font-weight: 600; cursor: pointer;
            }}
            QPushButton:hover {{ opacity: 0.9; }}
            QPushButton:pressed {{ opacity: 0.8; }}
        """)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        return b

    def label(text, size=13, bold=False, color=TX):
        l = QLabel(text)
        f = QFont("Segoe UI", size)
        f.setBold(bold)
        l.setFont(f)
        l.setStyleSheet(f"color:{color};")
        return l

    def separateur():
        f = QFrame()
        f.setFrameShape(QFrame.Shape.HLine)
        f.setStyleSheet(f"color:{VP};")
        return f

    # ── THREAD PUBLICATION
    class PublierThread(QThread):
        termine = pyqtSignal(list, list)
        def run(self):
            publier(lambda m,e: self.termine.emit(m,e))

    class SyncThread(QThread):
        termine = pyqtSignal(bool, str)
        def run(self):
            synchroniser(lambda ok,msg: self.termine.emit(ok,msg))

    class SaveThread(QThread):
        termine = pyqtSignal(bool, str)
        def run(self):
            sauvegarder(lambda ok,msg: self.termine.emit(ok,msg))

    # ── FENÊTRE PRINCIPALE
    class SophitekApp(QMainWindow):
        def __init__(self):
            super().__init__()
            self.setWindowTitle("Sophitek Studio — Gestionnaire v3")
            self.setMinimumSize(1100, 700)
            self.setStyleSheet(STYLE)
            self.sel_id = None
            self.cover_path = ""
            init_db()
            self._build()
            self._charger()
            threading.Thread(target=demarrer_flask, daemon=True).start()

        def _build(self):
            central = QWidget()
            self.setCentralWidget(central)
            main = QVBoxLayout(central)
            main.setContentsMargins(0,0,0,0)
            main.setSpacing(0)

            # ── HEADER
            header = QWidget()
            header.setStyleSheet(f"background:{V}; padding: 0;")
            header.setFixedHeight(64)
            hl = QHBoxLayout(header)
            hl.setContentsMargins(20,0,20,0)

            logo_lbl = label("✦ Sophitek Studio", 16, True, BL)
            slogan_lbl = label("Gestionnaire v3", 11, False, "rgba(255,255,255,0.7)")
            left_h = QVBoxLayout()
            left_h.setSpacing(2)
            left_h.addWidget(logo_lbl)
            left_h.addWidget(slogan_lbl)
            hl.addLayout(left_h)
            hl.addStretch()

            self.stat_lbl = label("", 12, False, "rgba(255,255,255,0.85)")
            hl.addWidget(self.stat_lbl)
            main.addWidget(header)

            # ── CORPS
            corps = QSplitter(Qt.Orientation.Horizontal)
            corps.setStyleSheet("QSplitter::handle{background:#ede9fe;width:2px;}")

            # Panneau gauche
            left = QWidget()
            left.setStyleSheet(f"background:{BL};")
            left.setFixedWidth(280)
            lv = QVBoxLayout(left)
            lv.setContentsMargins(12,16,12,12)
            lv.setSpacing(8)

            lv.addWidget(label("📦  Mes contenus", 13, True, V))
            lv.addWidget(separateur())

            # Filtre type
            self.filtre_type = QComboBox()
            self.filtre_type.addItems(["Tous","📚 Livres","💻 Applications","🎵 Audios","🎬 Vidéos","📦 Autres"])
            self.filtre_type.currentIndexChanged.connect(self._charger)
            lv.addWidget(self.filtre_type)

            self.liste = QListWidget()
            self.liste.itemClicked.connect(self._on_select)
            lv.addWidget(self.liste)

            self.btn_nouveau   = btn("＋  Nouveau",    OR, BL)
            self.btn_supprimer = btn("✕  Supprimer",   "#ef4444", BL)
            self.btn_coms      = btn("🗨  Commentaires", V, BL)
            self.btn_nouveau.clicked.connect(self._nouveau)
            self.btn_supprimer.clicked.connect(self._supprimer)
            self.btn_coms.clicked.connect(self._voir_coms)
            lv.addWidget(self.btn_nouveau)
            lv.addWidget(self.btn_supprimer)
            lv.addWidget(self.btn_coms)

            # Panneau droit
            right = QWidget()
            rv = QVBoxLayout(right)
            rv.setContentsMargins(16,16,16,16)
            rv.setSpacing(12)

            tabs = QTabWidget()

            # Tab 1 — Formulaire
            form_tab = QWidget()
            fv = QVBoxLayout(form_tab)
            fv.setSpacing(10)

            # Type
            type_row = QHBoxLayout()
            type_row.addWidget(label("Type:", 12, True, V))
            self.type_combo = QComboBox()
            self.type_combo.addItems(["livre","app","audio","video","autre"])
            type_row.addWidget(self.type_combo)
            type_row.addStretch()
            self.cb_gratuit = QCheckBox("Accès gratuit")
            self.cb_gratuit.setStyleSheet(f"color:{TX};font-size:13px;")
            type_row.addWidget(self.cb_gratuit)
            fv.addLayout(type_row)

            # Champs
            self.f = {}
            champs = [
                ("titre","Titre *"),("auteur","Auteur"),
                ("genre","Genre / Catégorie"),("prix","Prix (FCFA)"),
                ("lien_drive","Lien Google Drive"),("lien_media","Lien audio/vidéo"),
            ]
            grid = QGridLayout()
            grid.setSpacing(8)
            for i,(key,lbl) in enumerate(champs):
                grid.addWidget(label(lbl,11,False,TD), i//2*2, (i%2)*2)
                w = QLineEdit()
                w.setPlaceholderText(lbl)
                grid.addWidget(w, i//2*2+1, (i%2)*2)
                self.f[key] = w
            fv.addLayout(grid)

            fv.addWidget(label("Description",11,False,TD))
            self.f["description"] = QTextEdit()
            self.f["description"].setFixedHeight(70)
            fv.addWidget(self.f["description"])

            fv.addWidget(label("Extrait lisible",11,False,TD))
            self.f["extrait"] = QTextEdit()
            self.f["extrait"].setFixedHeight(70)
            fv.addWidget(self.f["extrait"])

            # Couverture
            cov_row = QHBoxLayout()
            self.cover_lbl = label("Aucune couverture", 11, False, TD)
            btn_cov = btn("🖼  Couverture", VP, V, 12)
            btn_cov.clicked.connect(self._choisir_cover)
            cov_row.addWidget(btn_cov)
            cov_row.addWidget(self.cover_lbl)
            cov_row.addStretch()
            fv.addLayout(cov_row)

            # Enregistrer
            sav_row = QHBoxLayout()
            self.btn_save   = btn("💾  Enregistrer", "#16a34a", BL)
            self.btn_cancel = btn("✕  Annuler", GC, TD, 12)
            self.btn_save.clicked.connect(self._enregistrer)
            self.btn_cancel.clicked.connect(self._vider)
            sav_row.addWidget(self.btn_save)
            sav_row.addWidget(self.btn_cancel)
            sav_row.addStretch()
            fv.addLayout(sav_row)
            fv.addStretch()

            tabs.addTab(form_tab, "✏️  Contenu")

            # Tab 2 — Logo & Paramètres
            logo_tab = QWidget()
            lv2 = QVBoxLayout(logo_tab)
            lv2.setContentsMargins(20,20,20,20)
            lv2.setSpacing(16)

            lv2.addWidget(label("Logo de la boutique", 15, True, V))
            lv2.addWidget(label("Ce logo apparaîtra sur le site et dans la navbar.", 12, False, TD))
            lv2.addWidget(separateur())

            self.logo_preview = QLabel("Aucun logo sélectionné")
            self.logo_preview.setFixedHeight(100)
            self.logo_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.logo_preview.setStyleSheet(f"background:{VP};border-radius:12px;color:{TD};font-size:12px;")
            if LOGO_PATH.exists():
                px = QPixmap(str(LOGO_PATH)).scaled(100,100,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation)
                self.logo_preview.setPixmap(px)
            lv2.addWidget(self.logo_preview)

            btn_logo = btn("🖼  Choisir un logo", OR, BL)
            btn_logo.clicked.connect(self._choisir_logo)
            lv2.addWidget(btn_logo)
            lv2.addStretch()

            tabs.addTab(logo_tab, "🎨  Logo & Style")
            rv.addWidget(tabs, stretch=1)

            # ── BARRE D'ACTIONS
            act = QGroupBox("Actions")
            av = QVBoxLayout(act)
            av.setSpacing(8)

            row1 = QHBoxLayout()
            self.btn_pub  = btn("🌐  PUBLIER SUR GITHUB", V, BL, 13)
            self.btn_sync = btn("⟳  Synchroniser", VC, BL, 12)
            self.btn_save2= btn("💾  Sauvegarder", OR, BL, 12)
            self.btn_prev = btn("👁  Aperçu", GC, V, 12)
            self.btn_site = btn("🔗  Site en ligne", GC, V, 12)
            self.btn_pub.clicked.connect(self._publier)
            self.btn_sync.clicked.connect(self._synchroniser)
            self.btn_save2.clicked.connect(self._sauvegarder)
            self.btn_prev.clicked.connect(self._apercu)
            self.btn_site.clicked.connect(self._ouvrir_site)
            for b in [self.btn_pub,self.btn_sync,self.btn_save2,self.btn_prev,self.btn_site]:
                row1.addWidget(b)
            av.addLayout(row1)

            self.act_lbl = label("", 12, False, TD)
            av.addWidget(self.act_lbl)
            rv.addWidget(act)

            corps.addWidget(left)
            corps.addWidget(right)
            corps.setSizes([280, 820])
            main.addWidget(corps, stretch=1)

        # ── LISTE
        def _charger(self):
            self.liste.clear()
            idx = self.filtre_type.currentIndex()
            types = [None,"livre","app","audio","video","autre"]
            self.data = get_contenus(types[idx])
            ICONS = {"livre":"📚","app":"💻","audio":"🎵","video":"🎬","autre":"📦"}
            for b in self.data:
                ic  = ICONS.get(b["type"],"📦")
                tag = "🆓" if b["gratuit"] else f"{b['prix']:,} F"
                item = QListWidgetItem(f"  {ic}  {b['titre']}  [{tag}]")
                self.liste.addItem(item)
            s = get_stats()
            self.stat_lbl.setText(f"  {s['total']} contenus  ·  {s['gratuit']} gratuits  ·  {s['commentaires']} avis")

        def _on_select(self, item):
            idx = self.liste.row(item)
            if idx < 0 or idx >= len(self.data): return
            b = self.data[idx]
            self.sel_id = b["id"]
            self._vider_champs()
            self.type_combo.setCurrentText(b.get("type","livre"))
            for k in ["titre","auteur","genre","prix","lien_drive","lien_media"]:
                self.f[k].setText(str(b.get(k,"")))
            self.f["description"].setPlainText(b.get("description",""))
            self.f["extrait"].setPlainText(b.get("extrait",""))
            self.cb_gratuit.setChecked(bool(b.get("gratuit",0)))
            self.cover_path = b.get("couverture","")
            self.cover_lbl.setText(self.cover_path or "Aucune couverture")

        def _vider(self):
            self.sel_id = None
            self.liste.clearSelection()
            self._vider_champs()

        def _vider_champs(self):
            self.sel_id = None
            for k,w in self.f.items():
                if isinstance(w, QTextEdit): w.clear()
                else: w.clear()
            self.cb_gratuit.setChecked(False)
            self.cover_path = ""
            self.cover_lbl.setText("Aucune couverture")
            self.type_combo.setCurrentIndex(0)

        def _get_data(self):
            try: prix = int(self.f["prix"].text().strip() or "0")
            except: prix = 0
            return {
                "type":        self.type_combo.currentText(),
                "titre":       self.f["titre"].text().strip(),
                "auteur":      self.f["auteur"].text().strip() or "Japhet Arcade Sophiano ASSOGBA",
                "genre":       self.f["genre"].text().strip(),
                "description": self.f["description"].toPlainText().strip(),
                "extrait":     self.f["extrait"].toPlainText().strip(),
                "prix":        prix,
                "gratuit":     int(self.cb_gratuit.isChecked()),
                "couverture":  self.cover_path,
                "lien_drive":  self.f["lien_drive"].text().strip(),
                "lien_media":  self.f["lien_media"].text().strip(),
            }

        def _nouveau(self):
            self._vider()
            self.f["titre"].setFocus()

        def _enregistrer(self):
            d = self._get_data()
            if not d["titre"]:
                QMessageBox.warning(self,"Erreur","Le titre est obligatoire."); return
            if self.sel_id:
                update_contenu(self.sel_id, d)
                QMessageBox.information(self,"✓",f"Modifié : {d['titre']}")
            else:
                add_contenu(d)
                QMessageBox.information(self,"✓",f"Ajouté : {d['titre']}")
            self._vider(); self._charger()

        def _supprimer(self):
            sel = self.liste.currentRow()
            if sel < 0 or not self.sel_id:
                QMessageBox.information(self,"Info","Sélectionne un contenu."); return
            titre = self.data[sel]["titre"]
            rep = QMessageBox.question(self,"Confirmer",f"Supprimer « {titre} » ?")
            if rep == QMessageBox.StandardButton.Yes:
                delete_contenu(self.sel_id)
                self._vider(); self._charger()

        def _choisir_cover(self):
            path,_ = QFileDialog.getOpenFileName(self,"Choisir une couverture",
                "","Images (*.jpg *.jpeg *.png *.webp)")
            if path:
                nom  = Path(path).name
                dest = COVERS_DIR / nom
                shutil.copy2(path, dest)
                self.cover_path = f"covers/{nom}"
                self.cover_lbl.setText(self.cover_path)

        def _choisir_logo(self):
            path,_ = QFileDialog.getOpenFileName(self,"Choisir un logo",
                "","Images (*.jpg *.jpeg *.png *.webp)")
            if path:
                shutil.copy2(path, LOGO_PATH)
                px = QPixmap(str(LOGO_PATH)).scaled(100,100,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation)
                self.logo_preview.setPixmap(px)
                QMessageBox.information(self,"✓","Logo mis à jour ! Clique Publier pour l'envoyer sur le site.")

        def _voir_coms(self):
            if not self.sel_id:
                QMessageBox.information(self,"Info","Sélectionne un contenu d'abord."); return
            coms = get_commentaires(self.sel_id)
            dlg = QDialog(self)
            dlg.setWindowTitle("Commentaires")
            dlg.setMinimumSize(500,400)
            dlg.setStyleSheet(STYLE)
            v = QVBoxLayout(dlg)
            v.addWidget(label(f"Commentaires ({len(coms)})",14,True,V))
            lb = QListWidget()
            for c in coms:
                lb.addItem(f"  {c['nom']} ({c['date_com'][:10]}) : {c['texte'][:60]}")
            v.addWidget(lb)
            def sup():
                idx = lb.currentRow()
                if idx < 0: return
                rep = QMessageBox.question(dlg,"Confirmer","Supprimer ce commentaire ?")
                if rep == QMessageBox.StandardButton.Yes:
                    delete_commentaire(coms[idx]["id"])
                    lb.takeItem(idx)
            b_sup = btn("✕  Supprimer", "#ef4444", BL)
            b_sup.clicked.connect(sup)
            v.addWidget(b_sup)
            dlg.exec()

        def _apercu(self):
            exporter_json()
            import webbrowser
            webbrowser.open(str(HTML_PATH))

        def _ouvrir_site(self):
            import webbrowser
            webbrowser.open(CONFIG["SITE_URL"])

        def _publier(self):
            self.btn_pub.setEnabled(False)
            self.act_lbl.setStyleSheet(f"color:{OR};")
            self.act_lbl.setText("⏳  Publication en cours...")
            exporter_json()
            self.pub_thread = PublierThread()
            def on_done(msgs, errors):
                self.btn_pub.setEnabled(True)
                if errors and not msgs:
                    self.act_lbl.setStyleSheet("color:#ef4444;")
                    self.act_lbl.setText(f"✗  Échec : {errors[0]}")
                    QMessageBox.critical(self,"Erreur","\n".join(errors[:3]))
                else:
                    self.act_lbl.setStyleSheet(f"color:#16a34a;")
                    self.act_lbl.setText(f"✓  Publié ! {len(msgs)} fichier(s) mis à jour")
                    QMessageBox.information(self,"✓  Succès !",
                        f"Site mis à jour !\n\nVisible dans 1-2 min sur :\n{CONFIG['SITE_URL']}")
                self._charger()
            self.pub_thread.termine.connect(on_done)
            self.pub_thread.start()

        def _synchroniser(self):
            rep = QMessageBox.question(self,"Synchroniser",
                "Mettre l'app à jour depuis GitHub ?")
            if rep != QMessageBox.StandardButton.Yes: return
            self.act_lbl.setStyleSheet(f"color:{OR};")
            self.act_lbl.setText("⏳  Synchronisation...")
            self.sync_thread = SyncThread()
            def on_done(ok, msg):
                self.act_lbl.setStyleSheet(f"color:{'#16a34a' if ok else '#ef4444'};")
                self.act_lbl.setText(msg)
                if ok:
                    QMessageBox.information(self,"✓",msg)
                    self._charger()
                else:
                    QMessageBox.critical(self,"Erreur",msg)
            self.sync_thread.termine.connect(on_done)
            self.sync_thread.start()

        def _sauvegarder(self):
            self.act_lbl.setStyleSheet(f"color:{OR};")
            self.act_lbl.setText("⏳  Sauvegarde...")
            self.save_thread = SaveThread()
            def on_done(ok, msg):
                self.act_lbl.setStyleSheet(f"color:{'#16a34a' if ok else '#ef4444'};")
                self.act_lbl.setText(msg)
                if ok:
                    QMessageBox.information(self,"✓  Sauvegardé",
                        "Fichier Python sauvegardé sur GitHub\ndans le dossier backup/")
                else:
                    QMessageBox.critical(self,"Erreur",msg)
            self.save_thread.termine.connect(on_done)
            self.save_thread.start()

# ════════════════════════════════════════
# POINT D'ENTRÉE
# ════════════════════════════════════════
if __name__ == "__main__":
    init_db()
    if ON_RENDER:
        logging.info("Mode serveur Render")
        demarrer_flask()
    else:
        logging.info("Mode gestionnaire PC")
        app = QApplication(sys.argv)
        app.setStyle("Fusion")
        window = SophitekApp()
        window.show()
        sys.exit(app.exec())
