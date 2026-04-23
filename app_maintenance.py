import streamlit as st
import streamlit_authenticator as stauth
import yaml
from yaml.loader import SafeLoader
import google.generativeai as genai
from streamlit_mic_recorder import speech_to_text

# --- CONFIGURATION IA ---
# La clé API est stockée dans .streamlit/secrets.toml
genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])
model = genai.GenerativeModel('gemini-pro')

# --- CHARGEMENT AUTHENTIFICATION ---
with open('config.yaml') as file:
    config = yaml.load(file, Loader=SafeLoader)

authenticator = stauth.Authenticate(
    config['credentials'],
    config['cookie']['name'],
    config['cookie']['key'],
    config['cookie']['expiry_days'],
)

name, authentication_status, username = authenticator.login(location= 'main')

if authentication_status:
    authenticator.logout('Déconnexion', 'sidebar')
    role = config['credentials']['usernames'][username]['role']

    st.title(f"MAINTENANCE PLF - {name}")

    # --- NAVIGATION ---
    tabs = ["SAISIE INTERVENTION", "STOCK MAGASIN"]
    if role == "administrator":
        tabs.append("CONFIGURATION")
    
    tab_saisie, tab_stock = st.tabs(tabs[:2])

    # --- ONGLET SAISIE INTERVENTION ---
    with tab_saisie:
        st.header("Nouvelle Intervention")
        
        col1, col2 = st.columns(2)
        with col1:
            techniciens = st.multiselect("Techniciens", ["Tech A", "Tech B", "Tech C"])
            
            # Sélection en cascade
            ateliers = {"Atelier 1": ["Ligne A", "Ligne B"], "Atelier 2": ["Ligne C"]}
            machines = {"Ligne A": ["Machine 101", "Machine 102"], "Ligne B": ["Machine 201"]}
            
            parent = st.selectbox("Atelier", list(ateliers.keys()))
            enfant = st.selectbox("Ligne", ateliers[parent])
            machine = st.selectbox("Machine", machines[enfant])

        with col2:
            photos = st.file_uploader("Prendre des photos", accept_multiple_files=True, type=['png', 'jpg'])
            
        st.subheader("Description du problème")
        # Saisie vocale gratuite (Web Speech API via streamlit-mic-recorder)
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
        # Ici, vous chargeriez votre base de données (CSV ou SQL)
        st.write("Visualisation des pièces et déduction automatique...")

    # --- ONGLET ADMIN (CONDITIONNEL) ---
    if role == "administrator":
        with st.sidebar.expander("Paramètres Administrateur"):
            st.write("Colonnes paramétrables du stock")
            # Logique pour modifier les colonnes ici

elif authentication_status == False:
    st.error('Identifiant ou mot de passe incorrect')
elif authentication_status == None:
    st.warning('Veuillez entrer vos identifiants')
