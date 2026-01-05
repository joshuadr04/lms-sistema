import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials

# --- 1. CONFIGURAÇÃO VISUAL ---
st.set_page_config(layout="wide")

# CSS para limpar o visual
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

# ==========================================
# 🚨 ÁREA DE DEBUG (CÂMERA DE SEGURANÇA) 🚨
# ==========================================
# Transforma os parâmetros em texto para a gente ler
params_recebidos = dict(st.query_params)
st.warning(f"🔍 DEBUG (O que chegou): {params_recebidos}")
# ==========================================

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

# --- 3. LÓGICA DO APP ---
# Tenta pegar a 'materia' do link
materia_alvo = st.query_params.get("materia", None)

if not materia_alvo:
    # Cenário 1: Link chegou vazio
    st.info("O sistema não encontrou o código da matéria no link.")
    st.write("Link que o App esperava receber: `...?materia=python1`")

else:
    # Cenário 2: Link chegou com algo
    try:
        st.subheader(f"📝 Pratique: {materia_alvo}")
        df_questoes = carregar_questoes()
        
        # Converte para texto para garantir que compare texto com texto
        questoes_filtradas = df_questoes[df_questoes['materia'].astype(str) == str(materia_alvo)]
        
        if len(questoes_filtradas) == 0:
            st.error(f"❌ Matéria '{materia_alvo}' não encontrada na planilha.")
            st.write("Matérias disponíveis no banco:", df_questoes['materia'].unique())
        
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
