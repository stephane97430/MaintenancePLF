import plotly.express as px
import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime, timedelta
import io
import streamlit_authenticator as stauth
from PIL import Image

# --- 1. CONFIGURATION DE LA PAGE ---
st.set_page_config(page_title="Maintenance CILAM PLF", layout="wide", page_icon="🛠️")

# --- 2. CONNEXION BASE DE DONNÉES ---
conn = sqlite3.connect('maintenance_plf.db', check_same_thread=False)
c = conn.cursor()

# Initialisation des tables avec support PHOTO (BLOB)
c.execute('''CREATE TABLE IF NOT EXISTS users 
             (username TEXT PRIMARY KEY, name TEXT, password TEXT)''')
c.execute('''CREATE TABLE IF NOT EXISTS interventions 
             (id INTEGER PRIMARY KEY, date TEXT, type TEXT, duree REAL, ligne TEXT, machine TEXT, 
              techniciens TEXT, statut TEXT, probleme TEXT, solution TEXT, remarque TEXT, auteur TEXT, photo BLOB)''')
c.execute('''CREATE TABLE IF NOT EXISTS dat 
             (id INTEGER PRIMARY KEY, date_creation TEXT, demandeur TEXT, ligne TEXT, machine TEXT, 
              urgence TEXT, action TEXT, tech_suivi TEXT, commentaire TEXT, echeance TEXT, statut TEXT, auteur TEXT)''')
c.execute('''CREATE TABLE IF NOT EXISTS config (type TEXT, nom TEXT)''')
c.execute('''CREATE TABLE IF NOT EXISTS preventif_plan 
             (id INTEGER PRIMARY KEY, ligne TEXT, machine TEXT, tache TEXT, frequence_jours INTEGER, 
              derniere_date TEXT, prochaine_date TEXT, pieces_necessaires TEXT, temps_estime REAL DEFAULT 0, technicien_prev TEXT)''')

# Migration automatique pour les colonnes manquantes
try:
    c.execute("ALTER TABLE interventions ADD COLUMN photo BLOB")
except sqlite3.OperationalError:
    pass

try:
    c.execute("ALTER TABLE preventif_plan ADD COLUMN pieces_necessaires TEXT")
    c.execute("ALTER TABLE preventif_plan ADD COLUMN temps_estime REAL DEFAULT 0")
except sqlite3.OperationalError:
    pass

conn.commit()

# --- 3. FONCTIONS UTILITAIRES ---
def get_config(type_cfg):
    res = c.execute("SELECT nom FROM config WHERE type=?", (type_cfg,)).fetchall()
    return [r[0] for r in res]

def to_excel(df):
    output = io.BytesIO()
    # On retire les données binaires de la photo pour l'export Excel
    df_export = df.drop(columns=['photo']) if 'photo' in df.columns else df
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df_export.to_excel(writer, index=False, sheet_name='Sheet1')
    return output.getvalue()

def compress_image(image_file):
    """Compresse l'image pour un stockage ultra-léger (format JPEG qualité 30%)."""
    img = Image.open(image_file)
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")
    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=80, optimize=True)
    return buffer.getvalue()

def selecteur_ligne_machine_harmonise(prefixe, ligne_defaut=None, machine_defaut=None, inclure_toutes=True):
    lignes = get_config("Ligne")
    options_ligne = (["Toutes"] + lignes) if inclure_toutes else lignes
    idx_l = options_ligne.index(ligne_defaut) if ligne_defaut in options_ligne else 0
    ligne = st.selectbox("Ligne", options_ligne, index=idx_l, key=f"{prefixe}_ligne")
    if ligne != "Toutes":
        machines = get_config(f"Machine_{ligne}")
        options_mach = (["Toutes"] + machines) if inclure_toutes else machines
        idx_m = options_mach.index(machine_defaut) if machine_defaut in options_mach else 0
        machine = st.selectbox("Machine", options_mach, index=idx_m, key=f"{prefixe}_mach")
    else:
        machine = "Toutes"
        st.selectbox("Machine", ["Sélectionner une ligne"], disabled=True, key=f"{prefixe}_mach_dis")
    return ligne, machine

# --- 4. AUTHENTIFICATION ---
def load_and_hash_credentials():
    c.execute("SELECT COUNT(*) FROM users")
    if c.fetchone()[0] == 0:
        c.execute("INSERT INTO users VALUES (?, ?, ?)", ('admin', 'Administrateur PLF', 'admin123'))
        conn.commit()
    df_users = pd.read_sql("SELECT * FROM users", conn)
    creds = {"usernames": {}}
    for _, row in df_users.iterrows():
        creds["usernames"][row['username']] = {"name": row['name'], "password": row['password']}
    # Note: Dans une version réelle, les mots de passe seraient hachés ici
    return creds

credentials = load_and_hash_credentials()
authenticator = stauth.Authenticate(credentials, "maintenance_plf_cookie", "signature_key_2026", cookie_expiry_days=30)

if st.session_state["authentication_status"] is None or st.session_state["authentication_status"] is False:
    col_l1, col_l2, col_l3 = st.columns([1,2,1])
    with col_l2:
        try: st.image("logo.png", width=200)
        except: st.markdown("### 🛠️ MAINTENANCE CILAM")
    authenticator.login(location='main')
    if st.session_state["authentication_status"] is False:
        st.error("Identifiant ou mot de passe incorrect")

# --- 5. LOGIQUE PRINCIPALE ---
if st.session_state["authentication_status"]:
    user_full_name = st.session_state["name"]
    user_id = st.session_state["username"]
    is_admin = (user_id == "admin")

    with st.sidebar:
        try: st.image("logo.png", use_container_width=True)
        except: st.title("CILAM PLF")
        st.success(f"Utilisateur : {user_full_name}")
        authenticator.logout('Déconnexion', 'sidebar')
        st.divider()
        menu_options = ["Saisie Intervention", "📅 Plan de Préventif", "Historique Interventions", "📝 Gestion DAT", "📈 Statistiques"]
        if is_admin: menu_options.append("⚙️ Configuration")
        menu = st.sidebar.radio("Navigation", menu_options)

    st.markdown('<p style="font-size: 45px; font-weight: bold; color: #1E3A8A; text-align: center; border-bottom: 4px solid #1E3A8A; margin-bottom: 20px; padding-bottom: 10px;">MAINTENANCE CILAM PLF</p>', unsafe_allow_html=True)

    # --- A. SAISIE INTERVENTION ---
    if menu == "Saisie Intervention":
        st.header("🛠️ Saisie d'une Intervention")
        params = st.query_params
        col1, col2 = st.columns(2)
        with col1:
            date_int = st.date_input("Date de l'intervention", datetime.now())
            type_int = st.selectbox("Type d'intervention", ["CURATIF", "PREVENTIF", "AMELIORATION", "REGLAGE"])
            duree = st.number_input("Durée de l'intervention (minutes)", min_value=0.0, step=5.0)
            ligne, machine = selecteur_ligne_machine_harmonise("saisie", params.get("ligne"), params.get("machine"), inclure_toutes=False)
            photo_capture = st.camera_input("📸 Photo (Format léger)")

        with col2:
            techs_dispo = get_config("Technicien")
            techs = st.multiselect("Techniciens concernés", techs_dispo, default=[user_full_name] if user_full_name in techs_dispo else None)
            statut = st.selectbox("Statut final", ["Terminé", "En cours", "En attente pièce"])
            prob = st.text_area("Description du problème")
            sol = st.text_area("Solution apportée")
            remarque = st.text_input("Observations / Pièces changées")

        if st.button("Enregistrer l'intervention"):
            img_blob = compress_image(photo_capture) if photo_capture else None
            c.execute("""INSERT INTO interventions (date, type, duree, ligne, machine, techniciens, statut, probleme, solution, remarque, auteur, photo) 
                      VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""", 
                      (str(date_int), type_int, duree, ligne, machine, ", ".join(techs), statut, prob, sol, remarque, user_id, img_blob))
            conn.commit()
            st.success("✅ Intervention enregistrée avec succès !")
            st.query_params.clear()

    # --- B. PLAN DE PRÉVENTIF ---
    elif menu == "📅 Plan de Préventif":
        st.header("📋 Planning de Maintenance Préventive")
        tabs_titles = ["🗓️ Vision 7 Jours"]
        if is_admin: tabs_titles.append("⚙️ Paramétrage des Gammes")
        tabs = st.tabs(tabs_titles)
        with tabs[0]:
            df_prev = pd.read_sql("SELECT * FROM preventif_plan", conn)
            if not df_prev.empty:
                df_prev['prochaine_date'] = pd.to_datetime(df_prev['prochaine_date'])
                now = pd.Timestamp.now().normalize()
                semaine = df_prev[(df_prev['prochaine_date'] >= now) & (df_prev['prochaine_date'] <= now + timedelta(days=7))]
                st.subheader("📅 Tâches à venir (Prochains 7 jours)")
                st.dataframe(semaine.sort_values('prochaine_date'), use_container_width=True)
                st.divider()
                st.subheader("✅ Valider une tâche effectuée")
                col_v1, col_v2 = st.columns(2)
                t_val = col_v1.selectbox("Sélectionner la tâche réalisée", df_prev['tache'].tolist())
                techs_list = get_config("Technicien")
                tech_val = col_v2.multiselect("Intervenants", techs_list, default=[user_full_name] if user_full_name in techs_list else None)
                if st.button("Valider la réalisation"):
                    if tech_val:
                        row = df_prev[df_prev['tache'] == t_val].iloc[0]
                        next_dt = (datetime.now() + timedelta(days=int(row['frequence_jours']))).date()
                        c.execute("UPDATE preventif_plan SET derniere_date=?, prochaine_date=? WHERE tache=?", (str(datetime.now().date()), str(next_dt), t_val))
                        c.execute("""INSERT INTO interventions (date, type, duree, ligne, machine, techniciens, probleme, solution, auteur, statut) 
                                     VALUES (?,?,?,?,?,?,?,?,?,?)""",
                                  (str(datetime.now().date()), "PREVENTIF", row.get('temps_estime',0), row['ligne'], row['machine'], ", ".join(tech_val), f"Réalisation : {t_val}", f"Pièces : {row.get('pieces_necessaires','N/A')}", user_id, "Terminé"))
                        conn.commit()
                        st.success("Tâche mise à jour et historisée !")
                        st.rerun()
        if is_admin:
            with tabs[1]:
                st.subheader("➕ Ajouter une nouvelle gamme")
                col_p1, col_p2 = st.columns(2)
                with col_p1:
                    p_ligne, p_mach = selecteur_ligne_machine_harmonise("param_prev", inclure_toutes=False)
                    p_tache = st.text_input("Libellé de la tâche")
                with col_p2:
                    p_freq = st.number_input("Fréquence (en jours)", min_value=1, value=30)
                    p_temps = st.number_input("Temps estimé (en min)", min_value=0.0, step=5.0)
                p_pieces = st.text_area("🛒 Liste des pièces nécessaires")
                if st.button("Enregistrer la nouvelle gamme"):
                    if p_tache and p_mach != "Sélectionner une ligne":
                        prochaine = datetime.now() + timedelta(days=p_freq)
                        c.execute("INSERT INTO preventif_plan (ligne, machine, tache, frequence_jours, prochaine_date, pieces_necessaires, temps_estime) VALUES (?,?,?,?,?,?,?)",
                                  (p_ligne, p_mach, p_tache, p_freq, str(prochaine.date()), p_pieces, p_temps))
                        conn.commit()
                        st.rerun()
                st.divider()
                st.subheader("📋 Liste complète des gammes")
                df_edit = pd.read_sql("SELECT * FROM preventif_plan", conn)
                edited_prev = st.data_editor(df_edit, use_container_width=True, num_rows="dynamic")
                if st.button("Appliquer les modifications du plan"):
                    edited_prev.to_sql("preventif_plan", conn, if_exists="replace", index=False)
                    st.rerun()

    # --- C. HISTORIQUE ---
    elif menu == "Historique Interventions":
        st.header("📂 Historique des Interventions")
        col_h1, col_h2, col_h3 = st.columns([1, 1, 1])
        with col_h1: h_ligne, h_mach = selecteur_ligne_machine_harmonise("hist", inclure_toutes=True)
        with col_h2: h_type = st.selectbox("Type", ["Toutes", "CURATIF", "PREVENTIF", "AMELIORATION", "REGLAGE"])
        with col_h3: h_search = st.text_input("Recherche (Problème/Solution)")

        query = "SELECT * FROM interventions WHERE 1=1"
        db_params = []
        if h_ligne != "Toutes":
            query += " AND ligne = ?"; db_params.append(h_ligne)
        if h_mach != "Toutes":
            query += " AND machine = ?"; db_params.append(h_mach)
        if h_type != "Toutes":
            query += " AND type = ?"; db_params.append(h_type)
        if h_search:
            query += " AND (probleme LIKE ? OR solution LIKE ?)"; db_params.extend([f"%{h_search}%", f"%{h_search}%"])
        
        df_hist = pd.read_sql(query + " ORDER BY id DESC", conn, params=db_params)
        
        for _, row in df_hist.iterrows():
            with st.expander(f"🛠️ {row['date']} - {row['machine']} - {row['type']}"):
                c1, c2 = st.columns([3, 1])
                c1.write(f"**Techniciens :** {row['techniciens']}")
                c1.write(f"**Problème :** {row['probleme']}")
                c1.write(f"**Solution :** {row['solution']}")
                if row['photo']:
                    c2.image(row['photo'], caption="Photo terrain", use_container_width=True)
                if is_admin:
                    if st.button(f"🗑️ Supprimer {row['id']}", key=f"del_{row['id']}"):
                        c.execute("DELETE FROM interventions WHERE id=?", (row['id'],))
                        conn.commit()
                        st.rerun()
            
        st.download_button("📥 Télécharger Excel (Données)", data=to_excel(df_hist), file_name="historique_plf.xlsx")

  # --- GESTION DAT MODIFIÉ POUR INCLURE FERMETURE ---
with t_liste:
    # Afficher les demandes actuelles
    df_dat = pd.read_sql("SELECT * FROM dat ORDER BY id DESC", conn)
    
    if not df_dat.empty:
        st.subheader("📋 Liste des Demandes d'Actions Techniques")
        for index, row in df_dat.iterrows():
            with st.expander(f"🔧 {row['date_creation']} - {row['demandeur']} - {row['ligne']} ({row['statut']})"):
                st.write(f"**Urgence :** {row['urgence']}")
                st.write(f"**Action demandée :** {row['action']}")
                st.write(f"**Commentaire :** {row['commentaire']}")
                # Ajouter un bouton pour fermer une DAT
                if row['statut'] != "Fermée":
                    if st.button(f"✅ Fermer la DAT {row['id']}", key=f"close_dat_{row['id']}"):
                        c.execute("UPDATE dat SET statut='Fermée' WHERE id=?", (row['id'],))
                        conn.commit()
                        st.success(f"DAT {row['id']} fermée.")
                        st.rerun()
    else:
        st.info("Aucune demande trouvée.")

    # Statistiques
    total_dat = c.execute("SELECT COUNT(*) FROM dat").fetchone()[0]
    closed_dat = c.execute("SELECT COUNT(*) FROM dat WHERE statut = 'Fermée'").fetchone()[0]
    
    if total_dat > 0:
        taux_fermeture = (closed_dat / total_dat) * 100
        st.metric("Taux de fermeture des DAT (%)", f"{taux_fermeture:.2f}%")
    else:
        st.metric("Taux de fermeture des DAT (%)", "N/A")
    
    st.write(f"📊 Total des DAT : {total_dat}")
    st.write(f"✅ DAT Fermées : {closed_dat}")

    # --- E. STATISTIQUES ---
    elif menu == "📈 Statistiques":
        st.header("📊 Analyse d'Activité")
        df_stats = pd.read_sql("SELECT * FROM interventions", conn)
        if not df_stats.empty:
            col_s1, col_s2 = st.columns(2)
            with col_s1:
                st.plotly_chart(px.pie(df_stats, names='type', title="Répartition par Type"), use_container_width=True)
            with col_s2:
                st.plotly_chart(px.bar(df_stats, x='ligne', y='duree', color='type', title="Temps passé par Ligne"), use_container_width=True)
        else:
            st.info("Aucune donnée pour les statistiques.")

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
