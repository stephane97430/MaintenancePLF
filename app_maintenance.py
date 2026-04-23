import streamlit as st
import streamlit_authenticator as stauth
import yaml
from yaml.loader import SafeLoader
import google.generativeai as genai
from streamlit_mic_recorder import speech_to_text
import streamlit_authenticator as stauth

# 1. Listez les mots de passe que vous voulez utiliser
passwords = ['admin123', 'tech123', 'guest123']

# 2. Transformez-les en codes sécurisés (Hashes)
hashed_passwords = stauth.Hasher(passwords).generate()

# 3. Affichez-les pour les copier
print(hashed_passwords)



# --- CONFIGURATION IA ---
genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])
model = genai.GenerativeModel('gemini-pro')

# --- CHARGEMENT AUTHENTIFICATION ---
with open('config.yaml') as file:
    config = yaml.load(file, Loader=SafeLoader)

# Correction 1 : Instanciation simplifiée (sans preauthorized en argument)
authenticator = stauth.Authenticate(
    config['credentials'],
    config['cookie']['name'],
    config['cookie']['key'],
    config['cookie']['expiry_days']
)

# Correction 2 : Login sans assignation de variables
authenticator.login(location='main', key='Login_form')

# Correction 3 : Utilisation du session_state pour vérifier le statut
if st.session_state["authentication_status"]:
    authenticator.logout('Déconnexion', 'sidebar')
    
    # Récupération des infos via session_state
    username = st.session_state["username"]
    name = st.session_state["name"]
    role = config['credentials']['usernames'][username]['role']

    st.title(f"MAINTENANCE PLF - {name}")

    # --- NAVIGATION ---
    tabs = ["SAISIE INTERVENTION", "STOCK MAGASIN"]
    if role == "administrator":
        tabs.append("CONFIGURATION")
    
    # Création dynamique des onglets selon le rôle
    tab_list = st.tabs(tabs)
    tab_saisie = tab_list[0]
    tab_stock = tab_list[1]

    # --- ONGLET SAISIE INTERVENTION ---
    with tab_saisie:
        st.header("Nouvelle Intervention")
        
        col1, col2 = st.columns(2)
        with col1:
            techniciens = st.multiselect("Techniciens", ["Tech A", "Tech B", "Tech C"])
            
            ateliers = {"Atelier 1": ["Ligne A", "Ligne B"], "Atelier 2": ["Ligne C"]}
            machines = {"Ligne A": ["Machine 101", "Machine 102"], "Ligne B": ["Machine 201"]}
            
            parent = st.selectbox("Atelier", list(ateliers.keys()))
            enfant = st.selectbox("Ligne", ateliers[parent])
            machine = st.selectbox("Machine", machines[enfant])

        with col2:
            photos = st.file_uploader("Prendre des photos", accept_multiple_files=True, type=['png', 'jpg'])
            
        st.subheader("Description du problème")
        text_input = speech_to_text(language='fr', start_prompt="🎙️ Cliquez pour parler", key='speech')
        
        description = st.text_area("Détails de l'incident", value=text_input if text_input else "")
        solution = st.text_area("Solution apportée")

        if st.button("Analyser l'intervention (IA)"):
            if solution:
                prompt = f"Analyse cette intervention technique : '{solution}'. Déduis les pièces de rechange nécessaires et donne-moi uniquement les codes magasins potentiels."
                response = model.generate_content(prompt)
                st.info(f"Analyse IA : {response.text}")
            else:
                st.warning("Veuillez remplir la solution avant l'analyse.")

    # --- ONGLET STOCK ---
    with tab_stock:
        st.header("Gestion du Stock")
        st.write("Visualisation des pièces et déduction automatique...")

    # --- ONGLET ADMIN (CONDITIONNEL) ---
    if role == "administrator" and len(tab_list) > 2:
        with tab_list[2]:
            st.header("Paramètres Administrateur")
            st.write("Colonnes paramétrables du stock")

# Correction 4 : Tests sur le statut via session_state
elif st.session_state["authentication_status"] is False:
    st.error('Identifiant ou mot de passe incorrect')
elif st.session_state["authentication_status"] is None:
    st.warning('Veuillez entrer vos identifiants')

