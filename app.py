import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials

# --- 1. CONFIGURAÇÃO VISUAL (Modo Embed/Camaleão) ---
st.set_page_config(layout="wide")

# CSS Hack para esconder menus e rodapé (Visual limpo para o Notion)
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

# --- 2. CONEXÃO HÍBRIDA (Funciona no PC e na Nuvem) ---
def conectar_banco():
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    
    # Tenta conectar via Segredo da Nuvem (Streamlit Cloud)
    if "gcp_service_account" in st.secrets:
        creds = Credentials.from_service_account_info(
            st.secrets["gcp_service_account"],
            scopes=scopes
        )
    # Se falhar, tenta conectar via Arquivo Local (Seu PC)
    else:
        creds = Credentials.from_service_account_file("credentials.json", scopes=scopes)
        
    client = gspread.authorize(creds)
    return client.open("LMS_Database")

def carregar_questoes():
    # Cache simples para performance
    if 'db_questoes' not in st.session_state:
        sheet = conectar_banco()
        worksheet = sheet.worksheet("DB_QUESTOES")
        dados = worksheet.get_all_records()
        st.session_state['db_questoes'] = pd.DataFrame(dados)
    return st.session_state['db_questoes']

# --- 3. LÓGICA INTELIGENTE (Lê a URL) ---
# Pega o parâmetro ?materia=Python da URL
params = st.query_params
materia_alvo = params.get("materia", None)

if not materia_alvo:
    # Tela de Boas-vindas (Caso abra o link direto sem parametros)
    st.title("🧩 Central de Exercícios")
    st.info("Este widget está pronto para ser conectado ao Notion.")
    st.markdown("Use o link no formato: `seu-app.streamlit.app/?materia=NomeDaMateria`")

else:
    # Tela de Questões (Quando vem do Notion)
    try:
        st.subheader(f"📝 Pratique: {materia_alvo}")
        df_questoes = carregar_questoes()
        
        # Filtra a matéria
        questoes_filtradas = df_questoes[df_questoes['materia'] == materia_alvo]
        
        if len(questoes_filtradas) == 0:
            st.warning(f"Nenhuma questão encontrada para '{materia_alvo}'.")
        
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
        st.error(f"Erro de conexão: {e}")