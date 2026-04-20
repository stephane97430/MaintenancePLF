import plotly.express as px
import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime, timedelta
import io, json, base64
import streamlit_authenticator as stauth
from PIL import Image
from streamlit_mic_recorder import speech_to_text

# --- 1. CONFIGURATION ---
st.set_page_config(page_title="Maintenance CILAM PLF", layout="wide", page_icon="🛠️")

# --- 2. DB & MIGRATIONS ---
conn = sqlite3.connect('maintenance_plf.db', check_same_thread=False)
c = conn.cursor()

tables = [
    "CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, name TEXT, password TEXT, role TEXT DEFAULT 'utilisateur')",
    "CREATE TABLE IF NOT EXISTS ateliers (id INTEGER PRIMARY KEY, nom TEXT UNIQUE)",
    "CREATE TABLE IF NOT EXISTS lignes (id INTEGER PRIMARY KEY, nom TEXT, atelier_id INTEGER, FOREIGN KEY(atelier_id) REFERENCES ateliers(id))",
    "CREATE TABLE IF NOT EXISTS machines (id INTEGER PRIMARY KEY, nom TEXT, ligne_id INTEGER, FOREIGN KEY(ligne_id) REFERENCES lignes(id))",
    "CREATE TABLE IF NOT EXISTS interventions (id INTEGER PRIMARY KEY, date TEXT, type TEXT, duree REAL, atelier TEXT, ligne TEXT, machine TEXT, techniciens TEXT, statut TEXT, probleme TEXT, solution TEXT, remarque TEXT, auteur TEXT, photo BLOB, photos_json TEXT)",
    "CREATE TABLE IF NOT EXISTS dat (id INTEGER PRIMARY KEY, date_creation TEXT, demandeur TEXT, atelier TEXT, ligne TEXT, machine TEXT, urgence TEXT, action TEXT, tech_suivi TEXT, commentaire TEXT, echeance TEXT, statut TEXT, auteur TEXT)",
    "CREATE TABLE IF NOT EXISTS config (type TEXT, nom TEXT)",
    "CREATE TABLE IF NOT EXISTS preventif_plan (id INTEGER PRIMARY KEY, atelier TEXT, ligne TEXT, machine TEXT, tache TEXT, frequence_jours INTEGER, derniere_date TEXT, prochaine_date TEXT, pieces_necessaires TEXT, temps_estime REAL DEFAULT 0, technicien_prev TEXT, procedure TEXT)"
]
for table in tables: c.execute(table)

migrations = [
    "ALTER TABLE users ADD COLUMN role TEXT DEFAULT 'utilisateur'",
    "ALTER TABLE interventions ADD COLUMN photos_json TEXT",
    "ALTER TABLE preventif_plan ADD COLUMN procedure TEXT",
    "ALTER TABLE dat ADD COLUMN atelier TEXT"
]
for m in migrations:
    try: c.execute(m)
    except sqlite3.OperationalError: pass
conn.commit()

# --- 3. FONCTIONS ---
def get_ateliers(): return [r[0] for r in c.execute("SELECT nom FROM ateliers ORDER BY nom").fetchall()]
def get_lignes(at): return [r[0] for r in c.execute("SELECT l.nom FROM lignes l JOIN ateliers a ON l.atelier_id=a.id WHERE a.nom=?", (at,)).fetchall()]
def get_machines(at, li): return [r[0] for r in c.execute("SELECT m.nom FROM machines m JOIN lignes l ON m.ligne_id=l.id JOIN ateliers a ON l.atelier_id=a.id WHERE a.nom=? AND l.nom=?", (at, li)).fetchall()]
def get_techniciens(): return [r[0] for r in c.execute("SELECT nom FROM config WHERE type='Technicien'").fetchall()]

def compress_image(image_file, qualite="Basse"):
    q = {"Basse": 25, "Moyenne": 55, "Haute": 85}.get(qualite, 25)
    img = Image.open(image_file).convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=q, optimize=True)
    return buf.getvalue()

def selecteur_cascade(pfx, inclure_toutes=True):
    ats = get_ateliers()
    opts_a = (["Tous"] + ats) if inclure_toutes else ats
    at = st.selectbox("Atelier", opts_a, key=f"{pfx}_at")
    if at in (None, "Tous"): return at, "Toutes", "Toutes"
    lis = (["Toutes"] + get_lignes(at)) if inclure_toutes else get_lignes(at)
    li = st.selectbox("Ligne", lis, key=f"{pfx}_li")
    if li in (None, "Toutes"): return at, li, "Toutes"
    mas = (["Toutes"] + get_machines(at, li)) if inclure_toutes else get_machines(at, li)
    ma = st.selectbox("Machine", mas, key=f"{pfx}_ma")
    return at, li, ma

# --- 4. AUTHENTIFICATION ---
creds = {"usernames": {r[0]: {"name": r[1], "password": r[2]} for r in c.execute("SELECT * FROM users").fetchall()}}
if not creds["usernames"]: c.execute("INSERT INTO users VALUES ('admin','Admin','admin123','admin')"); conn.commit()
auth = stauth.Authenticate(creds, "maint_cookie", "key_2026", 30)

if st.session_state.get("authentication_status") in (None, False):
    auth.login(location='main')
elif st.session_state["authentication_status"]:
    user_id, user_name = st.session_state["username"], st.session_state["name"]
    role = c.execute("SELECT role FROM users WHERE username=?", (user_id,)).fetchone()[0]
    is_admin = (role == "admin")

    # --- SIDEBAR & ALERTES ---
    with st.sidebar:
        st.title(f"👤 {user_name}")
        auth.logout('Déconnexion', 'sidebar')
        st.divider()
        # Calcul Alertes
        now = pd.Timestamp.now()
        df_p = pd.read_sql("SELECT prochaine_date FROM preventif_plan", conn)
        ret_p = len(df_p[pd.to_datetime(df_p['prochaine_date']) < now]) if not df_p.empty else 0
        if ret_p > 0: st.error(f"⚠️ {ret_p} Préventifs en retard")
        
        df_d = pd.read_sql("SELECT date_creation, statut FROM dat WHERE statut != 'Terminé'", conn)
        if not df_d.empty:
            ret_d = len(df_d[pd.to_datetime(df_d['date_creation']) < (now - pd.Timedelta(days=2))])
            if ret_d > 0: st.warning(f"🕒 {ret_d} DAT > 48h")
        
        menu = st.radio("Navigation", ["🛠️ Saisie", "📅 Préventif", "📂 Historique", "📝 DAT", "📈 Statistiques", "⚙️ Config"])

    # --- A. SAISIE INTERVENTION ---
    if menu == "🛠️ Saisie":
        st.header("🛠️ Saisie Intervention")
        if "photos_int" not in st.session_state: st.session_state.photos_int = []
        c1, c2 = st.columns(2)
        with c1:
            dt_i = st.date_input("Date", datetime.now()); typ_i = st.selectbox("Type", ["CURATIF","PREVENTIF","AMELIORATION"])
            at, li, ma = selecteur_cascade("s_i", False)
            q_p = st.radio("Qualité Photo", ["Basse","Moyenne","Haute"], horizontal=True)
            cam = st.camera_input("Photo")
            if cam: 
                st.session_state.photos_int.append(compress_image(cam, q_p))
                st.rerun()
        with c2:
            st.write("🎤 **Description Problème**")
            v_prob = speech_to_text(language='fr', start_prompt="Parler", key='v_p')
            prob = st.text_area("Problème", value=v_prob if v_prob else "")
            sol = st.text_area("Solution")
            if st.button("💾 Enregistrer"):
                p_json = json.dumps([base64.b64encode(b).decode() for b in st.session_state.photos_int])
                c.execute("INSERT INTO interventions (date, type, atelier, ligne, machine, probleme, solution, auteur, photos_json) VALUES (?,?,?,?,?,?,?,?,?)",
                          (str(dt_i), typ_i, at, li, ma, prob, sol, user_id, p_json))
                conn.commit(); st.session_state.photos_int = []; st.success("Enregistré !")

    # --- B. PRÉVENTIF ---
    elif menu == "📅 Préventif":
        df_prev = pd.read_sql("SELECT * FROM preventif_plan", conn)
        t1, t2 = st.tabs(["🗓️ Planning", "⚙️ Config"])
        with t1:
            if not df_prev.empty:
                sel_t = st.selectbox("Tâche à réaliser", df_prev['tache'].tolist())
                r_s = df_prev[df_prev['tache'] == sel_t].iloc[0]
                if r_s['procedure']: st.info(f"📖 **Procédure :** {r_s['procedure']}")
                if st.button("✅ Valider Réalisation"):
                    nxt = (datetime.now() + timedelta(days=int(r_s['frequence_jours']))).date()
                    c.execute("UPDATE preventif_plan SET derniere_date=?, prochaine_date=? WHERE tache=?", (str(datetime.now().date()), str(nxt), sel_t))
                    conn.commit(); st.rerun()
        with t2:
            if is_admin:
                at, li, ma = selecteur_cascade("p_p", False)
                t_p = st.text_input("Nom de la tâche")
                proc_p = st.text_area("Procédure")
                if st.button("Ajouter"):
                    c.execute("INSERT INTO preventif_plan (atelier, ligne, machine, tache, frequence_jours, prochaine_date, procedure) VALUES (?,?,?,?,?,?,?)",
                              (at, li, ma, t_p, 30, str((datetime.now()+timedelta(days=30)).date()), proc_p))
                    conn.commit(); st.rerun()

    # --- C. HISTORIQUE ---
    elif menu == "📂 Historique":
        if is_admin:
            with st.expander("📥 Import Excel"):
                up = st.file_uploader("Fichier", type="xlsx")
                if up and st.button("Importer"):
                    pd.read_excel(up).to_sql("interventions", conn, if_exists="append", index=False)
                    st.success("Importé !")
        st.dataframe(pd.read_sql("SELECT * FROM interventions ORDER BY id DESC", conn))

    # --- D. DAT ---
    elif menu == "📝 DAT":
        st.header("📝 Demandes d'Actions Techniques")
        t1, t2 = st.tabs(["➕ Créer", "📋 Liste"])
        with t1:
            at, li, ma = selecteur_cascade("dat_c", False)
            st.write("🎤 **Action demandée**")
            v_dat = speech_to_text(language='fr', start_prompt="Dicter l'action", key='v_dat')
            act = st.text_area("Action", value=v_dat if v_dat else "")
            if st.button("Envoyer DAT"):
                c.execute("INSERT INTO dat (date_creation, atelier, ligne, machine, action, statut, auteur) VALUES (?,?,?,?,?,?,?)",
                          (str(datetime.now().date()), at, li, ma, act, "Ouvert", user_id))
                conn.commit(); st.success("DAT créée !")
        with t2:
            df_dat = pd.read_sql("SELECT * FROM dat", conn)
            st.data_editor(df_dat, use_container_width=True)

    # --- E. STATISTIQUES ---
    elif menu == "📈 Statistiques":
        df_d = pd.read_sql("SELECT statut FROM dat", conn)
        if not df_d.empty:
            total = len(df_d)
            clos = len(df_d[df_d['statut'] == 'Terminé'])
            tx = (clos/total)*100
            c1, c2 = st.columns(2)
            c1.metric("Total DAT", total)
            c2.metric("Taux de clôture", f"{tx:.1f}%")
        st.plotly_chart(px.pie(pd.read_sql("SELECT type FROM interventions", conn), names='type', title="Interventions"))

    # --- F. CONFIGURATION (ADMIN) ---
    elif menu == "⚙️ Configuration":
        if is_admin:
            st.header("⚙️ Paramètres Système")
            tab_struct, tab_users = st.tabs(["🏗️ Structure Usine", "👤 Gestion des Utilisateurs"])
            
            with tab_struct:
                col_c1, col_c2 = st.columns(2)
                with col_c1:
                    st.subheader("➕ Ajouter un élément")
                    t_cfg = st.selectbox("Type", ["Technicien", "Ligne", "Machine"])
                    if t_cfg == "Machine":
                        lp = st.selectbox("Ligne parente", get_config("Ligne"))
                        nom_cfg = st.text_input("Désignation machine")
                        type_store = f"Machine_{lp}"
                    else:
                        nom_cfg = st.text_input(f"Désignation {t_cfg}")
                        type_store = t_cfg
                    if st.button("Ajouter à la config"):
                        if nom_cfg:
                            c.execute("INSERT INTO config (type, nom) VALUES (?,?)", (type_store, nom_cfg))
                            conn.commit()
                            st.rerun()
                with col_c2:
                    st.subheader("🗑️ Supprimer un élément")
                    all_cfg = pd.read_sql("SELECT * FROM config", conn)
                    sel_del = st.selectbox("Élément à supprimer", all_cfg['nom'].tolist() if not all_cfg.empty else [])
                    if st.button("❌ Supprimer définitivement"):
                        c.execute("DELETE FROM config WHERE nom=?", (sel_del,))
                        conn.commit()
                        st.rerun()

            with tab_users:
                df_u = pd.read_sql("SELECT username, name FROM users", conn)
                col_u1, col_u2 = st.columns(2)
                with col_u1:
                    st.subheader("➕ Nouvel utilisateur")
                    nu, nn, np = st.text_input("Login"), st.text_input("Nom Complet"), st.text_input("MDP", type="password")
                    if st.button("Créer le compte"):
                        if nu and np:
                            try:
                                c.execute("INSERT INTO users VALUES (?, ?, ?)", (nu, nn, np))
                                conn.commit()
                                st.success("Utilisateur ajouté !")
                                st.rerun()
                            except: st.error("Identifiant déjà utilisé.")
                with col_u2:
                    st.subheader("🔑 Sécurité")
                    target = st.selectbox("Compte à modifier", df_u['username'].tolist())
                    mod_pw = st.text_input("Nouveau MDP", type="password", key="mod_pw")
                    if st.button("Changer le MDP") and mod_pw:
                        c.execute("UPDATE users SET password=? WHERE username=?", (mod_pw, target))
                        conn.commit()
                        st.success("Mot de passe modifié.")
                    if target != "admin" and st.button("❌ Supprimer l'utilisateur"):
                        c.execute("DELETE FROM users WHERE username=?", (target,))
                        conn.commit()
                        st.rerun()
