import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import time
from datetime import datetime

# --- 1. CONFIGURAÇÃO VISUAL ---
st.set_page_config(layout="wide", page_title="LMS - Sistema Inteligente")

st.markdown("""
    <style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    .stDeployButton {display:none;}
    
    .block-container {padding-top: 1rem; padding-bottom: 5rem;} /* Espaço extra embaixo */
    
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

# --- 2. CONEXÃO E BANCO DE DADOS ---
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
    # Não usa cache para ler preferências sempre atualizadas
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
            "TRUE" if dados['acertou'] else "FALSE",
            str(round(dados['tempo'], 2)),
            str(dados['confianca']),
            str(dados['erro']),
            str(datetime.now())
        ])
    except Exception as e:
        print(f"Erro ao salvar log: {e}")

def atualizar_preferencia_aluno(matricula, coluna_nome, novo_valor):
    """
    Atualiza qualquer preferência na planilha DB_ALUNOS.
    Mapeamento de colunas (A=1, B=2...):
    D(4)=login_protegido, E(5)=pref_timer, F(6)=pref_confianca, G(7)=pref_autopsia
    """
    mapa_colunas = {
        'login_protegido': 4,
        'pref_timer': 5,
        'pref_confianca': 6,
        'pref_autopsia': 7
    }
    
    if coluna_nome not in mapa_colunas: return False
    
    try:
        sheet = conectar_banco()
        ws = sheet.worksheet("DB_ALUNOS")
        cell = ws.find(str(matricula))
        
        valor_str = "TRUE" if novo_valor else "FALSE"
        ws.update_cell(cell.row, mapa_colunas[coluna_nome], valor_str)
        return True
    except Exception as e:
        st.error(f"Erro ao salvar preferência: {e}")
        return False

# --- 3. CONTROLE DE SESSÃO ---
if 'usuario_ativo' not in st.session_state:
    st.session_state['usuario_ativo'] = None

# Variáveis para cronômetro
if 'timers' not in st.session_state:
    st.session_state['timers'] = {} # Dicionário para guardar tempo de cada questão

# ==================================================
# 🔐 TELA DE LOGIN
# ==================================================
if not st.session_state['usuario_ativo']:
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("<div class='login-box'><h2>🎓 Portal do Aluno</h2></div>", unsafe_allow_html=True)
        
        with st.form("login_form"):
            matricula_input = st.text_input("Matrícula:", placeholder="Ex: 202401")
            senha_input = st.text_input("Senha:", type="password", placeholder="(Opcional se Login Livre)")
            
            if st.form_submit_button("Entrar", use_container_width=True):
                df_alunos, _ = carregar_alunos_live()
                
                if df_alunos.empty: # Modo Teste
                    st.session_state['usuario_ativo'] = matricula_input
                    st.session_state['nome_aluno'] = "Aluno Teste"
                    st.session_state['prefs'] = {'timer': True, 'confianca': True, 'autopsia': True}
                    st.rerun()

                aluno = df_alunos[df_alunos['matricula'].astype(str) == str(matricula_input)]
                
                if not aluno.empty:
                    dados = aluno.iloc[0]
                    protegido = str(dados.get('login_protegido', 'FALSE')).upper() == 'TRUE'
                    senha_real = str(dados.get('senha', '')).strip()
                    
                    # Carrega Preferências do Aluno para a Sessão
                    st.session_state['prefs'] = {
                        'timer': str(dados.get('pref_timer', 'FALSE')).upper() == 'TRUE',
                        'confianca': str(dados.get('pref_confianca', 'FALSE')).upper() == 'TRUE',
                        'autopsia': str(dados.get('pref_autopsia', 'FALSE')).upper() == 'TRUE'
                    }

                    if protegido:
                        if str(senha_input) == senha_real:
                            st.session_state['usuario_ativo'] = matricula_input
                            st.session_state['nome_aluno'] = dados['nome']
                            st.success("Sucesso!")
                            st.rerun()
                        else:
                            st.error("🔒 Senha incorreta para perfil protegido.")
                    else:
                        st.session_state['usuario_ativo'] = matricula_input
                        st.session_state['nome_aluno'] = dados['nome']
                        st.rerun()
                else:
                    st.error("Matrícula não encontrada.")

# ==================================================
# 🚀 ÁREA LOGADA
# ==================================================
else:
    # --- BARRA LATERAL (CONFIGURAÇÕES E MENU) ---
    with st.sidebar:
        st.title(f"👤 {st.session_state.get('nome_aluno', 'Aluno')}")
        
        # --- MENU DE CONFIGURAÇÕES ---
        with st.expander("⚙️ Configurações & Preferências"):
            # Recupera estado atual da planilha para sincronizar checkboxes
            df_alunos, _ = carregar_alunos_live()
            try:
                dados_atuais = df_alunos[df_alunos['matricula'].astype(str) == str(st.session_state['usuario_ativo'])].iloc[0]
                
                # Estado Segurança
                is_prot = str(dados_atuais.get('login_protegido', 'FALSE')).upper() == 'TRUE'
                # Estados Pedagógicos
                is_timer = str(dados_atuais.get('pref_timer', 'FALSE')).upper() == 'TRUE'
                is_conf = str(dados_atuais.get('pref_confianca', 'FALSE')).upper() == 'TRUE'
                is_auto = str(dados_atuais.get('pref_autopsia', 'FALSE')).upper() == 'TRUE'
            except:
                is_prot, is_timer, is_conf, is_auto = False, False, False, False

            st.caption("Segurança")
            new_prot = st.toggle("Exigir Senha no Login", value=is_prot)
            
            st.caption("Diagnóstico Pedagógico")
            new_timer = st.toggle("⏱️ Ver Cronômetro", value=is_timer)
            new_conf = st.toggle("🤔 Marcar Confiança (Metacognição)", value=is_conf)
            new_auto = st.toggle("🔎 Autópsia do Erro", value=is_auto)
            
            # Lógica de Salvamento (se mudou algo, salva e recarrega prefs da sessão)
            mudou = False
            if new_prot != is_prot: 
                atualizar_preferencia_aluno(st.session_state['usuario_ativo'], 'login_protegido', new_prot)
                mudou = True
            if new_timer != is_timer:
                atualizar_preferencia_aluno(st.session_state['usuario_ativo'], 'pref_timer', new_timer)
                st.session_state['prefs']['timer'] = new_timer
                mudou = True
            if new_conf != is_conf:
                atualizar_preferencia_aluno(st.session_state['usuario_ativo'], 'pref_confianca', new_conf)
                st.session_state['prefs']['confianca'] = new_conf
                mudou = True
            if new_auto != is_auto:
                atualizar_preferencia_aluno(st.session_state['usuario_ativo'], 'pref_autopsia', new_auto)
                st.session_state['prefs']['autopsia'] = new_auto
                mudou = True
                
            if mudou:
                st.toast("Preferências Atualizadas!")
                time.sleep(0.5)
                st.rerun()

        st.divider()
        modo_estudo = st.sidebar.radio("Menu Principal:", ["🎯 Banco de Questões", "📄 Provas Antigas"])
        
        if st.sidebar.button("Sair"):
            st.session_state['usuario_ativo'] = None
            st.rerun()

    # --- CARREGAMENTO DE DADOS ---
    df_questoes = carregar_questoes()
    
    if df_questoes.empty:
        st.error("Erro: Base de questões vazia ou não encontrada.")
    else:
        # --- FILTRAGEM (MODO BANCO OU PROVA) ---
        df_filtrado = pd.DataFrame()
        
        if "Banco" in modo_estudo:
            st.header("🎯 Banco Geral de Questões")
            
            # Filtros
            c1, c2 = st.columns(2)
            with c1:
                logica = st.radio("Lógica:", ["Rigoroso (E)", "Flexível (OU)"], horizontal=True)
            operador = "and" if "Rigoroso" in logica else "or"
            
            opt_mat = sorted(df_questoes['materia'].unique()) if 'materia' in df_questoes.columns else []
            opt_dif = sorted(df_questoes['dificuldade'].unique()) if 'dificuldade' in df_questoes.columns else []
            
            sel_mat = st.multiselect("Matéria:", opt_mat)
            sel_dif = st.multiselect("Dificuldade:", opt_dif)
            
            queries = []
            if sel_mat: queries.append("materia in @sel_mat")
            if sel_dif: queries.append("dificuldade in @sel_dif")
            
            df_filtrado = df_questoes.copy()
            if queries:
                q = f" {operador} ".join(queries)
                try: df_filtrado = df_questoes.query(q)
                except: pass
            elif operador == "or" and (sel_mat or sel_dif):
                pass
            
            st.caption(f"{len(df_filtrado)} questões encontradas.")

        else: # Modo Prova
            st.header("📄 Provas Antigas")
            opt_ano = sorted(df_questoes['ano'].astype(str).unique()) if 'ano' in df_questoes.columns else []
            prova_sel = st.selectbox("Selecione a Edição:", opt_ano, index=None)
            
            if prova_sel:
                df_filtrado = df_questoes[df_questoes['ano'].astype(str) == str(prova_sel)]
                if 'numero_questao' in df_filtrado.columns:
                    df_filtrado = df_filtrado.sort_values(by='numero_questao')
            else:
                st.info("👈 Selecione uma prova no menu.")

        # --- EXIBIÇÃO DAS QUESTÕES (LOOP) ---
        for index, row in df_filtrado.iterrows():
            q_id = str(row['id'])
            
            # Inicializa Cronômetro Individual se não existir
            if q_id not in st.session_state['timers']:
                st.session_state['timers'][q_id] = time.time()
            
            with st.container(border=True):
                # Cabeçalho da Questão
                c_head1, c_head2 = st.columns([3, 1])
                with c_head1:
                    ano_txt = row.get('ano', '')
                    num_txt = f"Q.{row.get('numero_questao','')}" 
                    st.caption(f"🆔 {num_txt} | 📂 {row['materia']} | 📅 {ano_txt}")
                with c_head2:
                    # MOSTRA CRONÔMETRO (SE ATIVO NAS PREFS)
                    if st.session_state['prefs']['timer']:
                        tempo_decorrido = time.time() - st.session_state['timers'][q_id]
                        st.caption(f"⏱️ {int(tempo_decorrido)}s")

                st.markdown(f"**{row['enunciado']}**")
                
                # Alternativas
                opcoes = {
                    f"A) {row['alternativa_a']}": 'a',
                    f"B) {row['alternativa_b']}": 'b',
                    f"C) {row['alternativa_c']}": 'c',
                    f"D) {row['alternativa_d']}": 'd'
                }
                
                # Controle de Estado da Resposta (Radio)
                key_radio = f"radio_{q_id}"
                resposta = st.radio("Alternativa:", list(opcoes.keys()), key=key_radio, index=None, label_visibility="collapsed")
                
                # --- LÓGICA DE BOTÕES DE ENVIO (CAMADA ATIVA) ---
                
                # Variáveis de controle
                acao_enviar = False
                confianca_nivel = "N/A"
                
                # CASO 1: Com Confiança Ativada
                if st.session_state['prefs']['confianca']:
                    st.write("---")
                    st.caption("Nível de Certeza:")
                    col_b1, col_b2, col_b3 = st.columns(3)
                    if col_b1.button("🔴 Chute", key=f"chute_{q_id}", use_container_width=True):
                        acao_enviar = True
                        confianca_nivel = "Baixa (Chute)"
                    if col_b2.button("🟡 Dúvida", key=f"duvida_{q_id}", use_container_width=True):
                        acao_enviar = True
                        confianca_nivel = "Média"
                    if col_b3.button("🟢 Certeza", key=f"cert_{q_id}", use_container_width=True):
                        acao_enviar = True
                        confianca_nivel = "Alta"
                
                # CASO 2: Modo Simples (Sem confiança)
                else:
                    st.write("")
                    if st.button("Responder", key=f"btn_{q_id}"):
                        acao_enviar = True
                        confianca_nivel = "Desativado"

                # --- PROCESSAMENTO DA RESPOSTA ---
                if acao_enviar:
                    if not resposta:
                        st.warning("⚠️ Selecione uma alternativa antes de enviar.")
                    else:
                        # Cálculo final do tempo
                        tempo_final = time.time() - st.session_state['timers'][q_id]
                        
                        letra_escolhida = opcoes[resposta]
                        gabarito_oficial = str(row['gabarito']).lower().strip()
                        acertou = letra_escolhida == gabarito_oficial
                        
                        if acertou:
                            st.success("✅ Correto!")
                            # Salva imediatamente (Acerto não tem autópsia)
                            registrar_resposta({
                                'matricula': st.session_state['usuario_ativo'],
                                'id_questao': q_id,
                                'acertou': True,
                                'tempo': tempo_final,
                                'confianca': confianca_nivel,
                                'erro': 'N/A'
                            })
                            # Reseta o timer para uma futura tentativa
                            st.session_state['timers'][q_id] = time.time()
                            
                        else:
                            st.error(f"❌ Incorreto. Gabarito: {gabarito_oficial.upper()}")
                            
                            # VERIFICA SE DEVE PEDIR AUTÓPSIA
                            if st.session_state['prefs']['autopsia']:
                                # Salva estado temporário para mostrar botões de erro
                                st.session_state[f"erro_pendente_{q_id}"] = {
                                    'tempo': tempo_final,
                                    'confianca': confianca_nivel
                                }
                            else:
                                # Se não tem autópsia, salva como erro genérico
                                registrar_resposta({
                                    'matricula': st.session_state['usuario_ativo'],
                                    'id_questao': q_id,
                                    'acertou': False,
                                    'tempo': tempo_final,
                                    'confianca': confianca_nivel,
                                    'erro': 'Não Classificado'
                                })
                                st.session_state['timers'][q_id] = time.time()

                # --- EXIBIÇÃO CONDICIONAL DA AUTÓPSIA (DEPOIS DO ERRO) ---
                if f"erro_pendente_{q_id}" in st.session_state:
                    st.info("🔎 Diagnóstico: Por que você errou?")
                    c_e1, c_e2, c_e3, c_e4 = st.columns(4)
                    
                    motivo_selecionado = None
                    if c_e1.button("Falta Base", key=f"e1_{q_id}"): motivo_selecionado = "Lacuna Conceitual"
                    if c_e2.button("Interpretação", key=f"e2_{q_id}"): motivo_selecionado = "Erro Interpretação"
                    if c_e3.button("Atenção", key=f"e3_{q_id}"): motivo_selecionado = "Falta Atenção"
                    if c_e4.button("Pegadinha", key=f"e4_{q_id}"): motivo_selecionado = "Distrator"
                    
                    if motivo_selecionado:
                        dados_pendentes = st.session_state[f"erro_pendente_{q_id}"]
                        registrar_resposta({
                            'matricula': st.session_state['usuario_ativo'],
                            'id_questao': q_id,
                            'acertou': False,
                            'tempo': dados_pendentes['tempo'],
                            'confianca': dados_pendentes['confianca'],
                            'erro': motivo_selecionado
                        })
                        st.toast(f"Diagnóstico Salvo: {motivo_selecionado}")
                        # Limpa o estado pendente e reseta timer
                        del st.session_state[f"erro_pendente_{q_id}"]
                        st.session_state['timers'][q_id] = time.time()
                        time.sleep(1)
                        st.rerun()

# Espaço Fantasma para o Rodapé não tampar nada
st.markdown("<div style='height: 100px;'></div>", unsafe_allow_html=True)
