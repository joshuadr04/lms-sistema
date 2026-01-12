import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import time
from datetime import datetime
import google.generativeai as genai
import re

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
            ws.append_row(["matricula", "id_questao", "acertou", "tempo", "confianca", "motivo_erro", "data_hora", "nota_percentual"])
        
        tempo_valor = str(round(dados['tempo'], 2)) if dados['tempo'] is not None else ""
        nota_valor = int(dados.get('nota_percentual', 0))

        ws.append_row([
            str(dados['matricula']),
            str(dados['id_questao']),
            str(dados['acertou']),
            tempo_valor,
            str(dados['confianca']),
            str(dados['erro'])[:1000],
            str(datetime.now()),
            nota_valor
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
        return "Erro: Chave [gemini] não configurada.", 0

    base_instruction = """
    IMPORTANTE: No final da sua resposta, você DEVE incluir a nota percentual (0 a 100) da resposta do aluno.
    Use estritamente este formato no final: [[NOTA:XX]]
    Exemplo: "Sua explicação foi boa... [[NOTA:85]]"
    """

    instrucao_sistema = ""
    if modo_escolhido == "Banca":
        instrucao_sistema = base_instruction + """Atue como CORRETOR DE BANCA RIGOROSO. Dê nota, veredito e aponte falhas."""
    elif modo_escolhido == "Professor":
        instrucao_sistema = base_instruction + """Atue como PROFESSOR DIDÁTICO. Aponte acertos, explique o erro e dê uma mini-aula."""
    elif modo_escolhido == "Socrático":
        instrucao_sistema = base_instruction + """Atue como MENTOR SOCRÁTICO. Não dê a resposta, faça perguntas. Dê uma nota provisória."""

    modelo = genai.GenerativeModel(
        model_name='models/gemini-flash-latest', 
        system_instruction=instrucao_sistema
    )
    
    prompt = f"PERGUNTA: {pergunta}\nGABARITO/GUIA: {gabarito}\nRESPOSTA ALUNO: {resposta_aluno}"

    try:
        response = modelo.generate_content(prompt)
        texto_completo = response.text
        
        match = re.search(r'\[\[NOTA:(\d+)\]\]', texto_completo)
        if match:
            nota = int(match.group(1))
            texto_limpo = texto_completo.replace(match.group(0), "")
        else:
            nota = 0
            texto_limpo = texto_completo
            
        return texto_limpo, nota
    except Exception as e:
        return f"Erro na IA: {str(e)}", 0

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
    if 'modo_estudo_temp' not in st.session_state:
        st.session_state['modo_estudo_temp'] = "🎯 Banco de Questões"

    # --- SIDEBAR ---
    with st.sidebar:
        st.title(f"👤 {st.session_state.get('nome_aluno', 'Aluno')}")
        modo_estudo = st.radio("Menu:", ["🎯 Banco de Questões", "📄 Provas Antigas"])
        
        st.divider()

        with st.expander("⚙️ Preferências", expanded=True):
            df_alunos, _ = carregar_alunos_live()
            dados = df_alunos[df_alunos['matricula'].astype(str) == str(st.session_state['usuario_ativo'])].iloc[0]
            
            if "Banco" not in modo_estudo:
                p_timer = st.toggle("⏱️ Cronômetro", value=str(dados['pref_timer']).upper()=='TRUE')
                if p_timer != st.session_state['prefs']['timer']:
                    atualizar_preferencia_aluno(st.session_state['usuario_ativo'], 'pref_timer', p_timer)
                    st.session_state['prefs']['timer'] = p_timer
                    st.rerun()
            else:
                st.caption("⏱️ Cronômetro desativado no Banco.")
            
            p_conf = st.toggle("🤔 Confiança", value=str(dados['pref_confianca']).upper()=='TRUE')
            if p_conf != st.session_state['prefs']['confianca']:
                 atualizar_preferencia_aluno(st.session_state['usuario_ativo'], 'pref_confianca', p_conf)
                 st.session_state['prefs']['confianca'] = p_conf
                 st.rerun()
            
            p_auto = st.toggle("🔎 Autópsia Erro", value=str(dados['pref_autopsia']).upper()=='TRUE')
            if p_auto != st.session_state['prefs']['autopsia']:
                 atualizar_preferencia_aluno(st.session_state['usuario_ativo'], 'pref_autopsia', p_auto)
                 st.session_state['prefs']['autopsia'] = p_auto
                 st.rerun()

        st.divider()
        if st.sidebar.button("Sair"):
            st.session_state['usuario_ativo'] = None
            st.rerun()

    # --- CONTEÚDO PRINCIPAL ---
    df_questoes = carregar_questoes()
    
    if df_questoes.empty:
        st.error("⚠️ Base de questões vazia ou erro de conexão.")
    else:
        df_filtrado = pd.DataFrame()
        
        # --- LÓGICA DE FILTROS COM CONTROLE MANUAL ---
        if "Banco" in modo_estudo:
            st.header("🎯 Banco Geral")
            
            # 1. CONTROLE MANUAL DE LÓGICA
            c_log, c_inf = st.columns([1, 2])
            with c_log:
                # O BOTÃO VOLTOU!
                logica_filtro = st.radio("Lógica Interna:", ["Flexível (OU)", "Rigoroso (E)"], horizontal=True)
            with c_inf:
                st.caption("Flexível: Mostra itens de qualquer categoria selecionada. Rigoroso: Mostra apenas itens que atendam a TODOS os critérios (Cuidado: pode zerar a busca).")

            # 2. SELEÇÃO DE FILTROS
            opt_mat = sorted(df_questoes['materia'].unique())
            opt_dif = sorted(df_questoes['dificuldade'].unique())
            opt_top = sorted(df_questoes['topico_macro'].unique())
            opt_ano = sorted(df_questoes['ano'].unique())
            opt_tipo = sorted(df_questoes['tipo_input'].unique())

            sel_mat = st.multiselect("📚 Matéria:", opt_mat, placeholder="Todas")
            
            with st.expander("🌪️ Mais Filtros (Dificuldade, Fonte, Tipo...)", expanded=False):
                c_f1, c_f2 = st.columns(2)
                with c_f1:
                    sel_dif = st.multiselect("🔥 Dificuldade:", opt_dif)
                    sel_tipo = st.multiselect("📝 Tipo:", opt_tipo)
                with c_f2:
                    sel_ano = st.multiselect("🏛️ Fonte/Origem:", opt_ano)
                    sel_top = st.multiselect("📌 Tópico:", opt_top)

            # 3. APLICAÇÃO DA LÓGICA MANUAL
            df_filtrado = df_questoes.copy()
            
            # Função auxiliar para aplicar a lógica escolhida
            def aplicar_filtro(df, coluna, selecionados):
                if not selecionados: return df
                if "Rigoroso" in logica_filtro:
                    # Lógica E: Tem que ter TODAS as características (Iterativo)
                    for item in selecionados:
                        df = df[df[coluna] == item]
                    return df
                else:
                    # Lógica OU: Tem que ter PELO MENOS UMA (IsIn)
                    return df[df[coluna].isin(selecionados)]

            # Aplica em cascata
            df_filtrado = aplicar_filtro(df_filtrado, 'materia', sel_mat)
            df_filtrado = aplicar_filtro(df_filtrado, 'dificuldade', sel_dif)
            df_filtrado = aplicar_filtro(df_filtrado, 'ano', sel_ano)
            df_filtrado = aplicar_filtro(df_filtrado, 'topico_macro', sel_top)
            df_filtrado = aplicar_filtro(df_filtrado, 'tipo_input', sel_tipo)
            
            if len(df_filtrado) > 0:
                st.success(f"🔍 **{len(df_filtrado)}** questões encontradas.")
            else:
                st.warning("Nenhuma questão encontrada com essa combinação rigorosa.")

        else:
            # Modo Provas Antigas
            st.header("📄 Provas Antigas")
            opt_ano = sorted(df_questoes['ano'].unique())
            prova_sel = st.selectbox("Selecione a Fonte/Origem:", opt_ano, index=None)
            if prova_sel:
                df_filtrado = df_questoes[df_questoes['ano'] == prova_sel].sort_values(by='numero_questao')

        # --- LOOP DE EXIBIÇÃO ---
        for index, row in df_filtrado.iterrows():
            q_id = str(row['id'])
            
            # Timer só conta se for Prova E opção ativada
            usar_timer = ("Banco" not in modo_estudo) and st.session_state['prefs']['timer']
            
            if usar_timer and q_id not in st.session_state['timers']: 
                st.session_state['timers'][q_id] = time.time()
            
            with st.container(border=True):
                # Header
                c1, c2 = st.columns([4, 1])
                c1.markdown(f"**Questão {row.get('numero_questao','?')}** | {row['materia']}")
                c1.caption(f"🆔 {q_id} | 🏛️ {row['ano']} | 🔥 {row['dificuldade']}")
                
                if usar_timer:
                    tempo_decorrido = int(time.time() - st.session_state['timers'][q_id])
                    c2.markdown(f"⏱️ **{tempo_decorrido}s**")
                
                # Enunciado
                st.markdown(f"### {row['enunciado']}")
                
                tipo_input = str(row.get('tipo_input', 'Multipla')).strip().lower()
                
                if tipo_input == 'discursiva':
                    # --- DISCURSIVA (IA) ---
                    txt_resp = st.text_area("Sua Resposta:", key=f"txt_{q_id}", height=150)
                    st.caption("🤖 Solicitar Correção IA:")
                    b1, b2, b3 = st.columns(3)
                    
                    modo = None
                    if b1.button("👮 Banca", key=f"b_{q_id}"): modo = "Banca"
                    if b2.button("🧑‍🏫 Prof", key=f"p_{q_id}"): modo = "Professor"
                    if b3.button("🤔 Socrático", key=f"s_{q_id}"): modo = "Socrático"
                    
                    if modo:
                        if not txt_resp: 
                            st.warning("⚠️ Escreva algo!")
                        else:
                            with st.spinner(f"Analisando ({modo})..."):
                                feedback, nota_ia = corrigir_com_ia(row['enunciado'], row['gabarito'], txt_resp, modo)
                                
                                st.markdown("---")
                                st.markdown(f"### 📊 Nota: {nota_ia}/100")
                                st.markdown(f"**Feedback:**")
                                if modo == "Banca": st.info(feedback)
                                elif modo == "Socrático": st.warning(feedback)
                                else: st.success(feedback)
                                
                                registrar_resposta({
                                    'matricula': st.session_state['usuario_ativo'],
                                    'id_questao': q_id,
                                    'acertou': "IA-Check",
                                    'tempo': (time.time() - st.session_state['timers'][q_id]) if usar_timer else None,
                                    'confianca': f"IA-{modo}",
                                    'erro': feedback[:1000],
                                    'nota_percentual': nota_ia
                                })

                else:
                    # --- MÚLTIPLA ESCOLHA ---
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
                            tempo_salvar = (time.time() - st.session_state['timers'][q_id]) if usar_timer else None
                            letra = opcoes[resp]
                            gabarito = str(row['gabarito']).lower().strip()
                            acertou = letra == gabarito
                            nota_auto = 100 if acertou else 0
                            
                            if acertou:
                                st.success(f"✅ Correto! ({letra.upper()})")
                                if row.get('comentario'): st.info(f"💡 {row['comentario']}")
                                registrar_resposta({
                                    'matricula': st.session_state['usuario_ativo'],
                                    'id_questao': q_id,
                                    'acertou': True,
                                    'tempo': tempo_salvar,
                                    'confianca': conf,
                                    'erro': 'N/A',
                                    'nota_percentual': nota_auto
                                })
                                if usar_timer: st.session_state['timers'][q_id] = time.time()
                            else:
                                st.error(f"❌ Errado. Era {gabarito.upper()}")
                                if st.session_state['prefs']['autopsia']:
                                    st.session_state[f"erro_{q_id}"] = {'t': tempo_salvar, 'c': conf}
                                else:
                                    registrar_resposta({
                                        'matricula': st.session_state['usuario_ativo'],
                                        'id_questao': q_id,
                                        'acertou': False,
                                        'tempo': tempo_salvar,
                                        'confianca': conf,
                                        'erro': 'Não classificado',
                                        'nota_percentual': nota_auto
                                    })
                                    if usar_timer: st.session_state['timers'][q_id] = time.time()

                    if f"erro_{q_id}" in st.session_state:
                        st.warning("🔎 Autópsia: Por que errou?")
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
                                'erro': motivo,
                                'nota_percentual': 0
                            })
                            del st.session_state[f"erro_{q_id}"]
                            st.success("Salvo.")
                            time.sleep(1)
                            st.rerun()

st.markdown("<div style='height: 100px;'></div>", unsafe_allow_html=True)
