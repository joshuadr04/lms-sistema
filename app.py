import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials

# --- 1. CONFIGURAÇÃO E ESTILO ---
st.set_page_config(layout="wide", page_title="LMS - Sistema de Ensino")

# CSS: Remove menus do Streamlit e estiliza o Login
st.markdown("""
    <style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    .block-container {
        padding-top: 1rem;
        padding-bottom: 2rem;
    }
    /* Estilo do Box de Login */
    .login-box {
        padding: 20px;
        border-radius: 10px;
        background-color: #f0f2f6;
        text-align: center;
        margin-bottom: 20px;
    }
    </style>
    """, unsafe_allow_html=True)

# --- 2. CONEXÃO COM GOOGLE SHEETS ---
def conectar_banco():
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    
    # Tenta conectar via Secrets (Nuvem) ou Arquivo Local (PC)
    if "gcp_service_account" in st.secrets:
        creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scopes)
    else:
        creds = Credentials.from_service_account_file("credentials.json", scopes=scopes)
        
    client = gspread.authorize(creds)
    return client.open("LMS_Database")

# Cache para não ficar lendo a planilha toda hora (Performance)
@st.cache_data(ttl=60)
def carregar_dados(aba_nome):
    try:
        sheet = conectar_banco()
        worksheet = sheet.worksheet(aba_nome)
        dados = worksheet.get_all_records()
        return pd.DataFrame(dados)
    except Exception as e:
        # Retorna vazio se a aba não existir ou der erro
        return pd.DataFrame()

# --- 3. CONTROLE DE SESSÃO (LOGIN) ---
if 'usuario_ativo' not in st.session_state:
    st.session_state['usuario_ativo'] = None

# ==================================================
# 🔐 TELA DE LOGIN (HÍBRIDA: SIMPLES ou SEGURA)
# ==================================================
if not st.session_state['usuario_ativo']:
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("<div class='login-box'><h2>🎓 Portal do Aluno</h2></div>", unsafe_allow_html=True)
        
        # Input da Matrícula
        matricula_input = st.text_input("Digite sua Matrícula:", placeholder="Ex: 202401")
        
        # Variável de controle para pedir senha
        if 'pedir_senha' not in st.session_state:
            st.session_state['pedir_senha'] = False

        if st.button("Continuar / Entrar", use_container_width=True):
            df_alunos = carregar_dados("DB_ALUNOS")
            
            # Se não tiver DB_ALUNOS, libera geral (Modo Teste)
            if df_alunos.empty:
                st.session_state['usuario_ativo'] = matricula_input
                st.session_state['nome_aluno'] = "Aluno Teste"
                st.rerun()

            # Busca aluno (converte pra string pra não dar erro de numero vs texto)
            aluno = df_alunos[df_alunos['matricula'].astype(str) == str(matricula_input)]
            
            if not aluno.empty:
                dados = aluno.iloc[0]
                senha_registrada = str(dados.get('senha', '')).strip()
                
                # CENÁRIO A: Sem senha (Entra direto)
                if senha_registrada == "":
                    st.session_state['usuario_ativo'] = matricula_input
                    st.session_state['nome_aluno'] = dados['nome']
                    st.success(f"Bem-vindo(a), {dados['nome']}!")
                    st.rerun()
                
                # CENÁRIO B: Com senha (Pede senha)
                else:
                    st.session_state['pedir_senha'] = True
                    st.session_state['temp_matricula'] = matricula_input
                    st.session_state['temp_nome'] = dados['nome']
                    st.session_state['temp_senha_real'] = senha_registrada
                    st.rerun()
            else:
                st.error("Matrícula não encontrada.")

        # Campo de Senha (só aparece se necessário)
        if st.session_state['pedir_senha']:
            st.info(f"Olá, {st.session_state['temp_nome']}. Digite sua senha.")
            senha_input = st.text_input("Senha:", type="password")
            
            if st.button("Confirmar Senha", type="primary"):
                if str(senha_input) == str(st.session_state['temp_senha_real']):
                    st.session_state['usuario_ativo'] = st.session_state['temp_matricula']
                    st.session_state['nome_aluno'] = st.session_state['temp_nome']
                    del st.session_state['pedir_senha'] # Limpa memória
                    st.rerun()
                else:
                    st.error("Senha incorreta.")

# ==================================================
# 🚀 ÁREA LOGADA (SISTEMA PRINCIPAL)
# ==================================================
else:
    # Verifica se veio LINK DE LISTA (Notion) ou acesso direto
    param_lista = st.query_params.get("lista", None)

    # --- MODO 1: LISTA RÁPIDA (Embed no Notion) ---
    if param_lista:
        st.subheader(f"📝 Lista de Aula: {param_lista}")
        
        # Carrega da aba específica de Listas
        df_listas = carregar_dados("DB_LISTAS")
        
        if not df_listas.empty:
            # Filtra pela coluna 'nome_lista' (Ex: topico_cinematica)
            questoes_lista = df_listas[df_listas['nome_lista'] == param_lista]
            
            if questoes_lista.empty:
                st.warning(f"Nenhuma questão encontrada para a lista: {param_lista}")
            else:
                # Mostra as questões corridas
                for index, row in questoes_lista.iterrows():
                    with st.container(border=True):
                        st.markdown(f"**{row['enunciado']}**")
                        
                        opcoes = {
                            f"A) {row['alternativa_a']}": 'a',
                            f"B) {row['alternativa_b']}": 'b',
                            f"C) {row['alternativa_c']}": 'c',
                            f"D) {row['alternativa_d']}": 'd'
                        }
                        
                        # Chave única para não misturar os radios
                        key_q = f"lista_{row['id']}"
                        resposta = st.radio("Sua resposta:", list(opcoes.keys()), key=key_q, index=None, label_visibility="collapsed")
                        
                        if st.button("Corrigir", key=f"btn_lista_{row['id']}"):
                            if resposta:
                                letra = opcoes[resposta]
                                if letra.lower() == str(row['gabarito']).lower():
                                    st.success("✅ Correto!")
                                    # FUTURO: Salvar +1 ponto na habilidade X
                                else:
                                    st.error(f"❌ Incorreto. Gabarito: {str(row['gabarito']).upper()}")
                                    st.caption(f"💡 {row['comentario']}")
                                    # FUTURO: Salvar -1 ponto na habilidade X
        else:
            st.error("Erro: A aba 'DB_LISTAS' não foi encontrada na planilha.")

    # --- MODO 2: SUPER BANCO DE QUESTÕES (Estudo Geral) ---
    else:
        st.sidebar.title(f"👤 {st.session_state.get('nome_aluno', 'Aluno')}")
        if st.sidebar.button("Sair"):
            st.session_state['usuario_ativo'] = None
            st.rerun()
            
        st.sidebar.divider()
        st.sidebar.header("🔍 Filtros de Estudo")
        
        df_questoes = carregar_dados("DB_QUESTOES")
        
        if not df_questoes.empty:
            # Filtros
            modo_filtro = st.sidebar.radio("Lógica do Filtro:", ["Rigorosa (E)", "Flexível (OU)"])
            operador = "and" if "Rigorosa" in modo_filtro else "or"
            
            # Pega opções únicas das colunas se elas existirem
            opt_materia = sorted(df_questoes['materia'].unique()) if 'materia' in df_questoes.columns else []
            opt_ano = sorted(df_questoes['ano'].astype(str).unique()) if 'ano' in df_questoes.columns else []
            opt_dif = sorted(df_questoes['dificuldade'].unique()) if 'dificuldade' in df_questoes.columns else []
            
            sel_materia = st.sidebar.multiselect("Matéria:", opt_materia)
            sel_ano = st.sidebar.multiselect("Ano / Origem:", opt_ano)
            sel_dif = st.sidebar.multiselect("Dificuldade:", opt_dif)
            
            # Lógica de Filtragem
            df_filtrado = df_questoes.copy()
            queries = []
            
            if sel_materia: queries.append("materia in @sel_materia")
            if sel_ano: queries.append("ano in @sel_ano") # Aqui filtra Provas Antigas
            if sel_dif: queries.append("dificuldade in @sel_dif")
            
            if queries:
                query_final = f" {operador} ".join(queries)
                try:
                    df_filtrado = df_questoes.query(query_final)
                except:
                    st.warning("Erro na filtragem.")
            
            # Ordenação (Ano -> Numero da Questão)
            if 'numero_questao' in df_filtrado.columns:
                df_filtrado = df_filtrado.sort_values(by=['ano', 'numero_questao'])

            # Área Principal
            st.title(f"📚 Banco Geral ({len(df_filtrado)} questões)")
            
            if len(df_filtrado) == 0:
                st.info("Nenhuma questão encontrada com esses filtros.")
            
            for index, row in df_filtrado.iterrows():
                with st.container(border=True):
                    # Tags Visuais
                    ano_txt = row.get('ano', '')
                    dif_txt = row.get('dificuldade', '')
                    st.caption(f"📂 {row['materia']} | 📅 {ano_txt} | ⚡ {dif_txt}")
                    
                    st.markdown(f"**{row['enunciado']}**")
                    
                    opcoes = {
                        f"A) {row['alternativa_a']}": 'a',
                        f"B) {row['alternativa_b']}": 'b',
                        f"C) {row['alternativa_c']}": 'c',
                        f"D) {row['alternativa_d']}": 'd'
                    }
                    
                    key_q = f"banco_{row['id']}"
                    resposta = st.radio("Resposta:", list(opcoes.keys()), key=key_q, index=None, label_visibility="collapsed")
                    
                    if st.button("Verificar", key=f"btn_banco_{row['id']}"):
                        if resposta:
                            letra = opcoes[resposta]
                            if letra.lower() == str(row['gabarito']).lower():
                                st.success("✅ Correto!")
                            else:
                                st.error(f"❌ Errado. Gabarito: {str(row['gabarito']).upper()}")
                                st.caption(f"💡 {row['comentario']}")
        else:
            st.error("A aba 'DB_QUESTOES' não foi encontrada.")
