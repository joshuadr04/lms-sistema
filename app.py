import streamlit as st
import pandas as pd
import requests # Usamos requests (HTTP) para não depender de instalação complexa
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
    .block-container {padding-top: 3rem; padding-bottom: 5rem;} 
    .login-box {padding: 20px; border-radius: 10px; background-color: #1e1e1e; text-align: center; margin-bottom: 20px; border: 1px solid #333;}
    .resumo-box {background-color: #121212; padding: 20px; border-radius: 15px; border: 1px solid #444; text-align: center; margin-top: 20px;}
    </style>
    """, unsafe_allow_html=True)

# ==================================================
# 2. CONEXÃO COM SUPABASE (BANCO DE DADOS) ⚡
# ==================================================
# 👇👇👇 COLOQUE SUAS CHAVES AQUI 👇👇👇
SUPABASE_URL = "https://urwakfupwquqzwmvixyj.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InVyd2FrZnVwd3F1cXp3bXZpeHlqIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjgyMzg4NjAsImV4cCI6MjA4MzgxNDg2MH0.-w7ccV22Wi98Axf622VKjpx5Remb89Abb-GpmluYn8k"

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=minimal" # Faz insert ser rápido sem retornar dados
}

@st.cache_data(ttl=3600) # Cache de 1 hora
def carregar_questoes():
    """Busca todas as questões via API do Supabase"""
    try:
        # Busca todas as questões (*)
        url = f"{SUPABASE_URL}/rest/v1/questoes?select=*"
        resp = requests.get(url, headers=HEADERS)
        if resp.status_code == 200:
            df = pd.DataFrame(resp.json())
            # Força conversão para string para evitar erros de visualização no Streamlit
            return df.astype(str)
        else:
            # Se der erro 400+, mostra na tela para debug
            st.error(f"Erro Supabase: {resp.status_code}")
            return pd.DataFrame()
    except Exception as e:
        st.error(f"Erro de conexão: {e}")
        return pd.DataFrame()

def carregar_alunos_live():
    """Busca alunos sem cache para login"""
    try:
        url = f"{SUPABASE_URL}/rest/v1/alunos?select=*"
        resp = requests.get(url, headers=HEADERS)
        if resp.status_code == 200:
            return pd.DataFrame(resp.json())
        return pd.DataFrame()
    except:
        return pd.DataFrame()

def registrar_resposta(dados):
    """Envia resposta para o Supabase via API"""
    try:
        url = f"{SUPABASE_URL}/rest/v1/respostas"
        
        # Prepara payload
        payload = {
            "matricula": str(dados['matricula']),
            "id_questao": str(dados['id_questao']),
            "acertou": str(dados['acertou']),
            "tempo": dados['tempo'], # Já vem como float ou None (JSON null)
            "confianca": str(dados['confianca']),
            "motivo_erro": str(dados['erro'])[:1000],
            "nota_percentual": dados.get('nota_percentual', 0)
        }
        
        # Dispara e esquece (Fire & Forget) - Muito rápido
        requests.post(url, json=payload, headers=HEADERS)
        
    except Exception as e:
        print(f"Erro ao salvar: {e}")

def atualizar_preferencia_aluno(matricula, coluna_nome, novo_valor):
    """Atualiza preferências com PATCH"""
    try:
        url = f"{SUPABASE_URL}/rest/v1/alunos?matricula=eq.{matricula}"
        payload = {coluna_nome: novo_valor}
        requests.patch(url, json=payload, headers=HEADERS)
        return True
    except:
        return False

# ==================================================
# 3. CÉREBRO DA IA (STREAMING)
# ==================================================
def corrigir_com_ia_stream(pergunta, gabarito, resposta_aluno, modo_escolhido, placeholder_saida):
    if "gemini" in st.secrets:
        genai.configure(api_key=st.secrets["gemini"]["api_key"])
    else:
        placeholder_saida.error("Erro: Chave [gemini] não configurada.")
        return "", 0

    base_instruction = """
    IMPORTANTE: No final da sua resposta, você DEVE incluir a nota percentual (0 a 100).
    Use formato: [[NOTA:XX]]
    """
    
    instrucao_sistema = ""
    if modo_escolhido == "Banca": instrucao_sistema = base_instruction + """Atue como CORRETOR DE BANCA RIGOROSO."""
    elif modo_escolhido == "Professor": instrucao_sistema = base_instruction + """Atue como PROFESSOR DIDÁTICO."""
    elif modo_escolhido == "Socrático": instrucao_sistema = base_instruction + """Atue como MENTOR SOCRÁTICO."""

    modelo = genai.GenerativeModel('models/gemini-flash-latest', system_instruction=instrucao_sistema)
    prompt = f"PERGUNTA: {pergunta}\nGABARITO: {gabarito}\nALUNO: {resposta_aluno}"

    texto_completo = ""
    nota = 0

    try:
        response = modelo.generate_content(prompt, stream=True)
        for chunk in response:
            if chunk.text:
                texto_completo += chunk.text
                placeholder_saida.markdown(texto_completo + "▌")
        
        placeholder_saida.markdown(texto_completo)
        
        match = re.search(r'\[\[NOTA:(\d+)\]\]', texto_completo)
        if match: nota = int(match.group(1))
        
        return texto_completo, nota
    except Exception as e:
        placeholder_saida.error(f"IA Erro: {str(e)}")
        return str(e), 0

# ==================================================
# 4. LÓGICA DO APP
# ==================================================
if 'usuario_ativo' not in st.session_state: st.session_state['usuario_ativo'] = None
if 'timers' not in st.session_state: st.session_state['timers'] = {}
if 'prova_em_andamento' not in st.session_state: st.session_state['prova_em_andamento'] = False
if 'prova_selecionada_anterior' not in st.session_state: st.session_state['prova_selecionada_anterior'] = None
if 'resumo_prova' not in st.session_state: st.session_state['resumo_prova'] = None

# --- LOGIN ---
if not st.session_state['usuario_ativo']:
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("<div class='login-box'><h2>🎓 Portal do Aluno</h2></div>", unsafe_allow_html=True)
        with st.form("login_form"):
            matricula_input = st.text_input("Matrícula:", placeholder="Ex: 202401")
            senha_input = st.text_input("Senha:", type="password")
            if st.form_submit_button("Entrar", use_container_width=True):
                df_alunos = carregar_alunos_live()
                if not df_alunos.empty:
                    # Filtro manual no DataFrame (Seguro e Simples)
                    aluno = df_alunos[df_alunos['matricula'].astype(str) == str(matricula_input)]
                    if not aluno.empty:
                        dados = aluno.iloc[0]
                        protegido = str(dados.get('login_protegido', 'False')).lower() == 'true'
                        senha_real = str(dados.get('senha', '')).strip()
                        
                        st.session_state['prefs'] = {
                            'timer': str(dados.get('pref_timer', 'False')).lower() == 'true',
                            'confianca': str(dados.get('pref_confianca', 'False')).lower() == 'true',
                            'autopsia': str(dados.get('pref_autopsia', 'False')).lower() == 'true'
                        }

                        if protegido and str(senha_input) != senha_real:
                            st.error("🔒 Senha incorreta.")
                        else:
                            st.session_state['usuario_ativo'] = matricula_input
                            st.session_state['nome_aluno'] = dados['nome']
                            st.rerun()
                    else: st.error("Matrícula não encontrada.")
                else: st.error("Erro ao conectar banco de alunos.")

# --- ÁREA LOGADA ---
else:
    if 'modo_estudo_temp' not in st.session_state: st.session_state['modo_estudo_temp'] = "🎯 Banco de Questões"

    with st.sidebar:
        st.title(f"👤 {st.session_state.get('nome_aluno', 'Aluno')}")
        modo_estudo = st.radio("Menu:", ["🎯 Banco de Questões", "📄 Provas Antigas"])
        st.divider()
        with st.expander("⚙️ Preferências", expanded=True):
            df_alunos = carregar_alunos_live()
            dados = df_alunos[df_alunos['matricula'].astype(str) == str(st.session_state['usuario_ativo'])].iloc[0]
            
            p_login = st.toggle("🔒 Exigir Senha", value=str(dados['login_protegido']).lower()=='true')
            if p_login != (str(dados['login_protegido']).lower()=='true'):
                atualizar_preferencia_aluno(st.session_state['usuario_ativo'], 'login_protegido', p_login)
                st.toast("Salvo!"); time.sleep(0.5); st.rerun()

            p_conf = st.toggle("🤔 Confiança", value=str(dados['pref_confianca']).lower()=='true')
            if p_conf != st.session_state['prefs']['confianca']:
                 atualizar_preferencia_aluno(st.session_state['usuario_ativo'], 'pref_confianca', p_conf)
                 st.session_state['prefs']['confianca'] = p_conf; st.rerun()
            
            p_auto = st.toggle("🔎 Autópsia Erro", value=str(dados['pref_autopsia']).lower()=='true')
            if p_auto != st.session_state['prefs']['autopsia']:
                 atualizar_preferencia_aluno(st.session_state['usuario_ativo'], 'pref_autopsia', p_auto)
                 st.session_state['prefs']['autopsia'] = p_auto; st.rerun()
        st.divider()
        if st.sidebar.button("Sair"): st.session_state['usuario_ativo'] = None; st.session_state['prova_em_andamento'] = False; st.rerun()

    df_questoes = carregar_questoes()
    
    if df_questoes.empty:
        st.error("⚠️ Base de questões vazia. Verifique se importou as questões no Supabase.")
    else:
        df_filtrado = pd.DataFrame()
        
        # --- MODO BANCO ---
        if "Banco" in modo_estudo:
            st.session_state['prova_em_andamento'] = False; st.session_state['resumo_prova'] = None
            st.header("🎯 Banco Geral")
            c_log, c_inf = st.columns([1, 2])
            with c_log: logica_filtro = st.radio("Lógica:", ["Flexível (OU)", "Rigoroso (E)"], horizontal=True)
            with c_inf: st.caption("Flexível: Qualquer critério. Rigoroso: Todos os critérios.")

            opt_mat = sorted(df_questoes['materia'].unique())
            opt_dif = sorted(df_questoes['dificuldade'].unique())
            opt_ano = sorted(df_questoes['ano'].unique())
            
            sel_mat = st.multiselect("📚 Matéria:", opt_mat)
            with st.expander("🌪️ Mais Filtros"):
                c1, c2 = st.columns(2)
                with c1: sel_dif = st.multiselect("🔥 Dificuldade:", opt_dif)
                with c2: sel_ano = st.multiselect("🏛️ Fonte:", opt_ano)

            df_filtrado = df_questoes.copy()
            def aplicar_filtro(df, col, sels):
                if not sels: return df
                if "Rigoroso" in logica_filtro:
                    for item in sels: df = df[df[col] == item]
                    return df
                return df[df[col].isin(sels)]

            df_filtrado = aplicar_filtro(df_filtrado, 'materia', sel_mat)
            df_filtrado = aplicar_filtro(df_filtrado, 'dificuldade', sel_dif)
            df_filtrado = aplicar_filtro(df_filtrado, 'ano', sel_ano)
            
            if len(df_filtrado) > 0: st.success(f"🔍 **{len(df_filtrado)}** questões.")
            else: st.warning("Nenhum resultado.")

            for idx, row in df_filtrado.iterrows():
                q_id = str(row['id'])
                with st.container(border=True):
                    c1, c2 = st.columns([4, 1])
                    c1.markdown(f"**Questão {row.get('numero_questao','?')}** | {row['materia']}")
                    c1.caption(f"🆔 {q_id} | 🏛️ {row['ano']} | 🔥 {row['dificuldade']}")
                    st.markdown(f"### {row['enunciado']}")
                    
                    tipo = str(row.get('tipo_input', 'Multipla')).lower()
                    if tipo == 'discursiva':
                        txt = st.text_area("Resposta:", key=f"t_{q_id}")
                        col_b = st.columns(3)
                        modo = None
                        if col_b[0].button("👮 Banca", key=f"b_{q_id}"): modo = "Banca"
                        if col_b[1].button("🧑‍🏫 Prof", key=f"p_{q_id}"): modo = "Professor"
                        if col_b[2].button("🤔 Socrático", key=f"s_{q_id}"): modo = "Socrático"
                        if modo and txt:
                            ph = st.empty()
                            with st.spinner("IA Pensando..."):
                                fb, nota = corrigir_com_ia_stream(row['enunciado'], row['gabarito'], txt, modo, ph)
                                st.markdown(f"### 📊 Nota: {nota}/100")
                                registrar_resposta({'matricula': st.session_state['usuario_ativo'], 'id_questao': q_id, 'acertou': "IA-Check", 'tempo': None, 'confianca': f"IA-{modo}", 'erro': fb[:1000], 'nota_percentual': nota})
                    else:
                        ops = {f"A) {row['alternativa_a']}":'a', f"B) {row['alternativa_b']}":'b', f"C) {row['alternativa_c']}":'c', f"D) {row['alternativa_d']}":'d'}
                        resp = st.radio("Selecione:", list(ops.keys()), key=f"r_{q_id}", index=None)
                        if st.button("Responder", key=f"btn_{q_id}"):
                            if resp:
                                acertou = ops[resp] == str(row['gabarito']).lower().strip()
                                if acertou: st.success("✅ Correto!"); registrar_resposta({'matricula':st.session_state['usuario_ativo'], 'id_questao':q_id, 'acertou':True, 'tempo':None, 'confianca':'N/A', 'erro':'N/A', 'nota_percentual':100})
                                else: st.error(f"❌ Era {str(row['gabarito']).upper()}"); registrar_resposta({'matricula':st.session_state['usuario_ativo'], 'id_questao':q_id, 'acertou':False, 'tempo':None, 'confianca':'N/A', 'erro':'Erro', 'nota_percentual':0})

                        # Autópsia
                        if f"erro_{q_id}" in st.session_state:
                            st.warning("🔎 Autópsia: Por que errou?")
                            c1, c2, c3, c4 = st.columns(4)
                            motivo = None
                            if c1.button("🧠 Lacuna", key=f"m1_{q_id}"): motivo = "Lacuna Conceitual"
                            if c2.button("👀 Atenção", key=f"m2_{q_id}"): motivo = "Falta de Atenção"
                            if c3.button("📖 Interp.", key=f"m3_{q_id}"): motivo = "Erro de Interpretação"
                            if c4.button("🤡 Pegadinha", key=f"m4_{q_id}"): motivo = "Distrator/Pegadinha"
                            if motivo:
                                # Recupera info temporária
                                d = st.session_state[f"erro_{q_id}"]
                                registrar_resposta({'matricula': st.session_state['usuario_ativo'], 'id_questao': q_id, 'acertou': False, 'tempo': d['t'], 'confianca': d['c'], 'erro': motivo, 'nota_percentual': 0})
                                del st.session_state[f"erro_{q_id}"]
                                st.success("Salvo.")
                                time.sleep(0.5)
                                st.rerun()

        # --- MODO PROVAS ---
        else:
            st.header("📄 Provas Antigas")
            sel_prova = st.selectbox("Selecione:", sorted(df_questoes['ano'].unique()), index=None)
            
            # Timer Toggle
            dados_user = carregar_alunos_live()
            dados_user = dados_user[dados_user['matricula'].astype(str)==str(st.session_state['usuario_ativo'])].iloc[0]
            st.write("")
            timer_on = st.toggle("⏱️ Cronômetro", value=str(dados_user['pref_timer']).lower()=='true')
            if timer_on != st.session_state['prefs']['timer']:
                atualizar_preferencia_aluno(st.session_state['usuario_ativo'], 'pref_timer', timer_on)
                st.session_state['prefs']['timer'] = timer_on; st.rerun()

            if sel_prova != st.session_state['prova_selecionada_anterior']:
                st.session_state['prova_em_andamento'] = False; st.session_state['resumo_prova'] = None
                st.session_state['prova_selecionada_anterior'] = sel_prova; st.rerun()

            if sel_prova:
                df_prova = df_questoes[df_questoes['ano'] == sel_prova].sort_values(by='numero_questao')
                
                if st.session_state['prefs']['timer'] and not st.session_state['prova_em_andamento'] and not st.session_state['resumo_prova']:
                    if st.button("🚀 COMEÇAR PROVA", use_container_width=True):
                        st.session_state['prova_em_andamento'] = True
                        now = time.time()
                        for i, r in df_prova.iterrows(): st.session_state['timers'][str(r['id'])] = now
                        st.rerun()
                
                elif st.session_state['resumo_prova']:
                    st.balloons(); st.success("Prova Finalizada!")
                    if st.button("Voltar"): st.session_state['resumo_prova']=None; st.session_state['prova_em_andamento']=False; st.rerun()
                
                else:
                    for i, row in df_prova.iterrows():
                        q_id = str(row['id'])
                        use_t = st.session_state['prefs']['timer']
                        if use_t and q_id not in st.session_state['timers']: st.session_state['timers'][q_id] = time.time()
                        
                        with st.container(border=True):
                            c1, c2 = st.columns([4,1])
                            c1.markdown(f"**Questão {row.get('numero_questao','?')}**")
                            if use_t: c2.markdown(f"⏱️ {int(time.time()-st.session_state['timers'][q_id])}s")
                            st.markdown(f"### {row['enunciado']}")
                            
                            # (Lógica simplificada de resposta igual ao Banco)
                            ops = {f"A) {row['alternativa_a']}":'a', f"B) {row['alternativa_b']}":'b', f"C) {row['alternativa_c']}":'c', f"D) {row['alternativa_d']}":'d'}
                            resp = st.radio("Resp:", list(ops.keys()), key=f"rp_{q_id}", index=None)
                            if st.button("Responder", key=f"bp_{q_id}"):
                                t_gasto = (time.time()-st.session_state['timers'][q_id]) if use_t else None
                                if resp and ops[resp] == str(row['gabarito']).lower().strip():
                                    st.success("✅"); registrar_resposta({'matricula':st.session_state['usuario_ativo'], 'id_questao':q_id, 'acertou':True, 'tempo':t_gasto, 'confianca':'N/A', 'erro':'N/A', 'nota_percentual':100})
                                else:
                                    st.error("❌"); registrar_resposta({'matricula':st.session_state['usuario_ativo'], 'id_questao':q_id, 'acertou':False, 'tempo':t_gasto, 'confianca':'N/A', 'erro':'Erro', 'nota_percentual':0})
                            
                            # Autópsia na Prova
                            if f"erro_{q_id}" in st.session_state:
                                st.warning("🔎 Autópsia: Por que errou?")
                                c1, c2, c3, c4 = st.columns(4)
                                motivo = None
                                if c1.button("🧠 Lacuna", key=f"m1p_{q_id}"): motivo = "Lacuna Conceitual"
                                if c2.button("👀 Atenção", key=f"m2p_{q_id}"): motivo = "Falta de Atenção"
                                if c3.button("📖 Interp.", key=f"m3p_{q_id}"): motivo = "Erro de Interpretação"
                                if c4.button("🤡 Pegadinha", key=f"m4p_{q_id}"): motivo = "Distrator/Pegadinha"
                                if motivo:
                                    d = st.session_state[f"erro_{q_id}"]
                                    registrar_resposta({'matricula': st.session_state['usuario_ativo'], 'id_questao': q_id, 'acertou': False, 'tempo': d['t'], 'confianca': d['c'], 'erro': motivo, 'nota_percentual': 0})
                                    del st.session_state[f"erro_{q_id}"]
                                    st.success("Salvo.")
                                    time.sleep(0.5)
                                    st.rerun()

                    if use_t and st.session_state['prova_em_andamento']:
                        if st.button("🏁 TERMINAR", type="primary"): st.session_state['prova_em_andamento']=False; st.session_state['resumo_prova']=True; st.rerun()

st.markdown("<div style='height: 100px;'></div>", unsafe_allow_html=True)
