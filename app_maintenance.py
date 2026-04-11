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