import streamlit as st
import os
import sys
import logging
import sqlite3 # Importar sqlite3 para manipulação de arquivos de DB
import hashlib # Necessário para hash de senha, mesmo com db_utils real
import base64 # Importar base64 para codificar imagens

# st.set_page_config() DEVE SER A PRIMEIRA CHAMADA STREAMLIT NO SCRIPT
st.set_page_config(layout="wide", page_title="Gerenciamento COMEX")

# Injetar CSS personalizado para ocultar o botão de fullscreen das imagens
st.markdown("""
<style>
/* Oculta o botão de fullscreen que aparece ao passar o mouse sobre as imagens */
button[title="View fullscreen"] {
    display: none !important; /* Adicionado !important para forçar a ocultação */
}
/* Ajustes para reduzir o espaço ao redor da logo da sidebar */
[data-testid="stSidebarUserContent"] {
    padding-top: 0px !important; /* Reduz o padding superior do conteúdo da sidebar */
}
[data-testid="stSidebarUserContent"] img {
    margin-top: -75px; /* Move a imagem para cima */
    margin-bottom: -50px; /* Reduz o espaço abaixo da imagem */
}
</style>
""", unsafe_allow_html=True)


# Importar o módulo de utilitários de banco de dados
try:
    import db_utils
except ImportError:
    st.error("ERRO CRÍTICO: O módulo 'db_utils' não foi encontrado. Por favor, certifique-se de que 'db_utils.py' está no diretório 'app_logic' ou na raiz do projeto e que todas as dependências estão instaladas.")
    st.stop() # Interrompe a execução do aplicativo se o db_utils não puder ser importado

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
# Garante que as tabelas existam ao iniciar o aplicativo
if 'db_initialized' not in st.session_state:
    st.info("DEBUG: Iniciando verificação/criação do banco de dados.")
    # Tenta criar o diretório 'data' se não existir
    data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
    if not os.path.exists(data_dir):
        try:
            os.makedirs(data_dir)
            logger.info(f"Diretório de dados '{data_dir}' criado.")
            st.info(f"DEBUG: Diretório de dados '{data_dir}' criado.")
        except OSError as e:
            logger.error(f"Erro ao criar o diretório de dados '{data_dir}': {e}")
            st.error(f"ERRO: Não foi possível criar o diretório de dados em '{data_dir}'. Detalhes: {e}")
            st.session_state.db_initialized = False
            st.stop() # Adicionado st.stop() para evitar que o app continue com erro crítico
    else:
        st.info(f"DEBUG: Diretório de dados '{data_dir}' já existe.")

    # Tenta criar as tabelas gerais e de usuário
    st.info("DEBUG: Chamando db_utils.create_tables()...")
    tables_created_general = db_utils.create_tables()
    st.info(f"DEBUG: Resultado db_utils.create_tables(): {tables_created_general}")

    tables_created_user = True # Assumimos que create_tables() já cuidou da tabela de usuários

    if tables_created_general and tables_created_user:
        st.session_state.db_initialized = True
        logger.info("Bancos de dados e tabelas inicializados com sucesso.")
        st.success("DEBUG: Bancos de dados e tabelas inicializados com sucesso.")
    else:
        st.session_state.db_initialized = False
        logger.error("Falha ao inicializar bancos de dados e tabelas.")
        st.error("ERRO CRÍTICO: Falha ao inicializar bancos de dados e tabelas. Verifique os logs.")

# --- Estado da Sessão ---
# Inicializa as variáveis de estado da sessão se ainda não existirem
if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False
if 'user_info' not in st.session_state:
    st.session_state.user_info = None
if 'current_page' not in st.session_state:
    st.session_state.current_page = "Home" # Página inicial padrão

# --- Funções de Navegação ---
def navigate_to(page_name):
    """
    Define a página atual no estado da sessão e força um rerun para mudar de página.
    """
    st.session_state.current_page = page_name
    st.rerun()

# --- Páginas (Módulos) ---
# Importa as funções que representam suas "views" do diretório 'app_logic'
# Certifique-se de que o diretório 'app_logic' está no PYTHONPATH ou no mesmo diretório.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app_logic'))

from app_logic import custo_item_page
from app_logic import analise_xml_di_page
from app_logic import detalhes_di_calculos_page
from app_logic import descricoes_page
from app_logic import calculo_portonave_page
from app_logic import followup_importacao_page
from app_logic import user_management_page # Importa a página de Gerenciamento de Usuários
from app_logic import dashboard_page # Importa a nova página de Dashboard
# from app_logic import notification_page # Removido o import global, será feito na Home

# Mapeamento de nomes de páginas para as funções de exibição
PAGES = {
    "Home": None, # A página Home será tratada diretamente no app_main
    "Dashboard": dashboard_page.show_dashboard_page,
    "Descrições": descricoes_page.show_page,
    "Listagem NCM": None, # Placeholder (em desenvolvimento)
    "Follow-up Importação": followup_importacao_page.show_page,
    "Importar XML DI": analise_xml_di_page.show_page,
    "Pagamentos": detalhes_di_calculos_page.show_page,
    "Custo do Processo": custo_item_page.show_page,
    "Cálculo Portonave": calculo_portonave_page.show_page,
    "Análise de Documentos": None, # Placeholder (em desenvolvimento)
    "Pagamentos Container": None, # Placeholder (em desenvolvimento)
    "Cálculo de Tributos TTCE": None, # Placeholder (em desenvolvimento)
    "Gerenciamento de Usuários": user_management_page.show_page,
    # "Central de Notificações": notification_page.show_page, # Removido do menu lateral
}

# --- Tela de Login ---
if not st.session_state.authenticated:
    st.title("Login - Gerenciamento COMEX")
    username = st.text_input("Usuário")
    password = st.text_input("Senha", type="password")

    if st.button("Entrar"):
        user_info = authenticate_user(username, password)
        if user_info:
            st.session_state.authenticated = True
            st.session_state.user_info = user_info
            st.success(f"Bem-vindo, {user_info['username']}!")
            st.rerun() # Recarrega a página para mostrar a interface principal
        else:
            st.error("Usuário ou senha incorretos.")
    st.info("Use 'admin'/'admin' para o login inicial (se db_utils simulado).")
else:
    # --- Barra Lateral de Navegação (Menu) ---
    # st.sidebar.title("Menu Principal") # Removido o título "Menu Principal"
    
    # Adicionar a logo no canto superior esquerdo da barra lateral
    logo_sidebar_path = os.path.join(os.path.dirname(__file__), 'assets', 'Logo.png')
    if os.path.exists(logo_sidebar_path):
        st.sidebar.image(logo_sidebar_path, use_container_width=True)
    else:
        st.sidebar.markdown("### [Logo Superior Esquerda]")

    # Importar notification_page_module aqui para acessar o estado das notificações
    import app_logic.notification_page as notification_page_module
    num_notifications = len(st.session_state.get('notifications', []))

    st.sidebar.markdown(f"""
        <div style="display: flex; align-items: center; justify-content: space-between; margin-top: 10px; margin-bottom: 10px;">
            <div style="display: flex; align-items: center;">
                <span style="font-size: 1rem; font-weight: bold; color: white;">Usuário: {st.session_state.user_info['username']}</span>
            </div>
            <div style="display: flex; align-items: center; cursor: pointer;">
                <i class="fa-solid fa-bell" style="font-size: 1.2rem; color: yellow; margin-right: 5px;"></i>
                <span style="font-size: 1rem; font-weight: bold; color: yellow;">{num_notifications}</span>
            </div>
        </div>
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
    """, unsafe_allow_html=True)


    # Menu "Início"
    if st.sidebar.button("Tela Inicial", key="menu_home", use_container_width=True): # Ajuste de layout
        navigate_to("Home")

    # Menu "Dashboard"
    if st.sidebar.button("Dashboard", key="menu_dashboard", use_container_width=True): # Ajuste de layout
        navigate_to("Dashboard")

    # Menu "Descrições"
    if st.sidebar.button("Descrições", key="menu_descricoes", use_container_width=True): # Ajuste de layout
        navigate_to("Descrições")

    # Menu "Listagem NCM" (em desenvolvimento)
    if st.sidebar.button("Listagem NCM", key="menu_ncm", use_container_width=True): # Ajuste de layout
        navigate_to("Listagem NCM") # Navega para a página (mesmo que seja placeholder)

    # Menu "Follow-up"
    if st.sidebar.button("Follow-up Importação", key="menu_followup", use_container_width=True): # Ajuste de layout
        navigate_to("Follow-up Importação")

    # Menu "Registros"
    st.sidebar.subheader("Registros")
    if st.sidebar.button("Importar XML DI", key="menu_xml_di", use_container_width=True): # Ajuste de layout
        navigate_to("Importar XML DI")
    if st.sidebar.button("Pagamentos", key="menu_pagamentos", use_container_width=True): # Ajuste de layout
        navigate_to("Pagamentos")
    if st.sidebar.button("Custo do Processo", key="menu_custo_processo", use_container_width=True): # Ajuste de layout
        navigate_to("Custo do Processo")
    
    # Menu "Cálculos"
    st.sidebar.subheader("Cálculos")
    if st.sidebar.button("Cálculo Portonave", key="menu_calculo_portonave", use_container_width=True): # Ajuste de layout
        navigate_to("Cálculo Portonave")

    # Menu "Telas em desenvolvimento" (mantido para itens não movidos para páginas)
    st.sidebar.subheader("Telas em desenvolvimento")
    if st.sidebar.button("Análise de Documentos", key="menu_analise_documentos", use_container_width=True): # Ajuste de layout
        navigate_to("Análise de Documentos")
    if st.sidebar.button("Pagamentos Container", key="menu_pagamento_container", use_container_width=True): # Ajuste de layout
        navigate_to("Pagamentos Container")
    if st.sidebar.button("Cálculo de Tributos TTCE", key="menu_ttce_api", use_container_width=True): # Ajuste de layout
        navigate_to("Cálculo de Tributos TTCE")

    # Menu "Administrador" (visível apenas para admin)
    if st.session_state.user_info and st.session_state.user_info['is_admin']: # Condição para mostrar a seção Admin
        st.sidebar.subheader("Administrador") # Manter o subheader para a seção
        if st.sidebar.button("Gerenciamento de Usuários", key="menu_user_management", use_container_width=True): # Ajuste de layout
            navigate_to("Gerenciamento de Usuários")
        
        st.sidebar.markdown("---")
        st.sidebar.write("Seleção de Bancos (simulada)")
        if st.sidebar.button("Selecionar Banco Produtos...", key="select_db_produtos", use_container_width=True): # Ajuste de layout
            st.sidebar.info("Funcionalidade de seleção de DB simulada.")
        if st.sidebar.button("Selecionar Banco NCM...", key="select_db_ncm", use_container_width=True): # Ajuste de layout
            st.sidebar.info("Funcionalidade de seleção de DB simulada.")

    # Botão de Sair
    st.sidebar.markdown("---")
    if st.sidebar.button("Sair", key="logout_button", use_container_width=True): # Ajuste de layout
        st.session_state.authenticated = False
        st.session_state.user_info = None
        st.session_state.current_page = "Home"
        st.rerun()

    # --- Conteúdo Principal (Baseado na Página Selecionada) ---
    st.markdown("---") # Separador visual

    if st.session_state.current_page == "Home":
        st.header("Bem-vindo ao Gerenciamento COMEX") # Título alterado
        st.write("Use o menu lateral para navegar.") # Texto alterado

        # Usando a logo da empresa na tela inicial
        logo_main_path = os.path.join(os.path.dirname(__file__), 'assets', 'Logo_empresa.png')
        if os.path.exists(logo_main_path):
            st.image(logo_main_path, width=400) # Ajuste de tamanho para a logo principal
        else:
            st.image("https://placehold.co/400x200/2E2E2E/EAEAEA?text=Logo+da+Empresa", width=400) # Ajuste de tamanho para a logo principal
        
        # Central de Notificações
        notification_page_module.display_notifications_on_home() # Chamada da função sem subheader
        st.markdown("---") # Separador após notificações
        
        st.write(f"Versão da Aplicação: {st.session_state.get('app_version', '1.0.0')}")
        st.write("Status dos Bancos de Dados:")
        if st.session_state.db_initialized:
            st.success("- Bancos de dados inicializados e conectados.")
        else:
            st.error("- Falha na conexão/inicialização dos bancos de dados.")
        
        # Debug abaixo dos status dos bancos de dados
        st.info("DEBUG: Módulo 'db_utils' real importado com sucesso.")

    elif st.session_state.current_page in PAGES and PAGES[st.session_state.current_page] is not None:
        # Verifica se a página é uma das "em desenvolvimento" e exibe o aviso
        if st.session_state.current_page in ["Listagem NCM", "Análise de Documentos", "Pagamentos Container", "Cálculo de Tributos TTCE"]:
            st.warning(f"Tela de {st.session_state.current_page} (em desenvolvimento)")
        
        # Chama a função show_page() da página selecionada
        PAGES[st.session_state.current_page]()
    else:
        st.info(f"Página '{st.session_state.current_page}' em desenvolvimento ou não encontrada.")
