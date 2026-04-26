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

try:
    c.execute("ALTER TABLE stock ADD COLUMN machine TEXT")
    conn.commit()
except sqlite3.OperationalError:
    # La colonne existe déjà, on ne fait rien
    pass
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
# Création de la table stock
c.execute('''CREATE TABLE IF NOT EXISTS stock 
             (code_mag TEXT PRIMARY KEY, code_fournisseur TEXT, designation TEXT, qte REAL, min REAL, prix REAL)''')

conn.commit()

# --- 3. FONCTIONS UTILITAIRES ---
def to_excel_history(df):
    output = io.BytesIO()
    # On retire la colonne photo pour l'Excel car le binaire n'est pas lisible ainsi
    df_export = df.drop(columns=['photo']) if 'photo' in df.columns else df
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df_export.to_excel(writer, index=False, sheet_name='Historique_Interventions')
    return output.getvalue()

def import_excel_history(uploaded_file):
    try:
        df_import = pd.read_excel(uploaded_file)
        # On ignore l'ID pour laisser SQLite l'auto-incrémenter
        if 'id' in df_import.columns:
            df_import = df_import.drop(columns=['id'])
        
        # Ajout d'une colonne photo vide si absente
        if 'photo' not in df_import.columns:
            df_import['photo'] = None
            
        df_import.to_sql('interventions', conn, if_exists='append', index=False)
        return True
    except Exception as e:
        st.error(f"Erreur lors de l'import historique : {e}")
        return False
def to_excel_stock(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Inventaire_Stock')
    return output.getvalue()

def import_excel_stock(uploaded_file):
    try:
        df_import = pd.read_excel(uploaded_file)
        # Vérification des colonnes critiques
        colonnes_requises = ['code_mag', 'qte']
        if not all(col in df_import.columns for col in colonnes_requises):
            st.error("Le fichier doit contenir au moins les colonnes 'code_mag' et 'qte'.")
            return False
        
        for _, row in df_import.iterrows():
            c.execute("UPDATE stock SET qte = ? WHERE code_mag = ?", (row['qte'], str(row['code_mag'])))
        conn.commit()
        return True
    except Exception as e:
        st.error(f"Erreur lors de l'import : {e}")
        return False

c.execute("SELECT COUNT(*) FROM config WHERE type='Atelier'")
if c.fetchone()[0] == 0:
    # 2. On crée l'atelier par défaut pour la CILAM
    c.execute("INSERT INTO config (type, nom) VALUES (?,?)", ("Atelier", "Atelier PLF"))
    
    # 3. On rattache toutes les lignes existantes à cet atelier
    # On transforme le type 'Ligne' en 'Ligne_Atelier PLF'
    c.execute("UPDATE config SET type = ? WHERE type = ?", ("Ligne_Atelier PLF", "Ligne"))
    
    conn.commit()
    st.info("Migration réussie : Toutes les lignes ont été rattachées à 'Atelier PLF'.")
def selecteur_atelier_ligne_machine(prefixe, atelier_defaut=None, ligne_defaut=None, machine_defaut=None, inclure_toutes=True):
    # 1. Sélection de l'Atelier
    ateliers = get_config("Atelier")
    options_at = (["Toutes"] + ateliers) if inclure_toutes else ateliers
    
    # Calcul de l'index pour éviter les erreurs si l'atelier par défaut n'est pas trouvé
    idx_at = 0
    if atelier_defaut in options_at:
        idx_at = options_at.index(atelier_defaut)
        
    atelier = st.selectbox("Atelier", options_at, index=idx_at, key=f"{prefixe}_at")
    
    ligne = "Toutes"
    machine = "Toutes"

    if atelier != "Toutes":
        # 2. Sélection de la Ligne
        lignes = get_config(f"Ligne_{atelier}")
        options_li = (["Toutes"] + lignes) if inclure_toutes else lignes
        idx_li = options_li.index(ligne_defaut) if ligne_defaut in options_li else 0
        ligne = st.selectbox("Ligne", options_li, index=idx_li, key=f"{prefixe}_li")
        
        if ligne != "Toutes":
            # 3. Sélection de la Machine
            machines = get_config(f"Machine_{ligne}")
            options_ma = (["Toutes"] + machines) if inclure_toutes else machines
            idx_ma = options_ma.index(machine_defaut) if machine_defaut in options_ma else 0
            machine = st.selectbox("Machine", options_ma, index=idx_ma, key=f"{prefixe}_ma")
    else:
        # Menus désactivés si aucun atelier n'est choisi
        st.selectbox("Ligne", ["Sélectionner un atelier"], disabled=True, key=f"{prefixe}_li_dis")
        st.selectbox("Machine", ["Sélectionner une ligne"], disabled=True, key=f"{prefixe}_ma_dis")
        
    return atelier, ligne, machine
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

def compress_image(image_file, qualite="Basse"):
    """Compresse l'image selon le niveau choisi : Basse (~30kb) ou Haute (~300kb)."""
    img = Image.open(image_file)
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")
    
    # Définition du taux de compression
    val_qualite = 20 if qualite == "Basse" else 85
    
    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=val_qualite, optimize=True)
    return buffer.getvalue()

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
from streamlit_mic_recorder import speech_to_text

def saisie_vocale(label="Cliquez pour parler"):
    """Affiche un bouton micro et retourne le texte transcrit."""
    text = speech_to_text(
        language='fr', 
        start_prompt="🎤 " + label, 
        stop_prompt="🛑 Arrêter", 
        key=f"voice_{label.replace(' ', '_')}"
    )
    return text

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
        menu_options = ["Saisie Intervention", "📅 Plan de Préventif", "Historique Interventions", "📦 Gestion de Stock", "📝 Gestion DAT", "📈 Statistiques"]
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
            atelier, ligne, machine = selecteur_atelier_ligne_machine("saisie", inclure_toutes=False)
            choix_qualite = st.radio("Qualité de la photo", ["Basse", "Haute"], horizontal=True)
            photo_capture = st.camera_input("📸 Photo terrain")

        with col2:
            techs_dispo = get_config("Technicien")
            techs = st.multiselect("Techniciens concernés", techs_dispo, default=[user_full_name] if user_full_name in techs_dispo else None)
            statut = st.selectbox("Statut final", ["Terminé", "En cours", "En attente pièce"])
            
            v_prob = saisie_vocale("Décrire le problème")
            prob = st.text_area("Description du problème", value=v_prob if v_prob else "")
            
            v_sol = saisie_vocale("Décrire la solution")
            sol = st.text_area("Solution apportée", value=v_sol if v_sol else "")
            
            df_pieces = pd.read_sql("SELECT code_mag, designation FROM stock", conn)
            options_pieces = ["Aucune"] + (df_pieces['code_mag'] + " - " + df_pieces['designation']).tolist()
            piece_choisie = st.selectbox("Pièce utilisée (déduction stock)", options_pieces)
            
            qte_utilisee = 1.0
            if piece_choisie != "Aucune":
                qte_utilisee = st.number_input("Quantité utilisée", min_value=0.1, step=1.0, value=1.0)
            
            remarque_lib = st.text_input("Observations complémentaires / Détails pièces")

        if st.button("🚀 Enregistrer l'intervention"):
            img_blob = compress_image(photo_capture, qualite=choix_qualite) if photo_capture else None
            remarque_finale = remarque_lib

            if piece_choisie != "Aucune":
                code_a_deduire = piece_choisie.split(" - ")[0]
                c.execute("SELECT qte FROM stock WHERE code_mag = ?", (code_a_deduire,))
                result = c.fetchone()
                if result:
                    qte_actuelle = result[0]
                    if qte_actuelle >= qte_utilisee:
                        nouvelle_qte = qte_actuelle - qte_utilisee
                        c.execute("UPDATE stock SET qte = ? WHERE code_mag = ?", (nouvelle_qte, code_a_deduire))
                        remarque_finale = f"[SORTIE STOCK: {code_a_deduire} x{qte_utilisee}] " + remarque_lib
                    else:
                        st.error(f"Stock insuffisant ({qte_actuelle} restants).")
                        st.stop()

            c.execute("""INSERT INTO interventions (date, type, duree, ligne, machine, techniciens, statut, probleme, solution, remarque, auteur, photo) 
                      VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""", 
                      (str(date_int), type_int, duree, ligne, machine, ", ".join(techs), statut, prob, sol, remarque_finale, user_id, img_blob))
            conn.commit()
            st.success("✅ Intervention enregistrée !")
            st.rerun()

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
                    p_atelier, p_ligne, p_mach = selecteur_atelier_ligne_machine("param_prev", inclure_toutes=False)
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

# --- C. GESTION DE STOCK ---
    elif menu == "📦 Gestion de Stock":
        st.header("📦 Gestion du Stock Pièces Détachées")
        t_stock, t_ajout, t_excel = st.tabs(["📋 Inventaire", "➕ Nouvelle Référence", "📥 Inventaire (Excel)"])
        
        with t_stock:
            df_stock = pd.read_sql("SELECT * FROM stock", conn)
            if not df_stock.empty:
                liste_m = ["Toutes"] + sorted(df_stock['machine'].unique().astype(str).tolist())
                filtre_m = st.selectbox("Filtrer par machine", liste_m)
                df_to_show = df_stock if filtre_m == "Toutes" else df_stock[df_stock['machine'] == filtre_m]
                st.dataframe(df_to_show, use_container_width=True)
            else:
                st.info("Stock vide.")

        with t_ajout:
            st.subheader("Enregistrer une nouvelle pièce")
            with st.form("form_stock"):
                c1, c2 = st.columns(2)
                c_mag = c1.text_input("CODE MAG")
                c_fourn = c1.text_input("CODE FOURNISSEUR")
                desig = c1.text_input("DESIGNATION")
                with c2:
                    # On récupère la ligne et machine via votre fonction existante
                    at_s, li_s, ma_s = selecteur_atelier_ligne_machine("stock_add", inclure_toutes=False)
                    q_ini = st.number_input("Quantité actuelle", min_value=0.0)
                    q_min = st.number_input("Seuil d'alerte", min_value=0.0)
                    px_u = st.number_input("Prix Unitaire", min_value=0.0)
                
                if st.form_submit_button("Ajouter au Stock"):
                    if c_mag and desig:
                        c.execute("INSERT INTO stock (code_mag, code_fournisseur, designation, qte, min, prix, machine) VALUES (?,?,?,?,?,?,?)", 
                                  (c_mag, c_fourn, desig, q_ini, q_min, px_u, ma_s))
                        conn.commit()
                        st.success(f"Pièce ajoutée pour {ma_s}")
                        st.rerun()

        with t_excel:
            st.subheader("Export/Import Inventaire")
            col_ex1, col_ex2 = st.columns(2)
            with col_ex1:
                df_exp = pd.read_sql("SELECT code_mag, designation, machine, qte FROM stock", conn)
                st.download_button("📥 Export Excel", to_excel_stock(df_exp), "Stock_CILAM.xlsx")
            with col_ex2:
                up = st.file_uploader("Import Excel", type=["xlsx"])
                if up and st.button("🚀 Lancer l'import"):
                    if import_excel_stock(up):
                        st.success("Mise à jour réussie")
                        st.rerun()

    # --- D. HISTORIQUE (ALIGNÉ SUR LE ELIF PRÉCÉDENT) ---
    elif menu == "Historique Interventions":
        st.header("📂 Historique")
        df_hist = pd.read_sql("SELECT * FROM interventions ORDER BY id DESC", conn)
        st.dataframe(df_hist, use_container_width=True)
# N'oubliez pas de fermer la base de données à la fin du fichier (hors de l'auth)
# conn.close()
    elif menu == "Historique Interventions":
        st.header("📂 Historique des Interventions")
        col_h1, col_h2, col_h3 = st.columns([1, 1, 1])
        with col_h1: h_atelier, h_ligne, h_mach = selecteur_atelier_ligne_machine("hist", inclure_toutes=True)
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
            
# --- AJOUT DU BOUTON IMPORT ---
        st.divider()
        st.subheader("📥 Importation de données")
        with st.expander("Importer un historique (Fichier Excel)"):
            up_hist = st.file_uploader("Choisir un fichier .xlsx", type=["xlsx"], key="up_hist")
            if up_hist and st.button("🚀 Lancer l'importation de l'historique"):
                if import_excel_history(up_hist):
                    st.success("L'historique a été importé avec succès !")
                    st.rerun()
        
        # Le bouton d'export existant
        st.download_button("📥 Télécharger Excel (Données)", data=to_excel(df_hist), file_name="historique_plf.xlsx")

    # --- E. GESTION DAT ---
    elif menu == "📝 Gestion DAT":
        st.header("📝 Demandes d'Actions Techniques")
        t_crea, t_liste = st.tabs(["➕ Créer une DAT", "📋 Liste des demandes"])
        with t_crea:
            col1, col2 = st.columns(2)
            with col1:
                at_s, li_s, ma_s = selecteur_atelier_ligne_machine("dat_crea", inclure_toutes=False)
                d_demandeur = st.text_input("Nom du demandeur", value=user_full_name)
                d_urgence = st.selectbox("Niveau d'urgence", ["Basse", "Moyenne", "Haute", "CRITIQUE"])
            with col2:
                # --- Action demandée avec Option Vocale ---
                v_action = saisie_vocale("Détails de l'action")
                d_action = st.text_area("Action demandée détaillée", value=v_action if v_action else "")
                
                d_echeance = st.date_input("Date d'échéance souhaitée", datetime.now() + timedelta(days=7))
            if st.button("Soumettre la DAT"):
                c.execute("""INSERT INTO dat (date_creation, demandeur, ligne, machine, urgence, action, statut, auteur) 
                          VALUES (?,?,?,?,?,?,?,?)""", (str(datetime.now().date()), d_demandeur, d_ligne, d_mach, d_urgence, d_action, "Ouvert", user_id))
                conn.commit()
                st.success("DAT enregistrée !")
        with t_liste:
            df_dat = pd.read_sql("SELECT * FROM dat ORDER BY id DESC", conn)
            edited_dat = st.data_editor(df_dat, use_container_width=True, num_rows="dynamic" if is_admin else "fixed")
            if st.button("Sauvegarder les modifications DAT"):
                edited_dat.to_sql("dat", conn, if_exists="replace", index=False)
                st.success("Données synchronisées.")

    # --- F. STATISTIQUES ---
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
# --- G. GESTION DE STOCK ---
    elif menu == "📦 Gestion de Stock":
        st.header("📦 Inventaire des Pièces Détachées")
        t_stock, t_ajout = st.tabs(["📋 État du Stock", "➕ Ajouter une Pièce"])
        
        with t_stock:
            df_stock = pd.read_sql("SELECT * FROM stock", conn)
            # Mise en évidence des stocks bas (Alerte si QTE < MIN)
            def highlight_min(s):
                return ['background-color: #ffcccc' if s.qte < s.min else '' for _ in s]
            
            if not df_stock.empty:
                st.dataframe(df_stock.style.apply(highlight_min, axis=1), use_container_width=True)
                
                if is_admin:
                    st.subheader("Modifier le stock")
                    edited_stock = st.data_editor(df_stock, use_container_width=True, num_rows="dynamic", key="editor_stock")
                    if st.button("Enregistrer les modifications"):
                        edited_stock.to_sql("stock", conn, if_exists="replace", index=False)
                        st.success("Stock mis à jour.")
                        st.rerun()
            else:
                st.info("Le stock est vide.")

        with t_ajout:
            with st.form("ajout_piece"):
                col1, col2 = st.columns(2)
                code_mag = col1.text_input("CODE MAG (Identifiant unique)")
                code_fourn = col1.text_input("CODE FOURNISSEUR")
                desig = col1.text_input("DESIGNATION")
                qte_ini = col2.number_input("Quantité en stock", min_value=0.0)
                qte_min = col2.number_input("Seuil Minimum (Alerte)", min_value=0.0)
                prix_u = col2.number_input("Prix Unitaire", min_value=0.0)
                
                if st.form_submit_button("Ajouter au catalogue"):
                    if code_mag and desig:
                        c.execute("INSERT INTO stock VALUES (?,?,?,?,?,?)", (code_mag, code_fourn, desig, qte_ini, qte_min, prix_u))
                        conn.commit()
                        st.success(f"Pièce {code_mag} ajoutée !")
                        st.rerun()

# --- H. CONFIGURATION (ADMIN) ---
    elif menu == "⚙️ Configuration":
        if is_admin:
            st.header("⚙️ Paramètres Système")
            tab_struct, tab_users = st.tabs(["🏗️ Structure Usine", "👤 Gestion des Utilisateurs"])
            
            with tab_struct:
                col_c1, col_c2 = st.columns(2)
                
                with col_c1:
                    st.subheader("➕ Ajouter un élément")
                    t_cfg = st.selectbox("Type", ["Atelier", "Ligne", "Machine", "Technicien"])
                    
                    nom_cfg = ""
                    type_store = ""

                    if t_cfg == "Atelier":
                        nom_cfg = st.text_input("Nom de l'Atelier")
                        type_store = "Atelier"
                    
                    elif t_cfg == "Ligne":
                        ateliers_dispo = get_config("Atelier")
                        if ateliers_dispo:
                            parent = st.selectbox("Atelier parent", ateliers_dispo)
                            nom_cfg = st.text_input("Nom de la Ligne")
                            type_store = f"Ligne_{parent}"
                        else:
                            st.warning("Créez d'abord un Atelier.")
                        
                    elif t_cfg == "Machine":
                        at_temp_list = get_config("Atelier")
                        if at_temp_list:
                            at_temp = st.selectbox("Atelier de la machine", at_temp_list, key="at_m")
                            lignes_dispo = get_config(f"Ligne_{at_temp}")
                            if lignes_dispo:
                                li_temp = st.selectbox("Ligne parente", lignes_dispo)
                                nom_cfg = st.text_input("Désignation machine")
                                type_store = f"Machine_{li_temp}"
                            else:
                                st.warning("Créez d'abord une Ligne.")
                        else:
                            st.warning("Créez d'abord un Atelier.")

                    elif t_cfg == "Technicien":
                        nom_cfg = st.text_input("Nom et Prénom du Technicien")
                        type_store = "Technicien"

                    if st.button("Ajouter à la config"):
                        if nom_cfg and type_store:
                            c.execute("INSERT INTO config (type, nom) VALUES (?,?)", (type_store, nom_cfg))
                            conn.commit()
                            st.success(f"Ajouté : {nom_cfg}")
                            st.rerun()

                with col_c2:
                    st.subheader("🗑️ Supprimer un élément")
                    all_cfg = pd.read_sql("SELECT * FROM config", conn)
                    if not all_cfg.empty:
                        sel_del = st.selectbox("Élément à supprimer", all_cfg['nom'].tolist())
                        if st.button("❌ Supprimer définitivement"):
                            c.execute("DELETE FROM config WHERE nom=?", (sel_del,))
                            conn.commit()
                            st.rerun()

            with tab_users:
                st.subheader("👤 Gestion des comptes")
                df_u = pd.read_sql("SELECT username, name FROM users", conn)
                col_u1, col_u2 = st.columns(2)
                
                with col_u1:
                    st.markdown("**➕ Nouvel utilisateur**")
                    nu = st.text_input("Login (ex: j.dupont)")
                    nn = st.text_input("Nom Complet")
                    np = st.text_input("Mot de passe", type="password")
                    if st.button("Créer le compte"):
                        if nu and np:
                            try:
                                c.execute("INSERT INTO users VALUES (?, ?, ?)", (nu, nn, np))
                                conn.commit()
                                st.success("Utilisateur ajouté !")
                                st.rerun()
                            except: 
                                st.error("L'identifiant existe déjà.")
                
                with col_u2:
                    st.markdown("**🔑 Sécurité & Suppression**")
                    target = st.selectbox("Sélectionner un compte", df_u['username'].tolist())
                    mod_pw = st.text_input("Nouveau MDP", type="password", key="mod_pw_sec")
                    if st.button("Modifier le MDP") and mod_pw:
                        c.execute("UPDATE users SET password=? WHERE username=?", (mod_pw, target))
                        conn.commit()
                        st.success("Mot de passe mis à jour.")
                    
                    if target != "admin":
                        if st.button("❌ Supprimer l'utilisateur", type="primary"):
                            c.execute("DELETE FROM users WHERE username=?", (target,))
                            conn.commit()
                            st.rerun()

