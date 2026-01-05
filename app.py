import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials

# --- 1. CONFIGURAÇÃO VISUAL ---
st.set_page_config(layout="wide")
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

# --- 2. CONEXÃO E CARREGAMENTO ---
def conectar_banco():
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    if "gcp_service_account" in st.secrets:
        creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scopes)
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

# --- 3. LÓGICA BLINDADA (FAIL-SAFE) ---
try:
    df_questoes = carregar_questoes()
    lista_materias = df_questoes['materia'].unique()
    
    # Tenta pegar a matéria pelo Link (Plano A)
    param_materia = st.query_params.get("materia", None)
    
    materia_selecionada = None

    if param_materia:
        # Se veio pelo link, usa direto
        materia_selecionada = param_materia
    else:
        # PLANO B: Se o link falhou (Notion), mostra o menu!
        st.info("👋 Selecione o módulo abaixo para começar:")
        # Cria um dropdown para o aluno escolher
        materia_selecionada = st.selectbox("Escolha a Matéria:", lista_materias, index=None, placeholder="Clique para selecionar...")

    # --- 4. EXIBIÇÃO DAS QUESTÕES ---
    if materia_selecionada:
        st.subheader(f"📝 Pratique: {materia_selecionada}")
        
        # Filtro robusto (converte para string)
        questoes_filtradas = df_questoes[df_questoes['materia'].astype(str) == str(materia_selecionada)]
        
        if len(questoes_filtradas) == 0:
            st.warning(f"Não há questões cadastradas para: {materia_selecionada}")
        
        for index, row in questoes_filtradas.iterrows():
            with st.container(border=True):
                st.markdown(f"**{row['enunciado']}**")
                
                opcoes = {
                    f"A) {row['alternativa_a']}": 'a',
                    f"B) {row['alternativa_b']}": 'b',
                    f"C) {row['alternativa_c']}": 'c',
                    f"D) {row['alternativa_d']}": 'd'
                }
                
                key_unica = f"q_{row['id']}"
                resposta = st.radio("Alternativa:", list(opcoes.keys()), key=key_unica, index=None, label_visibility="collapsed")
                
                if st.button("Verificar", key=f"btn_{row['id']}"):
                    if resposta:
                        letra = opcoes[resposta]
                        if letra.lower() == str(row['gabarito']).lower():
                            st.success("✅ Correto!")
                        else:
                            st.error(f"❌ Errado. Gabarito: {str(row['gabarito']).upper()}")
                            st.caption(f"💡 {row['comentario']}")

except Exception as e:
    st.error(f"Erro de conexão: {e}")
