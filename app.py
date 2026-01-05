import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials

# --- 1. CONFIGURAÇÃO VISUAL ---
st.set_page_config(layout="wide")

# CSS Hack para esconder menus e rodapé
st.markdown("""
    <style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    .block-container {
        padding-top: 1rem;
        padding-bottom: 0rem;
        padding-left: 1rem;
        padding-right: 1rem;
    }
    </style>
    """, unsafe_allow_html=True)

# --- 🚨 ÁREA DE DEBUG (O DETETIVE) 🚨 ---
# Isso vai mostrar na tela o que o Streamlit está lendo do link.
# Se aparecer {}, significa que o link chegou vazio.
st.warning(f"🔍 DEBUG: O App recebeu estes parâmetros: {dict(st.query_params)}")
# ----------------------------------------

# --- 2. CONEXÃO HÍBRIDA ---
def conectar_banco():
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    
    if "gcp_service_account" in st.secrets:
        creds = Credentials.from_service_account_info(
            st.secrets["gcp_service_account"],
            scopes=scopes
        )
    else:
        creds = Credentials.from_service_account_file("credentials.json", scopes=scopes)
        
    client = gspread.authorize(creds)
    return client.open("LMS_Database")

def carregar_questoes():
    if 'db_questoes' not in st.session_state:
        sheet = conectar_banco()
        worksheet = sheet.worksheet("DB_QUESTOES")
        dados = worksheet.get_all_records()
        st.session_state['db_questoes'] = pd.DataFrame(dados)
    return st.session_state['db_questoes']

# --- 3. LÓGICA INTELIGENTE ---
params = st.query_params
materia_alvo = params.get("materia", None)

if not materia_alvo:
    # Tela de Boas-vindas (Link vazio)
    st.info("O sistema não detectou nenhuma matéria no link.")
    st.write("Link esperado: `seu-app.app/?materia=python1`")

else:
    # Tela de Questões
    try:
        st.subheader(f"📝 Pratique: {materia_alvo}")
        df_questoes = carregar_questoes()
        
        # Filtra a matéria (converte tudo para string para evitar erro)
        questoes_filtradas = df_questoes[df_questoes['materia'].astype(str) == str(materia_alvo)]
        
        if len(questoes_filtradas) == 0:
            st.warning(f"Nenhuma questão encontrada para o código '{materia_alvo}'. Verifique a planilha.")
            st.write("Matérias disponíveis na planilha:", df_questoes['materia'].unique())
        
        for index, row in questoes_filtradas.iterrows():
            with st.container(border=True):
                st.markdown(f"**{row['enunciado']}**")
                
                opcoes = {
                    f"A) {row['alternativa_a']}": 'a',
                    f"B) {row['alternativa_b']}": 'b',
                    f"C) {row['alternativa_c']}": 'c',
                    f"D) {row['alternativa_d']}": 'd'
                }
                
                resposta = st.radio("Alternativa:", list(opcoes.keys()), key=f"q_{row['id']}", index=None, label_visibility="collapsed")
                
                if st.button(f"Verificar", key=f"btn_{row['id']}"):
                    if resposta:
                        letra = opcoes[resposta]
                        if letra.lower() == str(row['gabarito']).lower():
                            st.success("✅ Correto!")
                        else:
                            st.error(f"❌ Errado. Gabarito: {str(row['gabarito']).upper()}")
                            st.caption(f"💡 {row['comentario']}")
    except Exception as e:
        st.error(f"Erro técnico: {e}")
