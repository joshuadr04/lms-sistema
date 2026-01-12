import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import time
from datetime import datetime
import google.generativeai as genai

# ==================================================
# 1. CONFIGURAÇÃO VISUAL
# ==================================================
st.set_page_config(layout="wide", page_title="LMS - Sistema Inteligente")

st.markdown("""
    <style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    .stDeployButton {display:none;}
    
    .block-container {
        padding-top: 3rem; 
        padding-bottom: 5rem;
    } 
    
    .login-box {
        padding: 20px;
        border-radius: 10px;
        background-color: #1e1e1e;
        text-align: center;
        margin-bottom: 20px;
        border: 1px solid #333;
    }
    </style>
    """, unsafe_allow_html=True)

# ==================================================
# 2. FUNÇÕES DE BANCO DE DADOS
# ==================================================
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
        # Lê tudo como string para evitar bugs de filtro
        df = pd.DataFrame(sheet.worksheet("DB_QUESTOES").get_all_records())
        return df.astype(str) 
    except:
        return pd.DataFrame()

def carregar_alunos_live():
    try:
        sheet = conectar_banco()
        ws = sheet.worksheet("DB_ALUNOS")
        return pd.DataFrame(ws.get_all_records()), ws
    except:
        return pd.DataFrame(), None

def registrar_resposta(dados):
    """Salva a resposta na aba DB_RESPOSTAS"""
    try:
        sheet = conectar_banco()
        try:
            ws = sheet.worksheet("DB_RESPOSTAS")
        except:
            ws = sheet.add_worksheet("DB_RESPOSTAS", 1000, 10)
            ws.append_row(["matricula", "id_questao", "acertou", "tempo", "confianca", "motivo_erro", "data_hora"])
        
        ws.append_row([
            str(dados['matricula']),
            str(dados['id_questao']),
            str(dados['acertou']),
            str(round(dados['tempo'], 2)),
            str(dados['confianca']),
            str(dados['erro'])[:1000],
            str(datetime.now())
        ])
    except Exception as e:
        print(f"Erro ao salvar log: {e}")

def atualizar_preferencia_aluno(matricula, coluna_nome, novo_valor):
    mapa_colunas = {'login_protegido': 4, 'pref_timer': 5, 'pref_confianca': 6, 'pref_autopsia': 7}
    if coluna_nome not in mapa_colunas: return False
    try:
        sheet = conectar_banco()
        ws = sheet.worksheet("DB_ALUNOS")
        cell = ws.find(str(matricula))
        valor_str = "TRUE" if novo_valor else "FALSE"
        ws.update_cell(cell.row, mapa_colunas[coluna_nome], valor_str)
        return True
    except:
        return False

# ==================================================
# 3. CÉREBRO DA IA (GEMINI)
# ==================================================
def corrigir_com_ia(pergunta, gabarito, resposta_aluno, modo_escolhido):
    if "gemini" in st.secrets:
        genai.configure(api_key=st.secrets["gemini"]["api_key"])
    else:
        return "Erro: Chave [gemini] não configurada nos Secrets."

    instrucao_sistema = ""
    if modo_escolhido == "Banca":
        instrucao_sistema = """Atue como um CORRETOR DE BANCA RIGOROSO (Estilo ENEM). Dê uma nota 0-100, um veredito (Correto/Parcial/Incorreto) e aponte falhas objetivas comparando com o gabarito. Seja conciso."""
    elif modo_escolhido == "Professor":
        instrucao_sistema = """Atue como um PROFESSOR DIDÁTICO. Aponte acertos primeiro. Explique o erro conceitual com paciência. Dê uma mini-aula de 2 frases sobre o tema correto."""
    elif modo_escolhido == "Socrático":
        instrucao_sistema = """Atue como um MENTOR SOCRÁTICO. NUNCA dê a resposta. Faça uma pergunta desafiadora ou dê uma analogia que leve o aluno a perceber o próprio erro."""

    modelo = genai.GenerativeModel(
        model_name='models/gemini-flash-latest', 
        system_instruction=instrucao_sistema
    )
    
    prompt = f"PERGUNTA: {pergunta}\nGABARITO/GUIA: {gabarito}\nRESPOSTA ALUNO: {resposta_aluno}"

    try:
        response = modelo.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"Erro na IA: {str(e)}"

# ==================================================
# 4. CONTROLE DE SESSÃO E LOGIN
# ==================================================
if 'usuario_ativo' not in st.session_state:
    st.session_state['usuario_ativo'] = None
if 'timers' not in st.session_state:
    st.session_state['timers'] = {}

# --- TELA DE LOGIN ---
if not st.session_state['usuario_ativo']:
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("<div class='login-box'><h2>🎓 Portal do Aluno</h2></div>", unsafe_allow_html=True)
        with st.form("login_form"):
            matricula_input = st.text_input("Matrícula:", placeholder="Ex: 202401")
            senha_input = st.text_input("Senha:", type="password")
            if st.form_submit_button("Entrar", use_container_width=True):
                df_alunos, _ = carregar_alunos_live()
                aluno = df_alunos[df_alunos['matricula'].astype(str) == str(matricula_input)]
                
                if not aluno.empty:
                    dados = aluno.iloc[0]
                    protegido = str(dados.get('login_protegido', 'FALSE')).upper() == 'TRUE'
                    senha_real = str(dados.get('senha', '')).strip()
                    
                    st.session_state['prefs'] = {
                        'timer': str(dados.get('pref_timer', 'FALSE')).upper() == 'TRUE',
                        'confianca': str(dados.get('pref_confianca', 'FALSE')).upper() == 'TRUE',
                        'autopsia': str(dados.get('pref_autopsia', 'FALSE')).upper() == 'TRUE'
                    }

                    if protegido and str(senha_input) != senha_real:
                        st.error("🔒 Senha incorreta.")
                    else:
                        st.session_state['usuario_ativo'] = matricula_input
                        st.session_state['nome_aluno'] = dados['nome']
                        st.rerun()
                else:
                    st.error("Matrícula não encontrada.")

# ==================================================
# 5. ÁREA LOGADA (MAIN APP)
# ==================================================
else:
    # --- BARRA LATERAL (SIDEBAR) ---
    with st.sidebar:
        st.title(f"👤 {st.session_state.get('nome_aluno', 'Aluno')}")
        with st.expander("⚙️ Preferências"):
            df_alunos, _ = carregar_alunos_live()
            dados = df_alunos[df_alunos['matricula'].astype(str) == str(st.session_state['usuario_ativo'])].iloc[0]
            
            p_timer = st.toggle("⏱️ Cronômetro", value=str(dados['pref_timer']).upper()=='TRUE')
            p_conf = st.toggle("🤔 Confiança", value=str(dados['pref_confianca']).upper()=='TRUE')
            p_auto = st.toggle("🔎 Autópsia Erro", value=str(dados['pref_autopsia']).upper()=='TRUE')
            
            if p_timer != st.session_state['prefs']['timer']:
                atualizar_preferencia_aluno(st.session_state['usuario_ativo'], 'pref_timer', p_timer)
                st.session_state['prefs']['timer'] = p_timer
                st.rerun()
            if p_conf != st.session_state['prefs']['confianca']:
                 atualizar_preferencia_aluno(st.session_state['usuario_ativo'], 'pref_confianca', p_conf)
                 st.session_state['prefs']['confianca'] = p_conf
                 st.rerun()
            if p_auto != st.session_state['prefs']['autopsia']:
                 atualizar_preferencia_aluno(st.session_state['usuario_ativo'], 'pref_autopsia', p_auto)
                 st.session_state['prefs']['autopsia'] = p_auto
                 st.rerun()

        st.divider()
        modo_estudo = st.sidebar.radio("Menu:", ["🎯 Banco de Questões", "📄 Provas Antigas"])
        
        if st.sidebar.button("Sair"):
            st.session_state['usuario_ativo'] = None
            st.rerun()

    # --- CONTEÚDO PRINCIPAL ---
    df_questoes = carregar_questoes()
    
    if df_questoes.empty:
        st.error("⚠️ Base de questões vazia ou erro de conexão.")
    else:
        df_filtrado = pd.DataFrame()
        
        # --- LÓGICA DE FILTROS (AMAZON STYLE) ---
        if "Banco" in modo_estudo:
            st.header("🎯 Banco Geral")
            st.caption("Filtre as questões por características:")
            
            # Prepara listas de opções (Sorted & Unique)
            opt_mat = sorted(df_questoes['materia'].unique())
            opt_dif = sorted(df_questoes['dificuldade'].unique())
            opt_top = sorted(df_questoes['topico_macro'].unique())
            opt_ano = sorted(df_questoes['ano'].unique()) # Continua lendo 'ano' do DB
            opt_tipo = sorted(df_questoes['tipo_input'].unique())

            # Painel de Filtros
            sel_mat = st.multiselect("📚 Matéria:", opt_mat, placeholder="Todas")
            
            with st.expander("🌪️ Mais Filtros (Dificuldade, Fonte, Tipo...)", expanded=False):
                c_f1, c_f2 = st.columns(2)
                with c_f1:
                    sel_dif = st.multiselect("🔥 Dificuldade:", opt_dif)
                    sel_tipo = st.multiselect("📝 Tipo:", opt_tipo)
                with c_f2:
                    # MUDANÇA AQUI: Label visual alterado para Fonte/Origem
                    sel_ano = st.multiselect("🏛️ Fonte/Origem:", opt_ano)
                    sel_top = st.multiselect("📌 Tópico:", opt_top)

            # Aplicação dos Filtros (Cascata)
            df_filtrado = df_questoes.copy()
            
            if sel_mat: df_filtrado = df_filtrado[df_filtrado['materia'].isin(sel_mat)]
            if sel_dif: df_filtrado = df_filtrado[df_filtrado['dificuldade'].isin(sel_dif)]
            if sel_ano: df_filtrado = df_filtrado[df_filtrado['ano'].isin(sel_ano)]
            if sel_top: df_filtrado = df_filtrado[df_filtrado['topico_macro'].isin(sel_top)]
            if sel_tipo: df_filtrado = df_filtrado[df_filtrado['tipo_input'].isin(sel_tipo)]
            
            if len(df_filtrado) > 0:
                st.success(f"🔍 **{len(df_filtrado)}** questões encontradas.")
            else:
                st.warning("Nenhuma questão com esses filtros.")

        else:
            # Modo Provas Antigas (Simplificado)
            st.header("📄 Provas Antigas")
            opt_ano = sorted(df_questoes['ano'].unique())
            # MUDANÇA AQUI: Label visual alterado
            prova_sel = st.selectbox("Selecione a Fonte/Origem:", opt_ano, index=None)
            if prova_sel:
                df_filtrado = df_questoes[df_questoes['ano'] == prova_sel].sort_values(by='numero_questao')

        # --- LOOP DE EXIBIÇÃO DAS QUESTÕES ---
        for index, row in df_filtrado.iterrows():
            q_id = str(row['id'])
            if q_id not in st.session_state['timers']: 
                st.session_state['timers'][q_id] = time.time()
            
            with st.container(border=True):
                # Cabeçalho da Questão
                c1, c2 = st.columns([4, 1])
                # MUDANÇA AQUI: Ícone e formatação visual
                c1.markdown(f"**Questão {row.get('numero_questao','?')}** | {row['materia']}")
                c1.caption(f"🆔 {q_id} | 🏛️ {row['ano']} | 🔥 {row['dificuldade']}")
                
                if st.session_state['prefs']['timer']:
                    tempo = int(time.time() - st.session_state['timers'][q_id])
                    c2.markdown(f"⏱️ **{tempo}s**")
                
                # Enunciado
                st.markdown(f"### {row['enunciado']}")
                
                # LÓGICA DE INPUT
                tipo_input = str(row.get('tipo_input', 'Multipla')).strip().lower()
                
                if tipo_input == 'discursiva':
                    # --- MODO ABERTO (IA) ---
                    txt_resp = st.text_area("Sua Resposta:", key=f"txt_{q_id}", height=150)
                    st.caption("🤖 Solicitar Correção IA:")
                    b1, b2, b3 = st.columns(3)
                    
                    modo = None
                    if b1.button("👮 Banca", key=f"b_{q_id}"): modo = "Banca"
                    if b2.button("🧑‍🏫 Prof", key=f"p_{q_id}"): modo = "Professor"
                    if b3.button("🤔 Socrático", key=f"s_{q_id}"): modo = "Socrático"
                    
                    if modo:
                        if not txt_resp: 
                            st.warning("⚠️ Escreva uma resposta antes de corrigir.")
                        else:
                            with st.spinner(f"A IA está analisando no modo {modo}..."):
                                feedback = corrigir_com_ia(row['enunciado'], row['gabarito'], txt_resp, modo)
                                
                                st.markdown("---")
                                st.markdown(f"**📝 Feedback ({modo}):**")
                                if modo == "Banca": st.info(feedback)
                                elif modo == "Socrático": st.warning(feedback)
                                else: st.success(feedback)
                                
                                registrar_resposta({
                                    'matricula': st.session_state['usuario_ativo'],
                                    'id_questao': q_id,
                                    'acertou': "IA-Check",
                                    'tempo': time.time() - st.session_state['timers'][q_id],
                                    'confianca': f"IA-{modo}",
                                    'erro': "Feedback IA Salvo"
                                })

                else:
                    # --- MODO MÚLTIPLA ESCOLHA ---
                    opcoes = {
                        f"A) {row['alternativa_a']}": 'a',
                        f"B) {row['alternativa_b']}": 'b',
                        f"C) {row['alternativa_c']}": 'c',
                        f"D) {row['alternativa_d']}": 'd'
                    }
                    resp = st.radio("Selecione:", list(opcoes.keys()), key=f"r_{q_id}", index=None)
                    
                    acao = False
                    conf = "N/A"
                    
                    if st.session_state['prefs']['confianca']:
                        st.write("---")
                        st.caption("Responder com nível de confiança:")
                        bc1, bc2, bc3 = st.columns(3)
                        if bc1.button("🔴 Chute", key=f"c1_{q_id}", use_container_width=True): acao, conf = True, "Baixa"
                        if bc2.button("🟡 Dúvida", key=f"c2_{q_id}", use_container_width=True): acao, conf = True, "Média"
                        if bc3.button("🟢 Certeza", key=f"c3_{q_id}", use_container_width=True): acao, conf = True, "Alta"
                    else:
                        st.write("---")
                        if st.button("Responder", key=f"btn_{q_id}"): acao = True
                    
                    if acao:
                        if not resp:
                            st.warning("Selecione uma alternativa!")
                        else:
                            tempo_final = time.time() - st.session_state['timers'][q_id]
                            letra_escolhida = opcoes[resp]
                            gabarito_oficial = str(row['gabarito']).lower().strip()
                            acertou = letra_escolhida == gabarito_oficial
                            
                            if acertou:
                                st.success(f"✅ Correto! ({letra_escolhida.upper()})")
                                if row.get('comentario'): st.info(f"💡 {row['comentario']}")
                                registrar_resposta({
                                    'matricula': st.session_state['usuario_ativo'],
                                    'id_questao': q_id,
                                    'acertou': True,
                                    'tempo': tempo_final,
                                    'confianca': conf,
                                    'erro': 'N/A'
                                })
                                st.session_state['timers'][q_id] = time.time()
                            else:
                                st.error(f"❌ Errado. A resposta certa era {gabarito_oficial.upper()}")
                                if st.session_state['prefs']['autopsia']:
                                    st.session_state[f"erro_{q_id}"] = {'t': tempo_final, 'c': conf}
                                else:
                                    registrar_resposta({
                                        'matricula': st.session_state['usuario_ativo'],
                                        'id_questao': q_id,
                                        'acertou': False,
                                        'tempo': tempo_final,
                                        'confianca': conf,
                                        'erro': 'Não classificado'
                                    })
                                    st.session_state['timers'][q_id] = time.time()

                    if f"erro_{q_id}" in st.session_state:
                        st.warning("🔎 Autópsia: Por que você errou?")
                        c1, c2, c3, c4 = st.columns(4)
                        motivo = None
                        if c1.button("🧠 Lacuna", key=f"m1_{q_id}"): motivo = "Lacuna Conceitual"
                        if c2.button("👀 Atenção", key=f"m2_{q_id}"): motivo = "Falta de Atenção"
                        if c3.button("📖 Interp.", key=f"m3_{q_id}"): motivo = "Erro de Interpretação"
                        if c4.button("🤡 Pegadinha", key=f"m4_{q_id}"): motivo = "Distrator/Pegadinha"
                        
                        if motivo:
                            d = st.session_state[f"erro_{q_id}"]
                            registrar_resposta({
                                'matricula': st.session_state['usuario_ativo'],
                                'id_questao': q_id,
                                'acertou': False,
                                'tempo': d['t'],
                                'confianca': d['c'],
                                'erro': motivo
                            })
                            del st.session_state[f"erro_{q_id}"]
                            st.success("Motivo registrado.")
                            time.sleep(1)
                            st.rerun()

st.markdown("<div style='height: 100px;'></div>", unsafe_allow_html=True)
