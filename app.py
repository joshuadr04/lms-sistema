import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials

# --- 1. CONFIGURAÇÃO VISUAL ---
st.set_page_config(layout="wide", page_title="LMS - Sistema Escolar")

st.markdown("""
    <style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    /* header {visibility: hidden;} <--- COMENTADO PARA O MENU LATERAL VOLTAR A APARECER */
    
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
def carregar_questoes():
    try:
        sheet = conectar_banco()
        return pd.DataFrame(sheet.worksheet("DB_QUESTOES").get_all_records())
    except:
        return pd.DataFrame()

def carregar_alunos_live():
    try:
        sheet = conectar_banco()
        ws = sheet.worksheet("DB_ALUNOS")
        return pd.DataFrame(ws.get_all_records()), ws
    except:
        return pd.DataFrame(), None

def atualizar_preferencia_senha(matricula, ativar_protecao):
    try:
        sheet = conectar_banco()
        ws = sheet.worksheet("DB_ALUNOS")
        cell = ws.find(str(matricula))
        # Ajuste a coluna se necessário (4 = coluna D 'login_protegido')
        valor_para_salvar = "TRUE" if ativar_protecao else "FALSE"
        ws.update_cell(cell.row, 4, valor_para_salvar)
        st.toast(f"Preferência salva: {valor_para_salvar}")
        return True
    except Exception as e:
        st.error(f"Erro ao salvar: {e}")
        return False

# --- 3. CONTROLE DE SESSÃO ---
if 'usuario_ativo' not in st.session_state:
    st.session_state['usuario_ativo'] = None

# ==================================================
# 🔐 TELA DE LOGIN (UNIFICADA E LIMPA)
# ==================================================
if not st.session_state['usuario_ativo']:
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("<div class='login-box'><h2>🎓 Portal do Aluno</h2></div>", unsafe_allow_html=True)
        
        # Formulário Único
        with st.form("login_form"):
            matricula_input = st.text_input("Matrícula:", placeholder="Ex: 202401")
            senha_input = st.text_input("Senha:", type="password", placeholder="(Opcional se seu login for livre)")
            
            # Botão Único
            submitted = st.form_submit_button("Entrar", use_container_width=True)
            
            if submitted:
                df_alunos, _ = carregar_alunos_live()
                
                # Modo Teste (Sem planilha)
                if df_alunos.empty:
                    st.session_state['usuario_ativo'] = matricula_input
                    st.session_state['nome_aluno'] = "Aluno Teste"
                    st.rerun()

                # Busca Aluno
                aluno = df_alunos[df_alunos['matricula'].astype(str) == str(matricula_input)]
                
                if not aluno.empty:
                    dados = aluno.iloc[0]
                    protegido = str(dados.get('login_protegido', 'FALSE')).upper() == 'TRUE'
                    senha_real = str(dados.get('senha', '')).strip()
                    
                    # LÓGICA DE VALIDAÇÃO
                    if protegido:
                        # Se for protegido, OBRIGA a senha estar certa
                        if str(senha_input) == senha_real:
                            st.session_state['usuario_ativo'] = matricula_input
                            st.session_state['nome_aluno'] = dados['nome']
                            st.success("Login autorizado!")
                            st.rerun()
                        else:
                            st.error("🔒 Este perfil é protegido. Senha incorreta.")
                    else:
                        # Se NÃO for protegido, ignora o campo de senha e entra
                        st.session_state['usuario_ativo'] = matricula_input
                        st.session_state['nome_aluno'] = dados['nome']
                        st.rerun()
                else:
                    st.error("❌ Matrícula não encontrada.")

# ==================================================
# 🚀 ÁREA LOGADA
# ==================================================
else:
    # --- BARRA LATERAL ---
    with st.sidebar:
        st.title(f"👤 {st.session_state.get('nome_aluno', 'Aluno')}")
        
        # Configuração de Segurança
        with st.expander("⚙️ Segurança"):
            df_alunos, _ = carregar_alunos_live()
            try:
                dados_atuais = df_alunos[df_alunos['matricula'].astype(str) == str(st.session_state['usuario_ativo'])].iloc[0]
                estado_atual = str(dados_atuais.get('login_protegido', 'FALSE')).upper() == 'TRUE'
            except:
                estado_atual = False
            
            novo_estado = st.toggle("Exigir Senha no Login", value=estado_atual)
            if novo_estado != estado_atual:
                atualizar_preferencia_senha(st.session_state['usuario_ativo'], novo_estado)
                st.rerun()
        
        st.divider()
        modo_estudo = st.sidebar.radio("Menu:", ["🎯 Banco de Questões", "📄 Provas Antigas"])
        
        if st.sidebar.button("Sair"):
            st.session_state['usuario_ativo'] = None
            st.rerun()

    # --- CORPO DO APP ---
    df_questoes = carregar_questoes()
    
    if df_questoes.empty:
        st.error("Erro ao carregar banco de questões.")
    else:
        if "Banco" in modo_estudo:
            st.header("🎯 Banco Geral")
            col_f1, col_f2 = st.columns(2)
            with col_f1:
                logica = st.radio("Filtro:", ["Rigoroso (E)", "Flexível (OU)"], horizontal=True)
            operador = "and" if "Rigoroso" in logica else "or"
            
            opt_materia = sorted(df_questoes['materia'].unique()) if 'materia' in df_questoes.columns else []
            opt_dif = sorted(df_questoes['dificuldade'].unique()) if 'dificuldade' in df_questoes.columns else []
            
            sel_materia = st.multiselect("Matéria:", opt_materia)
            sel_dif = st.multiselect("Dificuldade:", opt_dif)
            
            queries = []
            if sel_materia: queries.append("materia in @sel_materia")
            if sel_dif: queries.append("dificuldade in @sel_dif")
            
            df_filtrado = df_questoes.copy()
            if queries:
                query_final = f" {operador} ".join(queries)
                try: df_filtrado = df_questoes.query(query_final)
                except: pass
            elif operador == "or" and (sel_materia or sel_dif): pass

            st.caption(f"Encontradas: {len(df_filtrado)}")
            
        else:
            st.header("📄 Provas Antigas")
            opt_ano = sorted(df_questoes['ano'].astype(str).unique()) if 'ano' in df_questoes.columns else []
            prova_selecionada = st.selectbox("Selecione a Edição:", opt_ano, index=None)
            
            if prova_selecionada:
                df_filtrado = df_questoes[df_questoes['ano'].astype(str) == str(prova_selecionada)]
                if 'numero_questao' in df_filtrado.columns:
                    df_filtrado = df_filtrado.sort_values(by='numero_questao')
            else:
                df_filtrado = pd.DataFrame()

        for index, row in df_filtrado.iterrows():
            with st.container(border=True):
                st.markdown(f"**{row['enunciado']}**")
                opcoes = {f"A) {row['alternativa_a']}": 'a', f"B) {row['alternativa_b']}": 'b', 
                          f"C) {row['alternativa_c']}": 'c', f"D) {row['alternativa_d']}": 'd'}
                key_q = f"q_{row['id']}"
                resposta = st.radio("Resposta:", list(opcoes.keys()), key=key_q, index=None, label_visibility="collapsed")
                
                if st.button("Verificar", key=f"btn_{row['id']}"):
                    if resposta:
                        if opcoes[resposta].lower() == str(row['gabarito']).lower():
                            st.success("✅ Correto!")
                        else:
                            st.error(f"❌ Errado. Gabarito: {str(row['gabarito']).upper()}")
