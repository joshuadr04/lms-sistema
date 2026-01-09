import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials

# --- 1. CONFIGURAÇÃO VISUAL ---
st.set_page_config(layout="wide", page_title="LMS - Banco & Provas")

st.markdown("""
    <style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    .block-container {padding-top: 1rem; padding-bottom: 2rem;}
    .login-box {
        padding: 20px;
        border-radius: 10px;
        background-color: #f0f2f6;
        text-align: center;
        margin-bottom: 20px;
    }
    </style>
    """, unsafe_allow_html=True)

# --- 2. CONEXÃO GOOGLE SHEETS ---
def conectar_banco():
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    
    if "gcp_service_account" in st.secrets:
        creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scopes)
    else:
        creds = Credentials.from_service_account_file("credentials.json", scopes=scopes)
        
    client = gspread.authorize(creds)
    return client.open("LMS_Database")

@st.cache_data(ttl=60)
def carregar_dados(aba_nome):
    try:
        sheet = conectar_banco()
        worksheet = sheet.worksheet(aba_nome)
        dados = worksheet.get_all_records()
        return pd.DataFrame(dados)
    except:
        return pd.DataFrame()

# --- 3. CONTROLE DE SESSÃO (LOGIN) ---
if 'usuario_ativo' not in st.session_state:
    st.session_state['usuario_ativo'] = None

# ==================================================
# 🔐 TELA DE LOGIN (HÍBRIDA)
# ==================================================
if not st.session_state['usuario_ativo']:
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("<div class='login-box'><h2>🎓 Banco de Questões</h2></div>", unsafe_allow_html=True)
        
        matricula_input = st.text_input("Digite sua Matrícula:", placeholder="Ex: 202401")
        
        if 'pedir_senha' not in st.session_state:
            st.session_state['pedir_senha'] = False

        if st.button("Entrar", use_container_width=True):
            df_alunos = carregar_dados("DB_ALUNOS")
            
            # Modo Teste (Se não houver aba de alunos)
            if df_alunos.empty:
                st.session_state['usuario_ativo'] = matricula_input
                st.session_state['nome_aluno'] = "Aluno Teste"
                st.rerun()

            aluno = df_alunos[df_alunos['matricula'].astype(str) == str(matricula_input)]
            
            if not aluno.empty:
                dados = aluno.iloc[0]
                senha_registrada = str(dados.get('senha', '')).strip()
                
                # Sem senha (Entra direto)
                if senha_registrada == "":
                    st.session_state['usuario_ativo'] = matricula_input
                    st.session_state['nome_aluno'] = dados['nome']
                    st.success(f"Bem-vindo(a), {dados['nome']}!")
                    st.rerun()
                # Com senha (Pede senha)
                else:
                    st.session_state['pedir_senha'] = True
                    st.session_state['temp_matricula'] = matricula_input
                    st.session_state['temp_nome'] = dados['nome']
                    st.session_state['temp_senha_real'] = senha_registrada
                    st.rerun()
            else:
                st.error("Matrícula não encontrada.")

        if st.session_state['pedir_senha']:
            st.info(f"Olá, {st.session_state['temp_nome']}. Digite sua senha.")
            senha_input = st.text_input("Senha:", type="password")
            if st.button("Confirmar Senha", type="primary"):
                if str(senha_input) == str(st.session_state['temp_senha_real']):
                    st.session_state['usuario_ativo'] = st.session_state['temp_matricula']
                    st.session_state['nome_aluno'] = st.session_state['temp_nome']
                    del st.session_state['pedir_senha']
                    st.rerun()
                else:
                    st.error("Senha incorreta.")

# ==================================================
# 🚀 ÁREA LOGADA (BANCO & PROVAS)
# ==================================================
else:
    # Sidebar: Perfil e Seletor de Modo
    st.sidebar.title(f"👤 {st.session_state.get('nome_aluno', 'Aluno')}")
    modo_estudo = st.sidebar.radio("Escolha o Modo:", ["🎯 Banco Geral (Filtros)", "📄 Provas Antigas"])
    
    if st.sidebar.button("Sair"):
        st.session_state['usuario_ativo'] = None
        st.rerun()
    st.sidebar.divider()

    df_questoes = carregar_dados("DB_QUESTOES")
    
    if df_questoes.empty:
        st.error("Erro: A aba 'DB_QUESTOES' não foi encontrada.")
    else:
        # --- MODO 1: BANCO GERAL (FILTROS) ---
        if "Banco" in modo_estudo:
            st.sidebar.header("🔍 Filtros")
            
            # Botão de Lógica E/OU
            logica = st.sidebar.radio("Rigidez:", ["Rigorosa (E)", "Flexível (OU)"])
            operador = "and" if "Rigorosa" in logica else "or"
            
            # Filtros Dinâmicos
            opt_materia = sorted(df_questoes['materia'].unique()) if 'materia' in df_questoes.columns else []
            opt_dif = sorted(df_questoes['dificuldade'].unique()) if 'dificuldade' in df_questoes.columns else []
            opt_ano = sorted(df_questoes['ano'].astype(str).unique()) if 'ano' in df_questoes.columns else []
            
            sel_materia = st.sidebar.multiselect("Matéria:", opt_materia)
            sel_dif = st.sidebar.multiselect("Dificuldade:", opt_dif)
            sel_ano = st.sidebar.multiselect("Origem/Ano:", opt_ano) # Opcional aqui
            
            # Construção da Query
            queries = []
            if sel_materia: queries.append("materia in @sel_materia")
            if sel_dif: queries.append("dificuldade in @sel_dif")
            if sel_ano: queries.append("ano in @sel_ano")
            
            df_filtrado = df_questoes.copy()
            if queries:
                query_final = f" {operador} ".join(queries)
                try:
                    df_filtrado = df_questoes.query(query_final)
                except:
                    st.warning("Erro no filtro.")
            elif operador == "or" and (sel_materia or sel_dif or sel_ano):
                 pass # Se for OU e falhar, mantém vazio ou trata conforme regra

            st.title(f"🎯 Banco de Questões ({len(df_filtrado)})")

        # --- MODO 2: PROVAS ANTIGAS (INTEGRAL) ---
        else:
            st.sidebar.header("📂 Seleção de Prova")
            
            # Filtro Único: Ano/Edição
            opt_ano = sorted(df_questoes['ano'].astype(str).unique()) if 'ano' in df_questoes.columns else []
            prova_selecionada = st.sidebar.selectbox("Selecione a Edição:", opt_ano, index=None, placeholder="Escolha um ano...")
            
            if prova_selecionada:
                # Filtra EXATAMENTE aquele ano e ordena por número da questão
                df_filtrado = df_questoes[df_questoes['ano'].astype(str) == str(prova_selecionada)]
                
                if 'numero_questao' in df_filtrado.columns:
                    df_filtrado = df_filtrado.sort_values(by='numero_questao')
                
                st.title(f"📄 Prova: {prova_selecionada}")
            else:
                df_filtrado = pd.DataFrame() # Não mostra nada até escolher
                st.info("👈 Selecione uma prova no menu lateral para começar.")

        # --- RENDERIZADOR UNIVERSAL DE QUESTÕES ---
        if not df_filtrado.empty:
            for index, row in df_filtrado.iterrows():
                with st.container(border=True):
                    # Cabeçalho da Questão
                    ano_txt = row.get('ano', '-')
                    num_txt = f"Q.{row['numero_questao']}" if 'numero_questao' in row else ""
                    st.caption(f"🆔 {num_txt} | 📂 {row['materia']} | 📅 {ano_txt}")
                    
                    st.markdown(f"**{row['enunciado']}**")
                    
                    opcoes = {
                        f"A) {row['alternativa_a']}": 'a',
                        f"B) {row['alternativa_b']}": 'b',
                        f"C) {row['alternativa_c']}": 'c',
                        f"D) {row['alternativa_d']}": 'd'
                    }
                    
                    key_q = f"q_{row['id']}"
                    resposta = st.radio("Sua resposta:", list(opcoes.keys()), key=key_q, index=None, label_visibility="collapsed")
                    
                    if st.button("Verificar", key=f"btn_{row['id']}"):
                        if resposta:
                            letra = opcoes[resposta]
                            if letra.lower() == str(row['gabarito']).lower():
                                st.success("✅ Correto!")
                            else:
                                st.error(f"❌ Errado. Gabarito: {str(row['gabarito']).upper()}")
                                st.caption(f"💡 {row['comentario']}")
        elif "Banco" in modo_estudo and not df_filtrado.empty: 
            # Caso especial para evitar mostrar vazio sem querer
            pass 
        elif "Banco" in modo_estudo and len(queries) > 0:
            st.warning("Nenhuma questão encontrada com esses filtros.")
