import streamlit as st
import os
import sys
import logging
import sqlite3
import hashlib
import base64
from datetime import datetime
import requests # Adicionado para fazer requisições HTTP

# Importar funções de utilidade do novo módulo
from app_logic.utils import set_background_image, set_sidebar_background_image, get_dolar_cotacao

st.set_page_config(layout="wide", page_title="Gerenciamento COMEX")

# Injetar CSS personalizado para ajustar layout e ocultar elementos indesejados
st.markdown("""
<style>
/* Oculta o botão de fullscreen que aparece ao passar o mouse sobre as imagens */
button[title="View fullscreen"] {
    display: none !important;
}
/* Ajustes para reduzir o espaço ao redor da logo da sidebar */
[data-testid="stSidebarUserContent"] {
    padding-top: 0px !important;
    padding-bottom: 0px !important;
}
[data-testid="stSidebarUserContent"] .stImage {
    margin-top: 0px !important;
    margin-bottom: 0px !important;
    padding-top: 0px !important;
    padding-bottom: 0px !important;
}
[data-testid="stSidebarUserContent"] img {
    margin-top: 0px !important;
    margin-bottom: 0px !important;
    padding-top: 0px !important;
    padding-bottom: 0px !important;
}
/* Ajustar margens do div de usuário/notificações na sidebar */
.stSidebar [data-testid="stVerticalBlock"] > div:nth-child(2) > div:nth-child(1) > div:nth-child(1) {
    margin-top: 0px !important;
    margin-bottom: 0px !important;
    padding-top: 0px !important;
    padding-bottom: 0px !important;
}
/* Reduzir o padding dos botões na sidebar para um visual mais compacto */
/* Ajustado para afetar diretamente os botões dentro da sidebar */
[data-testid="stSidebarNav"] button {
    padding-top: 0.1rem !important; /* Reduzir padding superior */
    padding-bottom: 0.1rem !important; /* Reduzir padding inferior */
    margin-top: 0.05rem !important; /* Reduzir margem superior */
    margin-bottom: 0.05rem !important; /* Reduzir margem inferior */
    height: auto !important; /* Permite que a altura se ajuste ao conteúdo */
}
/* Remover margens e padding de subheaders na sidebar para compactar */
.stSidebar h3 {
    margin-top: 0.2rem !important; /* Reduzir margem superior */
    margin-bottom: 0.2rem !important; /* Reduzir margem inferior */
    padding-top: 0px !important;
    padding-bottom: 0px !important;
}
/* Ajustar margens e padding para a imagem principal (se necessário) */
.main-logo-container {
    margin-top: 0px !important;
    margin-bottom: 0px !important;
    padding-top: 0px !important;
    padding-bottom: 0px !important;
}
.main-logo-container img {
    margin-top: 0px !important;
    margin-bottom: 0px !important;
    padding-top: 0px !important;
    padding-bottom: 0px !important;
}

/* Remover margens e padding de st-emotion-cache genéricos */
.st-emotion-cache-z5fcl4, .st-emotion-cache-zq5wmm, .st-emotion-cache-1c7y2o2,
.st-emotion-cache-1avcm0n, .st-emotion-cache-1dp5ifq, .st-emotion-cache-10qtn7d,
.st-emotion-cache-1y4p8pa, .st-emotion-cache-ocqkz7, .st-emotion-cache-1gh0m0m,
.st-emotion-cache-1vq4p4b, .st-emotion-cache-1v04791, .st-emotion-cache-1kyx2u8 {
    padding-top: 0 !important;
    padding-bottom: 0 !important;
    margin-top: 0 !important;
    margin-bottom: 0 !important;
}

/* Remover padding do cabeçalho do Streamlit */
header {
    padding: 0 !important;
}

/* Remover padding e margem de elementos de bloco no topo */
.block-container {
    padding-top: 0 !important;
    padding-bottom: 0 !important;
    margin-top: 0 !important;
    margin-bottom: 0 !important;
}

/* Ajustar o padding do main content para que o conteúdo comece mais para cima */
.stApp > header {
    height: 0px !important;
}

/* Ajustar o padding do main content para que o conteúdo comece mais para cima */
.main .block-container {
    padding-top: 0rem !important;
    padding-right: 1rem !important;
    padding-left: 1rem !important;
    padding-bottom: 1rem !important;
}

/* Remover espaço superior do título da página */
h1, h2, h3, h4, h5, h6 {
    margin-top: 0rem !important;
    padding-top: 0rem !important;
}

/* Ajustar margem superior do primeiro elemento após o cabeçalho */
.stApp > div:first-child > div:first-child {
    margin-top: 0 !important;
}

/* Ocultar a barra de decoração superior do Streamlit */
[data-testid="stDecoration"] {
    display: none !important;
}

/* Ocultar o "Deploy" e os três pontos no canto superior direito */
.st-emotion-cache-s1qj3df {
    display: none !important;
}

/* Ajustar o padding do conteúdo dentro da sidebar para um visual mais compacto */
[data-testid="stSidebarContent"] {
    padding-top: 0.1rem !important; /* Reduzir padding superior */
    padding-bottom: 0.1rem !important; /* Reduzir padding inferior */
    padding-left: 0.1rem !important; /* Reduzir padding esquerdo */
    padding-right: 0.1rem !important; /* Reduzir padding direito */
}

/* Ocultar o cabeçalho do Streamlit que pode conter o título da página ou outros elementos */
.st-emotion-cache-10qtn7d, .st-emotion-cache-1a3f5x, .st-emotion-cache-1avcm0n {
    display: none !important;
}

/* Ocultar o texto de status no canto superior esquerdo (seletores genéricos) */
[data-testid="stStatusWidget"],
.st-emotion-cache-1jm6g5k,
.st-emotion-cache-1r6dm1k,
.st-emotion-cache-1d3jo8e,
body > div:nth-child(1) > div:nth-child(1) > div:nth-child(1) > div:nth-child(1) > div:first-child,
body > div:nth-child(1) > div:nth-child(1) > div:first-child > div:first-child > div:first-child,
body > div:nth-child(1) > div:first-child > div:first-child > div:first-child,
.st-emotion-cache-1g8w69,
.st-emotion-cache-1v04791 {
    display: none !important;
}

/* Ajustes para centralizar horizontalmente os inputs de texto e labels na tela de login */
/* E definir um tamanho máximo para os inputs de texto */
.st-emotion-cache-h5rpjc, /* Seletor comum para o container de inputs de texto */
.st-emotion-cache-kjg0a8 { /* Outro seletor possível para o wrapper de inputs */
    max-width: 300px; /* Define a largura máxima do container/input */
    margin-left: auto;
    margin-right: auto;
    float: none; /* Garante que não haja float que impeça o margin auto */
}

/* Alinhar o label do input à esquerda (conforme a imagem) */
div[data-testid="stTextInput"] label { /* Alvo: o label dentro do stTextInput */
    display: block;
    text-align: left; /* Alinha o texto do label à esquerda */
    width: 100%; /* Garante que o label ocupe a largura total para alinhar o texto */
    /* Removido padding-left aqui, pois o input será centralizado e o label deve seguir */
}

/* Centralizar os inputs de texto */
div[data-testid="stTextInput"] > div > div > input {
    max-width: 250px; /* Ajusta a largura do campo de input */
    min-width: 150px; /* Define uma largura mínima para o campo de input */
    margin-left: 15px;
    margin-right: auto;
    display: block; /* Para que margin auto funcione */
}

/* Adicionar espaçamento entre os campos de entrada */
div[data-testid="stTextInput"] {
    margin-bottom: 15px; /* Espaçamento entre os campos de texto */
}

/* Centralizar o botão de Entrar e adicionar espaçamento */
div[data-testid="stForm"] button {
    display: block; /* Para que margin auto funcione */
    margin-left: 15px;
    margin-right: 15px;
    float: none;
    margin-top: 15px; /* Espaçamento acima do botão */
}

/* Centralizar verticalmente o conteúdo principal da página de login */
/* Alvo: O container principal da página que contém as colunas do formulário */
.stApp > div > div > div.main > div.block-container {
    display: flex;
    flex-direction: column;
    justify-content: center; /* Centraliza verticalmente o conteúdo */
    align-items: center; /* Centraliza horizontalmente o bloco inteiro */
    min-height: 100vh; /* Garante que o container ocupe a altura total da viewport */
    padding-top: 0 !important; /* Reduzir padding superior para melhor centralização */
    padding-bottom: 0 !important; /* Reduzir padding inferior */
}

/* Adicionar opacidade à imagem de fundo do login SEM afetar o conteúdo */
/* A imagem de fundo é definida pela função set_background_image (geralmente no body ou html) */
/* Para dar a ela uma aparência opaca, aplicamos um overlay semi-transparente ao .stApp */
.stApp {
    background-color: rgba(0, 0, 0, 0.9); /* Camada semi-transparente sobre o fundo, ajustado para 0.9 */
    background-blend-mode: multiply; /* Mistura a cor com a imagem de fundo */
    background-size: cover; /* Garante que a imagem de fundo cubra o elemento */
    background-position: center; /* Centraliza a imagem de fundo */
    background-repeat: no-repeat; /* Evita a repetição da imagem de fundo */
    transition: background-color 0.5s ease-in-out; /* Transição suave para a cor de fundo */
}

</style>
""", unsafe_allow_html=True)


# Importar o módulo de utilitários de banco de dados (direto, pois está na mesma pasta)
try:
    import db_utils
except ImportError:
    st.error("ERRO CRÍTICO: O módulo 'db_utils' não foi encontrado. Por favor, certifique-se de que 'db_utils.py' está no mesmo diretório que 'app_main.py' e que todas as dependências estão instaladas.")
    st.stop() # Interrompe a execução do aplicativo se o db_utils não puder ser importado

# Importar followup_db_manager diretamente
import followup_db_manager

# Importar as páginas da pasta 'app_logic'
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app_logic'))

from app_logic import custo_item_page
from app_logic import analise_xml_di_page
from app_logic import detalhes_di_calculos_page
from app_logic import descricoes_page
from app_logic import calculo_portonave_page
from app_logic import followup_importacao_page
from app_logic import user_management_page
from app_logic import dashboard_page
from app_logic import notification_page
# NOVO: Importar a nova página de Frete Internacional
from app_logic import calculo_frete_internacional_page
# IMPORTANTE: Importar a nova página de análise de PDF
from app_logic import pdf_analyzer_page
# NOVO: Importar a nova página de listagem NCM
from app_logic import ncm_list_page
# NOVO: Importar a nova página de formulário de processo
from app_logic import process_form_page


# Importar as novas páginas de cálculo
from app_logic import calculo_futura_page
from app_logic import calculo_paclog_elo_page
from app_logic import calculo_fechamento_page
from app_logic import calculo_fn_transportes_page


# Configuração de logging (simplificada para Streamlit)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Autenticação e Usuário ---
def authenticate_user(username, password):
    """
    Autentica o usuário usando a função real do db_utils.
    """
    return db_utils.verify_credentials(username, password)

# --- Inicialização do Banco de Dados ---
# Este bloco agora é executado apenas uma vez, na primeira execução do script.


# --- Estado da Sessão ---
if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False
if 'user_info' not in st.session_state:
    st.session_state.user_info = None
if 'current_page' not in st.session_state:
    st.session_state.current_page = "Home"

# Mapeamento de nomes de páginas para as funções de exibição
PAGES = {
    "Home": None,
    "Dashboard": dashboard_page.show_dashboard_page,
    "Descrições": descricoes_page.show_page,
    "Listagem NCM": ncm_list_page.show_ncm_list_page,
    "Follow-up Importação": followup_importacao_page.show_page, # Aponta para a página principal de listagem
    "Importar XML DI": analise_xml_di_page.show_page,
    "Pagamentos": detalhes_di_calculos_page.show_page,
    "Custo do Processo": custo_item_page.show_page,
    "Cálculo Portonave": calculo_portonave_page.show_page,
    "Cálculo Futura": calculo_futura_page.show_calculo_futura_page,
    "Cálculo Pac Log - Elo": calculo_paclog_elo_page.show_calculo_paclog_elo_page,
    "Cálculo Fechamento": calculo_fechamento_page.show_calculo_fechamento_page,
    "Cálculo FN Transportes": calculo_fn_transportes_page.show_calculo_fn_transportes_page,
    "Cálculo Frete Internacional": calculo_frete_internacional_page.show_calculo_frete_internacional_page, 
    "Análise de Faturas/PL (PDF)": pdf_analyzer_page.show_pdf_analyzer_page,
    "Análise de Documentos": None,
    "Pagamentos Container": None,
    "Cálculo de Tributos TTCE": None,
    "Gerenciamento de Usuários": user_management_page.show_page,
    "Gerenciar Notificações": notification_page.show_admin_notification_page,
    "Formulário Processo": process_form_page.show_process_form_page, # Nova página dedicada para o formulário
}

# --- Tela de Login ---
if not st.session_state.authenticated:
    # Definir fundo para a tela de login
    login_background_image_path = os.path.join(os.path.dirname(__file__), 'assets', 'fundo_login.png')
    set_background_image(login_background_image_path)
    lb_title = st.columns(5)[2]
    with lb_title:
        
        st.subheader("Gerenciamento COMEX")
        st.markdown("---")

    lb_username = st.columns(5)[2]
    with lb_username:
        username = st.text_input("Usuário", key="login_username_input")

    lb_password = st.columns(5)[2]
    with lb_password:
        password = st.text_input("Senha", type="password", key="login_password_input")
    # Botão de Entrar   
    lb_title = st.columns(5)[2]
    with lb_title:
        if st.button("Entrar"):
            user_info = authenticate_user(username, password)
            if user_info:
                st.session_state.authenticated = True
                st.session_state.user_info = user_info
                st.success(f"Bem-vindo, {user_info['username']}!")
                # REMOVIDO: O bloco de inicialização do DB duplicado
                st.rerun()
            else:
                st.error("Usuário ou senha incorretos.")
    lb_title = st.columns(5)[2]
    with lb_title:
        st.markdown("---")
        st.markdown("---")
        st.markdown("---")
        st.markdown("---")
        st.markdown("---")
        
        
        st.markdown("**Versão da Aplicação:** 2.0.1")
        st.info("Informe as credenciais de login ao sistema para continuar.")
             
     if 'db_initialized' not in st.session_state:
        st.info("DEBUG: Iniciando verificação/criação do banco de dados.")
        data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
        
        # Tenta criar o diretório 'data' se não existir
        if not os.path.exists(data_dir):
            try:
                os.makedirs(data_dir)
                logger.info(f"Diretório de dados '{data_dir}' criado.")
                st.info(f"DEBUG: Diretório de dados '{data_dir}' criado.")
            except OSError as e:
                logger.error(f"Erro ao criar o diretório de dados '{data_dir}': {e}")
                st.error(f"ERRO: Não foi possível criar o diretório de dados em '{data_dir}'. Detalhes: {e}")
                st.session_state.db_initialized = False
                st.stop()
        else:
            st.info(f"DEBUG: Diretório de dados '{data_dir}' já existe.")
    
        st.info("DEBUG: Chamando db_utils.create_tables()...")
        tables_created_general = db_utils.create_tables()
        st.info(f"DEBUG: Resultado db_utils.create_tables(): {tables_created_general}")

    # --- NOVO: Debugging detalhado para o banco de dados 'produtos' ---
    conn_prod = db_utils.connect_db(db_utils.get_db_path("produtos"))
    if conn_prod:
        try:
            cursor_prod = conn_prod.cursor()
            # Verifica se a tabela 'produtos' existe
            cursor_prod.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='produtos';")
            if cursor_prod.fetchone():
                cursor_prod.execute("PRAGMA table_info(produtos)")
                cols_prod = [info[1] for info in cursor_prod.fetchall()]
                cursor_prod.execute("SELECT COUNT(*) FROM produtos")
                count_prod = cursor_prod.fetchone()[0]
                st.info(f"DEBUG: Tabela 'produtos' existe e possui colunas: {cols_prod}")
                st.info(f"DEBUG: Tabela 'produtos' possui {count_prod} registros.")
            else:
                st.warning("DEBUG: Tabela 'produtos' não encontrada no banco de dados. Pode haver um problema na criação.")
        except Exception as e:
            st.error(f"ERRO DEBUG: Falha ao inspecionar tabela 'produtos': {e}")
            logger.error(f"ERRO DEBUG: Falha ao inspecionar tabela 'produtos': {e}")
        finally:
            conn_prod.close()
    else:
        st.error("ERRO DEBUG: Não foi possível conectar ao DB 'produtos' para inspeção.")
        logger.error("ERRO DEBUG: Não foi possível conectar ao DB 'produtos' para inspeção.")
    # --- Fim do Debugging detalhado ---

    if tables_created_general:
        st.session_state.db_initialized = True
        logger.info("Bancos de dados e tabelas inicializados com sucesso.")
        st.success("DEBUG: Bancos de dados e tabelas inicializados com sucesso.")
    else:
        st.session_state.db_initialized = False
        logger.error("Falha ao inicializar bancos de dados e tabelas.")
        st.error("ERRO CRÍTICO: Falha ao inicializar bancos de dados e tabelas. Verifique os logs.")            

else:
    # --- Barra Lateral de Navegação (Menu) ---
    logo_sidebar_path = os.path.join(os.path.dirname(__file__), 'assets', 'Logo.png')
    if os.path.exists(logo_sidebar_path):
        st.sidebar.image(logo_sidebar_path, use_container_width=True)
    else:
        pass 

    current_username = st.session_state.get('user_info', {}).get('username', 'Convidado')
    num_notifications = notification_page.get_notification_count_for_user(current_username)

    st.sidebar.markdown(f"""
        <div style="display: flex; align-items: center; justify-content: space-between; margin-top: 10px; margin-bottom: 10px;">
            <div style="display: flex; align-items: center;">
                <span style="font-size: 1rem; font-weight: bold; color: gray;">Usuário: {current_username}</span>
            </div>
            <div style="display: flex; align-items: center; cursor: pointer;">
                <i class="fa-solid fa-bell" style="font-size: 1.2rem; color: yellow; margin-right: 5px;"></i>
                <span style="font-size: 1rem; font-weight: bold; color: yellow;">{num_notifications}</span>
            </div>
        </div>
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
    """, unsafe_allow_html=True)

    sidebar_background_image_path = os.path.join(os.path.dirname(__file__), 'assets', 'logo_navio_atracado.png')
    set_sidebar_background_image(sidebar_background_image_path, opacity=0.6)

    def navigate_to(page_name, **kwargs):
        st.session_state.current_page = page_name
        # Passar argumentos extras para a próxima página através do session_state
        for key, value in kwargs.items():
            st.session_state[key] = value
        st.rerun()

    # Menu "Início"
    if st.sidebar.button("Tela Inicial", key="menu_home", use_container_width=True):
        navigate_to("Home")
    # Menu "Dashboard"
    if st.sidebar.button("Dashboard", key="menu_dashboard", use_container_width=True):
        navigate_to("Dashboard")
    # Menu "Descrições"
    if st.sidebar.button("Descrições", key="menu_descricoes", use_container_width=True):
        navigate_to("Descrições")
    # Menu "Listagem NCM" (em desenvolvimento)
    if st.sidebar.button("Listagem NCM", key="menu_ncm", use_container_width=True):
        navigate_to("Listagem NCM")
    # Menu "Follow-up"
    if st.sidebar.button("Follow-up Importação", key="menu_followup", use_container_width=True):
        navigate_to("Follow-up Importação")
    # Menu "Registros"
    st.sidebar.subheader("Registros")
    if st.sidebar.button("Importar XML DI", key="menu_xml_di", use_container_width=True):
        navigate_to("Importar XML DI")
    if st.sidebar.button("Cálculos para Pagamentos", key="menu_pagamentos", use_container_width=True):
        navigate_to("Pagamentos")
    if st.sidebar.button("Custo do Processo", key="menu_custo_processo", use_container_width=True):
        navigate_to("Custo do Processo")
    
    
    # NOVO: Botão para Cálculo Frete Internacional
    if st.sidebar.button("Cálculo Frete Internacional", key="menu_frete_internacional", use_container_width=True):
        navigate_to("Cálculo Frete Internacional")
    # IMPORTANTE: Botão para a nova página de Análise de Faturas/PL (PDF)
    if st.sidebar.button("Análise de Faturas/PL (PDF)", key="menu_pdf_analyzer", use_container_width=True):
        navigate_to("Análise de Faturas/PL (PDF)")

    # Menu "Telas em desenvolvimento"
    st.sidebar.subheader("Telas em desenvolvimento")
    if st.sidebar.button("Análise de Documentos", key="menu_analise_documentos", use_container_width=True):
        navigate_to("Análise de Documentos")
    if st.sidebar.button("Pagamentos Container", key="menu_pagamento_container", use_container_width=True):
        navigate_to("Pagamentos Container")
    if st.sidebar.button("Cálculo de Tributos TTCE", key="menu_ttce_api", use_container_width=True):
        navigate_to("Cálculo de Tributos TTCE")

    # Menu "Administrador" (visível apenas para admin)
    if st.session_state.user_info and st.session_state.user_info.get('is_admin'):
        st.sidebar.subheader("Administrador")
        if st.sidebar.button("Gerenciamento de Usuários", key="menu_user_management", use_container_width=True):
            navigate_to("Gerenciamento de Usuários")
        if st.sidebar.button("Gerenciar Notificações", key="menu_manage_notifications", use_container_width=True):
            navigate_to("Gerenciar Notificações")
        
        st.sidebar.markdown("---")
        st.sidebar.write("Seleção de Bancos (simulada)")
        if st.sidebar.button("Selecionar Banco Produtos...", key="select_db_produtos", use_container_width=True):
            st.sidebar.info("Funcionalidade de seleção de DB simulada.")
        if st.sidebar.button("Selecionar Banco NCM...", key="select_db_ncm", use_container_width=True):
            st.sidebar.info("Funcionalidade de seleção de DB simulada.")

    # Botão de Sair
    st.sidebar.markdown("---")
    if st.sidebar.button("Sair", key="logout_button", use_container_width=True):
        st.session_state.authenticated = False
        st.session_state.user_info = None
        st.session_state.current_page = "Home"
        st.rerun()

    # --- Conteúdo Principal (Baseado na Página Selecionada) ---
    st.markdown("---")

    with st.container():
        if st.session_state.current_page == "Home":
            background_image_path = os.path.join(os.path.dirname(__file__), 'assets', 'logo_navio_atracado.png')
            set_background_image(background_image_path, opacity=0.5)

            st.header("Bem-vindo ao Gerenciamento COMEX")
            st.write("Use o menu lateral para navegar.")
            
            st.subheader("Cotação do Dólar (USD) - Hoje")
            dolar_data = get_dolar_cotacao()
            
            if dolar_data:
                col1, col2, col3, col4, col5, col6 = st.columns(6)
                
                with col1:
                    st.metric(label="Dólar Abertura Compra 💸", value=dolar_data['abertura_compra'])
                    st.metric(label="Dólar Abertura Venda 💸", value=dolar_data['abertura_venda'])
                
                with col2:
                    st.metric(label="Dólar PTAX Compra 🪙", value=dolar_data['ptax_compra'])
                    st.metric(label="Dólar PTAX Venda 🪙", value=dolar_data['ptax_venda'])
            else:
                st.warning("Não foi possível carregar a cotação do dólar. Verifique sua conexão ou tente mais tarde.")
            
            st.markdown("---")

            current_username = st.session_state.get('user_info', {}).get('username', 'Desconhecido')
            notification_page.display_notifications_on_home(current_username)
            st.markdown("---")
            
            st.write(f"Versão da Aplicação: {st.session_state.get('app_version', '2.0.1')}")
            st.write("Status dos Bancos de Dados:")
            if st.session_state.get('db_initialized', False):
                st.success("- Bancos de dados inicializados e conectados.")
            else:
                st.error("- Falha na conexão/inicialização dos bancos de dados.")
            
            st.info("DEBUG: Módulo 'db_utils' real importado com sucesso.")

        elif st.session_state.current_page == "Dashboard":
            dashboard_page.show_dashboard_page()

        elif st.session_state.current_page in PAGES and PAGES[st.session_state.current_page] is not None:
            if st.session_state.current_page in ["Análise de Documentos", "Pagamentos Container", "Cálculo de Tributos TTCE"]:
                st.warning(f"Tela de {st.session_state.current_page} (em desenvolvimento)")
            
            # Se a página atual é "Formulário Processo", chame-a com os dados do session_state
            if st.session_state.current_page == "Formulário Processo":
                process_form_page.show_process_form_page(
                    st.session_state.get('form_process_identifier'),
                    st.session_state.get('form_reload_processes_callback')
                )
            else:
                PAGES[st.session_state.current_page]()
        else:
            st.info(f"Página '{st.session_state.current_page}' em desenvolvimento ou não encontrada.")
