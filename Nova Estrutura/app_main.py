import streamlit as st
import os
import sys
import logging
import sqlite3 # Importar sqlite3 para manipulação de arquivos de DB

# st.set_page_config() DEVE SER A PRIMEIRA CHAMADA STREAMLIT NO SCRIPT
st.set_page_config(layout="wide", page_title="Gerenciamento COMEX")

# Importar o módulo de utilitários de banco de dados (assumindo que db_utils existe e é acessível)
# Você precisaria ter um arquivo db_utils.py no mesmo nível ou em um pacote configurado.
# Para este exemplo, vamos simular algumas funções básicas de db_utils.
try:
    import db_utils
except ImportError:
    # Simulação de db_utils para que o app_main possa rodar independentemente
    # Se você tiver um db_utils real, remova esta simulação.
    class MockDbUtils:
        def verify_credentials(self, username, password):
            # Credenciais de teste
            if username == "admin" and password == "admin":
                return {"username": "admin", "is_admin": True}
            elif username == "user" and password == "password":
                return {"username": "user", "is_admin": False}
            return None

        def create_tables(self):
            # Simula a criação de tabelas
            logging.info("Simulando criação de tabelas gerais.")
            # Para depuração, vamos simular a criação e verificar se o arquivo existe
            try:
                # Tentar criar alguns arquivos .db para simular
                db_names = ["produtos", "xml_di", "ncm", "pagamentos", "users"]
                for db_name in db_names:
                    db_path = self.get_db_path(db_name)
                    # Forçar a remoção do arquivo se ele não for um DB válido ou estiver corrompido
                    if os.path.exists(db_path):
                        try:
                            # Tentar abrir como DB para verificar integridade
                            conn_check = sqlite3.connect(db_path)
                            conn_check.close()
                        except sqlite3.Error:
                            # Se não for um DB válido, remover
                            os.remove(db_path)
                            logging.warning(f"Arquivo '{db_path}' não é um DB SQLite válido, removido.")
                            st.warning(f"DEBUG: Arquivo '{db_path}' não é um DB SQLite válido, removido.")
                    
                    # Criar o DB se não existir ou foi removido
                    conn = sqlite3.connect(db_path)
                    conn.close()
                    logging.info(f"Simulando criação de tabela para {db_name}.db.")
                return True
            except Exception as e:
                logging.error(f"Erro na simulação de criação de tabelas: {e}")
                st.error(f"ERRO SIMULADO DB: {e}")
                return False

        def create_user_table(self):
            # Simula a criação da tabela de usuários
            logging.info("Simulando criação da tabela de usuários.")
            # A criação real da tabela de usuários seria aqui, usando sqlite3.connect e cursor.execute
            return True
        
        def get_db_path(self, db_name):
            # Simula o caminho do DB, ajustando para o diretório 'data'
            _base_path = os.path.dirname(os.path.abspath(__file__))
            _app_root_path = os.path.dirname(_base_path) if os.path.basename(_base_path) == 'app_logic' else _base_path
            _DEFAULT_DB_FOLDER = "data"
            return os.path.join(_app_root_path, _DEFAULT_DB_FOLDER, f"{db_name}.db")
        
        def connect_db(self, db_path):
            try:
                conn = sqlite3.connect(db_path)
                conn.row_factory = sqlite3.Row
                return conn
            except Exception as e:
                logging.error(f"Erro ao conectar ao DB em {db_path}: {e}")
                return None


    db_utils = MockDbUtils()
    logging.warning("Módulo 'db_utils' não encontrado. Usando simulação para desenvolvimento.")
    st.info("DEBUG: Módulo 'db_utils' não encontrado, usando simulação. Se você tem um 'db_utils.py' real, verifique o caminho.")


# Configuração de logging (simplificada para Streamlit)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Simulação de Autenticação e Usuário ---
def authenticate_user(username, password):
    """
    Autentica o usuário usando a função real ou simulada do db_utils.
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
            # Não continue se o diretório não puder ser criado
            st.stop() # Adicionado st.stop() para evitar que o app continue com erro crítico
    else:
        st.info(f"DEBUG: Diretório de dados '{data_dir}' já existe.")


    # Tenta criar as tabelas gerais e de usuário
    st.info("DEBUG: Chamando db_utils.create_tables()...")
    tables_created_general = db_utils.create_tables()
    st.info(f"DEBUG: Resultado db_utils.create_tables(): {tables_created_general}")

    st.info("DEBUG: Chamando db_utils.create_user_table()...")
    tables_created_user = db_utils.create_user_table()
    st.info(f"DEBUG: Resultado db_utils.create_user_table(): {tables_created_user}")


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
# Para este exemplo, assumimos que 'app_logic' é um subdiretório.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app_logic'))

from app_logic import custo_item_page
from app_logic import analise_xml_di_page
from app_logic import detalhes_di_calculos_page
from app_logic import descricoes_page
from app_logic import calculo_portonave_page
from app_logic import followup_importacao_page # NOVO: Importa a página de Follow-up Importação

# Mapeamento de nomes de páginas para as funções de exibição
PAGES = {
    "Home": None, # A página Home será tratada diretamente no app_main
    "Descrições": descricoes_page.show_page,
    "Listagem NCM": None, # Placeholder (em desenvolvimento)
    "Follow-up Importação": followup_importacao_page.show_page, # NOVO: Adiciona a página de Follow-up Importação
    "Importar XML DI": analise_xml_di_page.show_page,
    "Pagamentos": detalhes_di_calculos_page.show_page,
    "Custo do Processo": custo_item_page.show_page,
    "Cálculo Portonave": calculo_portonave_page.show_page,
    "Análise de Documentos": None, # Placeholder (em desenvolvimento)
    "Pagamentos Container": None, # Placeholder (em desenvolvimento)
    "Cálculo de Tributos TTCE": None, # Placeholder (em desenvolvimento)
    "Gerenciamento de Usuários": None, # Placeholder (em desenvolvimento)
}

# --- Layout da Aplicação Streamlit ---
# st.set_page_config(layout="wide", page_title="Gerenciamento COMEX") # MOVIDO PARA O TOPO

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
    st.sidebar.title("Menu Principal")
    st.sidebar.markdown(f"**Usuário:** {st.session_state.user_info['username']}")
    st.sidebar.markdown(f"**Admin:** {'Sim' if st.session_state.user_info['is_admin'] else 'Não'}")

    # Menu "Início"
    if st.sidebar.button("Tela Inicial", key="menu_home"):
        navigate_to("Home")

    # Menu "Descrições"
    if st.sidebar.button("Descrições", key="menu_descricoes"):
        navigate_to("Descrições")

    # Menu "Listagem NCM" (em desenvolvimento)
    if st.sidebar.button("Listagem NCM", key="menu_ncm"):
        st.sidebar.warning("Tela de Listagem NCM (em desenvolvimento)")
        # navigate_to("Listagem NCM") # Descomente quando a página for criada

    # Menu "Follow-up"
    if st.sidebar.button("Follow-up Importação", key="menu_followup"):
        navigate_to("Follow-up Importação")

    # Menu "Registros"
    st.sidebar.subheader("Registros")
    if st.sidebar.button("Importar XML DI", key="menu_xml_di"):
        navigate_to("Importar XML DI")
    if st.sidebar.button("Pagamentos", key="menu_pagamentos"):
        navigate_to("Pagamentos")
    if st.sidebar.button("Custo do Processo", key="menu_custo_processo"):
        navigate_to("Custo do Processo")
    
    # Menu "Cálculos"
    st.sidebar.subheader("Cálculos")
    if st.sidebar.button("Cálculo Portonave", key="menu_calculo_portonave"):
        navigate_to("Cálculo Portonave")

    # Menu "Telas em desenvolvimento" (mantido para itens não movidos para páginas)
    st.sidebar.subheader("Telas em desenvolvimento")
    if st.sidebar.button("Análise de Documentos", key="menu_analise_documentos"):
        st.sidebar.warning("Tela de Análise de Documentos (em desenvolvimento)")
    if st.sidebar.button("Pagamentos Container", key="menu_pagamento_container"):
        st.sidebar.warning("Tela de Pagamentos Container (em desenvolvimento)")
    if st.sidebar.button("Cálculo de Tributos TTCE", key="menu_ttce_api"):
        st.sidebar.warning("Tela de Cálculo de Tributos TTCE (em desenvolvimento)")

    # Menu "Administrador" (visível apenas para admin)
    if st.session_state.user_info['is_admin']:
        st.sidebar.subheader("Administrador")
        if st.sidebar.button("Gerenciamento de Usuários", key="menu_user_management"):
            st.sidebar.warning("Tela de Gerenciamento de Usuários (em desenvolvimento)")
        
        st.sidebar.markdown("---")
        st.sidebar.write("Seleção de Bancos (simulada)")
        if st.sidebar.button("Selecionar Banco Produtos...", key="select_db_produtos"):
            st.sidebar.info("Funcionalidade de seleção de DB simulada.")
        if st.sidebar.button("Selecionar Banco NCM...", key="select_db_ncm"):
            st.sidebar.info("Funcionalidade de seleção de DB simulada.")
        # ... adicione outros botões de seleção de DB

    # Botão de Sair
    st.sidebar.markdown("---")
    if st.sidebar.button("Sair", key="logout_button"):
        st.session_state.authenticated = False
        st.session_state.user_info = None
        st.session_state.current_page = "Home"
        st.rerun()

    # --- Conteúdo Principal (Baseado na Página Selecionada) ---
    st.markdown("---") # Separador visual

    if st.session_state.current_page == "Home":
        st.header("Bem-vindo ao Gerenciamento COMEX (Streamlit)")
        st.write("Use o menu lateral para navegar entre as seções da aplicação.")
        # Usando um placeholder para a imagem do logo
        st.image("https://placehold.co/600x300/2E2E2E/EAEAEA?text=Logo+da+Empresa", caption="Logo da Empresa (Placeholder)")
        st.write(f"Versão da Aplicação: {st.session_state.get('app_version', '1.0.0')}")
        st.write("Status dos Bancos de Dados:")
        if st.session_state.db_initialized:
            st.success("- Bancos de dados inicializados e conectados.")
        else:
            st.error("- Falha na conexão/inicialização dos bancos de dados.")
        
        # Adicione mais informações de status de DB se desejar
        # st.write("- DB Produtos: Conectado")
        # st.write("- DB NCM: Conectado")
        # st.write("- DB XML DI: Conectado")

    elif st.session_state.current_page in PAGES and PAGES[st.session_state.current_page] is not None:
        # Chama a função show_page() da página selecionada
        PAGES[st.session_state.current_page]()
    else:
        st.info(f"Página '{st.session_state.current_page}' em desenvolvimento ou não encontrada.")

