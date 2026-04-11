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

c.execute('''CREATE TABLE IF NOT EXISTS stocks 
             (id INTEGER PRIMARY KEY, code_magasin TEXT UNIQUE, ref_constructeur TEXT, 
              designation TEXT, quantite_reelle INTEGER, stock_mini INTEGER)''')
c.execute('''CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, name TEXT, password TEXT)''')
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
import smtplib
from email.mime.text import MIMEText

def deduire_stock_automatique(texte_intervention):
    pieces_en_stock = c.execute("SELECT designation, quantite_reelle FROM stocks").fetchall()
    actions_faites = []
    for designation, qte in pieces_en_stock:
        if designation.lower() in texte_intervention.lower():
            if qte > 0:
                nouvelle_qte = qte - 1
                c.execute("UPDATE stocks SET quantite_reelle = ? WHERE designation = ?", (nouvelle_qte, designation))
                actions_faites.append(f"📦 Stock mis à jour : {designation} (-1)")
            else:
                st.error(f"⚠️ Rupture de stock pour : {designation}")
    conn.commit()
    return actions_faites

def envoyer_alerte_dat(ligne, machine, action):
    sender_email = "latchoumanestephane@gmail.com"
    receiver_email = "stephane_latchoumane@cilam.com"
    password = "wkrz dljx isrf jhuw"
    msg = MIMEText(f"URGENCE CRITIQUE sur la ligne {ligne}\nMachine : {machine}\n\nAction demandée : {action}")
    msg['Subject'] = f"⚠️ ALERTE DAT CRITIQUE - {machine}"
    msg['From'] = sender_email
    msg['To'] = receiver_email
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(sender_email, password)
            server.sendmail(sender_email, receiver_email, msg.as_string())
    except Exception as e:
        st.error(f"Erreur d'envoi mail : {e}")

def get_config(type_cfg):
    res = c.execute("SELECT nom FROM config WHERE type=?", (type_cfg,)).fetchall()
    return [r[0] for r in res]

def to_excel(df):
    output = io.BytesIO()
    df_export = df.drop(columns=['photo']) if 'photo' in df.columns else df
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df_export.to_excel(writer, index=False, sheet_name='Sheet1')
    return output.getvalue()

def compress_image(image_file):
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
    return creds

credentials = load_and_hash_credentials()
authenticator = stauth.Authenticate(credentials, "maintenance_plf_cookie", "signature_key_2026", cookie_expiry_days=30)

# --- 5. LOGIQUE D'AFFICHAGE ---
if st.session_state["authentication_status"] is None or st.session_state["authentication_status"] is False:
    col_l1, col_l2, col_l3 = st.columns([1,2,1])
    with col_l2:
        try: st.image("logo.png", width=200)
        except: st.markdown("### 🛠️ MAINTENANCE CILAM")
    authenticator.login(location='main')
    if st.session_state["authentication_status"] is False:
        st.error("Identifiant ou mot de passe incorrect")

elif st.session_state["authentication_status"]:
    user_full_name = st.session_state["name"]
    user_id = st.session_state["username"]
    is_admin = (user_id == "admin")

    with st.sidebar:
        try: st.image("logo.png", use_container_width=True)
        except: st.title("CILAM PLF")
        st.success(f"Utilisateur : {user_full_name}")
        authenticator.logout('Déconnexion', 'sidebar')
        st.divider()
        menu_options = ["Saisie Intervention", "📅 Plan de Préventif", "Historique Interventions", "📝 Gestion DAT", "📈 Statistiques", "📦 Gestion des Stocks"]
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
                      VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""", (str(date_int), type_int, duree, ligne, machine, ", ".join(techs), statut, prob, sol, remarque, user_id, img_blob))          
            conn.commit()
            logs_stock = deduire_stock_automatique(remarque)
            for log in logs_stock: st.info(log) 
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
                                     VALUES (?,?,?,?,?,?,?,?,?,?)""", (str(datetime.now().date()), "PREVENTIF", row.get('temps_estime',0), row['ligne'], row['machine'], ", ".join(tech_val), f"Réalisation : {t_val}", f"Pièces : {row.get('pieces_necessaires','N/A')}", user_id, "Terminé"))
                        conn.commit()
                        st.success("Tâche mise à jour !")
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
                        c.execute("INSERT INTO preventif_plan (ligne, machine, tache, frequence_jours, prochaine_date, pieces_necessaires, temps_estime) VALUES (?,?,?,?,?,?,?)", (p_ligne, p_mach, p_tache, p_freq, str(prochaine.date()), p_pieces, p_temps))
                        conn.commit()
                        st.rerun()
                st.divider()
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
                if row['photo']: c2.image(row['photo'], caption="Photo terrain", use_container_width=True)
                if is_admin:
                    if st.button(f"🗑️ Supprimer {row['id']}", key=f"del_{row['id']}"):
                        c.execute("DELETE FROM interventions WHERE id=?", (row['id'],))
                        conn.commit()
                        st.rerun()
        st.download_button("📥 Télécharger Excel", data=to_excel(df_hist), file_name="historique_plf.xlsx")

    # --- D. GESTION DAT ---
    elif menu == "📝 Gestion DAT":
        st.header("📝 Demandes d'Actions Techniques")
        t_crea, t_liste = st.tabs(["➕ Créer une DAT", "📋 Liste des demandes"])
        with t_crea:
            col1, col2 = st.columns(2)
            with col1:
                d_ligne, d_mach = selecteur_ligne_machine_harmonise("dat_crea", inclure_toutes=False)
                d_demandeur = st.text_input("Nom du demandeur", value=user_full_name)
                d_urgence = st.selectbox("Niveau d'urgence", ["Basse", "Moyenne", "Haute", "CRITIQUE"])
            with col2:
                d_action = st.text_area("Action demandée détaillée")
                d_echeance = st.date_input("Date d'échéance souhaitée", datetime.now() + timedelta(days=7))
            if st.button("Soumettre la DAT"):
                c.execute("INSERT INTO dat (date_creation, demandeur, ligne, machine, urgence, action, statut, auteur) VALUES (?,?,?,?,?,?,?,?)", (str(datetime.now().date()), d_demandeur, d_ligne, d_mach, d_urgence, d_action, "Ouvert", user_id))
                conn.commit()
                st.success("DAT enregistrée !")
                if d_urgence == "CRITIQUE": envoyer_alerte_dat(d_ligne, d_mach, d_action)
        with t_liste:
            df_dat = pd.read_sql("SELECT * FROM dat ORDER BY id DESC", conn)
            edited_dat = st.data_editor(df_dat, use_container_width=True, num_rows="dynamic" if is_admin else "fixed")
            if st.button("Sauvegarder les modifications DAT"):
                edited_dat.to_sql("dat", conn, if_exists="replace", index=False)
                st.success("Données synchronisées.")

    # --- E. STATISTIQUES ---
    elif menu == "📈 Statistiques":
        st.header("📊 Tableau de Bord Maintenance")
        df_stats = pd.read_sql("SELECT * FROM interventions", conn)
        if not df_stats.empty:
            df_stats['date'] = pd.to_datetime(df_stats['date'], errors='coerce')
            df_stats = df_stats.dropna(subset=['date'])
            tab_global, tab_fiabilite = st.tabs(["🌍 Vision Globale", "⚙️ Fiabilité Machines"])
            with tab_global:
                col_kpi1, col_kpi2, col_kpi3 = st.columns(3)
                col_kpi1.metric("Total Interventions", f"{len(df_stats)}")
                col_kpi2.metric("Temps Total", f"{df_stats['duree'].sum()/60:.1f} h")
                col_g1, col_g2 = st.columns(2)
                with col_g1: st.plotly_chart(px.pie(df_stats, names='type', title="Répartition par Type"), use_container_width=True)
                with col_g2: st.plotly_chart(px.histogram(df_stats, x='date', y='duree', color='type', title="Charge de travail"), use_container_width=True)
            with tab_fiabilite:
                df_curatif = df_stats[df_stats['type'] == 'CURATIF'].sort_values(['machine', 'date'])
                if len(df_curatif) > 0:
                    df_curatif['diff'] = df_curatif.groupby('machine')['date'].diff().dt.days
                    mtbf = df_curatif.dropna(subset=['diff']).groupby('machine')['diff'].mean().reset_index()
                    st.plotly_chart(px.bar(mtbf, x='machine', y='diff', title="MTBF (Jours)"), use_container_width=True)

    # --- F. GESTION DES STOCKS ---
    elif menu == "📦 Gestion des Stocks":
        st.header("📦 Gestion du Magasin Pièces Rechange")
        tab_inv, tab_add = st.tabs(["📋 Inventaire & Alertes", "➕ Entrée Stock / Nouvelle Réf"])
        with tab_inv:
            df_s = pd.read_sql("SELECT * FROM stocks", conn)
            if not df_s.empty:
                st.dataframe(df_s, use_container_width=True)
                alertes = df_s[df_s['quantite_reelle'] <= df_s['stock_mini']]
                if not alertes.empty: st.warning(f"⚠️ {len(alertes)} références critiques !")
            else: st.info("Le magasin est vide.")
        with tab_add:
            with st.form("form_stock"):
                c_mag = st.text_input("Code Magasin")
                c_ref = st.text_input("Référence Constructeur")
                c_des = st.text_input("Désignation")
                c_qte = st.number_input("Quantité", min_value=0)
                c_mini = st.number_input("Stock Mini", min_value=0)
                if st.form_submit_button("Enregistrer"):
                    if c_mag and c_des:
                        c.execute("INSERT OR REPLACE INTO stocks (code_magasin, ref_constructeur, designation, quantite_reelle, stock_mini) VALUES (?,?,?,?,?)", (c_mag, c_ref, c_des, c_qte, c_mini))
                        conn.commit()
                        st.rerun()

    # --- G. CONFIGURATION ---
    elif menu == "⚙️ Configuration" and is_admin:
        st.header("⚙️ Paramètres Système")
        t_cfg = st.selectbox("Type", ["Technicien", "Ligne", "Machine"])
        nom_cfg = st.text_input(f"Désignation {t_cfg}")
        if st.button("Ajouter"):
            c.execute("INSERT INTO config (type, nom) VALUES (?,?)", (t_cfg, nom_cfg))
            conn.commit()
            st.rerun()
