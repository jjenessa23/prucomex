import streamlit as st # st deve ser importado primeiro para set_page_config

# Configuração da página (DEVE SER A PRIMEIRA CHAMADA STREAMLIT)
st.set_page_config(layout="wide", page_title="Gerenciamento COMEX")

import os
import sys
import logging
import hashlib
import base64
from datetime import datetime
import requests # Adicionado para fazer requisições HTTP
import json # Importado para depuração de secrets.toml
import pytz # Adicionado para suporte a fuso horário de Brasília


try:
    from google.cloud import firestore
    from google.oauth2 import service_account
    import firebase_admin
    from firebase_admin import credentials
except ImportError as ie:
    logging.critical(f"APP_MAIN_DEBUG: Erro de importação: {ie}. Assegure que as bibliotecas 'google-cloud-firestore', 'google-auth' e 'firebase-admin' estão instaladas.")
    st.error(f"Erro de importação: {ie}. Assegure que as bibliotecas 'google-cloud-firestore', 'google-auth' e 'firebase-admin' estão instaladas.")
    st.session_state.firebase_ready = False # Sinaliza que Firebase não está pronto
   

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


if 'firebase_ready' not in st.session_state:
    st.session_state.firebase_ready = False # Estado inicial

if not st.session_state.firebase_ready:
    logger.info("APP_MAIN_DEBUG: Iniciando bloco de inicialização do Firebase Admin SDK e Firestore client.")
    try:
        if "firestore_service_account" not in st.secrets:
            st.error("ERRO CRÍTICO: Chave 'firestore_service_account' NÃO encontrada em st.secrets. Verifique secrets.toml.")
            logger.critical("APP_MAIN_DEBUG: 'firestore_service_account' NÃO ENCONTRADO em st.secrets. Abortando inicialização do Firebase.")
            st.session_state.firebase_ready = False
        else:
            firestore_secrets = st.secrets["firestore_service_account"]
            logger.debug(f"APP_MAIN_DEBUG: Bloco 'firestore_service_account' encontrado em st.secrets. Chaves: {list(firestore_secrets.keys())}")

            if "credentials_json" not in firestore_secrets:
                st.error("ERRO CRÍTICO: Chave 'credentials_json' NÃO encontrada dentro de 'firestore_service_account'. Verifique secrets.toml.")
                logger.critical("APP_MAIN_DEBUG: 'credentials_json' AUSENTE. Abortando inicialização do Firebase.")
                st.session_state.firebase_ready = False
            else:
                _firestore_credentials_json = firestore_secrets["credentials_json"]
                logger.debug(f"APP_MAIN_DEBUG: Comprimento de credentials_json: {len(_firestore_credentials_json)} caracteres.")

                try:
                    credentials_info = json.loads(_firestore_credentials_json)
                    logger.debug("APP_MAIN_DEBUG: JSON de credenciais PARSEADO com sucesso.")

                    if not firebase_admin._apps: # Verifica se já foi inicializado
                        cred = credentials.Certificate(credentials_info)
                        firebase_admin.initialize_app(cred)
                        logger.info("APP_MAIN_DEBUG: Firebase Admin SDK inicializado com SUCESSO!")
                    else:
                        logger.info("APP_MAIN_DEBUG: Firebase Admin SDK já estava inicializado.")

                    # Inicializa o cliente Firestore (para operações de banco de dados)
                    st.session_state.db_firestore = firestore.Client(credentials=service_account.Credentials.from_service_account_info(credentials_info), project=credentials_info['project_id'])
                    logger.info("APP_MAIN_DEBUG: Firestore client inicializado com SUCESSO!")
                    st.session_state.firebase_ready = True
                   
                    try:
                        users_ref = st.session_state.db_firestore.collection("users")
                        users_docs = users_ref.limit(1).get() # Busca apenas um documento para verificar se a coleção está vazia
                        if not list(users_docs):
                            admin_username = "admin"
                            admin_password_hash = hashlib.sha256((admin_username + admin_username).encode('utf-8')).hexdigest() # Senha 'admin', hash com username
                            all_screens_default = ["Home", "Dashboard", "Descrições", "Listagem NCM", "Follow-up Importação",
                                                   "Importar XML DI", "Pagamentos", "Custo do Processo", "Cálculo Portonave",
                                                   "Cálculo Itapoa", "Cálculo Futura", "Cálculo Pac Log - Elo", "Cálculo Fechamento",
                                                   "Cálculo FN Transportes", "Cálculo Frete Internacional",
                                                   "Análise de Faturas/PL (PDF)", "Análise de Documentos",
                                                   "Pagamentos Container", "Cálculo de Tributos TTCE",
                                                   "Gerenciamento de Usuários", "Gerenciar Notificações",
                                                   "Formulário Processo", "Clonagem de Processo", "Produtos",
                                                   "Rateios de Carga", "Gerenciar Processos em Massa", "Editar Múltiplos Processos",
                                                   "Atualizar Dados de Processo", "Ações do Processo (Popover)", # Adicionando permissão para o popover de ações
                                                   "Mais Opções (Popover)", # Adicionando permissão para o popover de mais opções
                                                   "Exportar Excel", # Adicionando permissão para exportar excel
                                                   "Testar API Portonave Lineup", # NOVO: Adicionando permissão para a nova tela de API
                                                   "Cotação de Frete Internacional", # NOVO: Permissão para a tela de cotação
                                                   "Inserir Cotação Agente"] # NOVO: Permissão para a tela de inserção de cotação do agente
                            user_data = {"username": admin_username, "password_hash": admin_password_hash, "is_admin": True, "allowed_screens": all_screens_default}
                            users_ref.document(admin_username).set(user_data)
                            logger.info("APP_MAIN_DEBUG: Usuário admin padrão 'admin' criado no Firestore.")
                        else:
                            logger.info("APP_MAIN_DEBUG: Coleção 'users' no Firestore já contém dados. Usuário admin padrão não criado.")
                    except Exception as e:
                        logger.exception(f"APP_MAIN_DEBUG: Erro ao criar/verificar usuário admin no Firestore após inicialização do cliente: {e}")
                        st.error(f"Erro ao verificar/criar usuário admin no Firestore: {e}")

                except json.JSONDecodeError as jde:
                    logger.critical(f"APP_MAIN_DEBUG: Erro CRÍTICO de DECODIFICAÇÃO JSON nas credenciais do Firestore: {jde}. Verifique a formatação em secrets.toml.")
                    st.error(f"Erro CRÍTICO na formatação JSON das credenciais do Firestore: {jde}")
                    st.session_state.firebase_ready = False
                except Exception as e:
                    logger.exception(f"APP_MAIN_DEBUG: Erro INESPERADO durante a criação do cliente Firestore/Firebase Admin SDK: {e}. Verifique permissões ou conectividade.")
                    st.error(f"Erro inesperado durante a inicialização do Firebase: {e}")
                    st.session_state.firebase_ready = False

    except Exception as e:
        logger.exception(f"APP_MAIN_DEBUG: ERRO INESPERADO ao iniciar o bloco de inicialização do Firebase: {e}")
        st.error(f"Erro geral na depuração inicial do Firebase: {e}")
        st.session_state.firebase_ready = False

# Importar funções de utilidade do novo módulo
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app_logic'))

from app_logic.utils import set_background_image, set_sidebar_background_image, get_dolar_cotacao
from app_logic import db_utils # Importar db_utils aqui após a inicialização do Firebase

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
/* Reduzir o padding dos botões na sidebar para um visual más compacto */
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

/* Ajustar o padding do main content para que o conteúdo comece más para cima */
.stApp > header {
    height: 0px !important;
}

/* Ajustar o padding do main content para que o conteúdo comece más para cima */
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

/* Ajustar o padding do conteúdo dentro da sidebar para um visual más compacto */
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

/* Ajustes para o fundo do .stApp para que o body possa ter o background de quadrados */
.stApp {
    background-color: transparent !important; /* Torna o fundo do app transparente */
    background-image: none !important; /* Remove qualquer imagem de fundo padrão */
    background-blend-mode: normal !important; /* Garante que o blend mode não atrapalhe */
    transition: none !important; /* Remove transições que podem conflitar */
}

/* Define um fundo padrão escuro para o corpo */
body {
    background-color: #1a202c; /* Cor de fundo escura padrão */
}

/* Estilo para as partículas individuais */
.particle {
    position: absolute;
    background-color: rgba(255, 255, 255, 1); /* Cor branca sólida para máxima visibilidade */
    border-radius: 50%; /* Torna as partículas circulares */
    animation-timing-function: linear; /* Animação linear */
    animation-iteration-count: infinite; /* Animação infinita */
    opacity: 0; /* Começa invisível, animado para visível */
    box-shadow: 0 0 8px rgba(255, 255, 255, 0.6); /* Adiciona um brilho más notável */
}

/* Definição das animações para as partículas */
@keyframes particle-fall {
    0% {
        transform: translateY(-50vh) translateX(0vw) scale(0.8); /* Começa acima, más visível */
        opacity: 0;
    }
    10% {
        opacity: 1; /* Atinge opacidade total más rápido */
    }
    90% {
        opacity: 1; /* Mantém opacidade total por más tempo */
        transform: translateY(150vh) translateX(50vw) scale(1.2); /* Move más para baixo e para o lado */
    }
    100% {
        transform: translateY(180vh) translateX(70vw) scale(1.5); /* Termina fora da tela, ligeiramente maior */
        opacity: 0; /* Desaparece no final */
    }
}

@keyframes particle-fade {
    0% { opacity: 0; }
    50% { opacity: 0.8; }
    100% { opacity: 0; }
}
</style>
""", unsafe_allow_html=True)

try:
    # db_utils importado após a inicialização do Firebase para garantir que st.session_state.db_firestore esteja disponível
    # e que as credenciais sejam carregadas corretamente.
    # No entanto, a importação de db_utils deve ser feita antes de usá-lo.
    # A ordem de importação é importante aqui.
    # Se db_utils.py depende de st.session_state.db_firestore, ele deve ser importado após a inicialização do Firebase.
    # Se db_utils.py inicializa o Firestore, então a lógica de inicialização do Firebase em app_main.py
    # pode ser simplificada ou removida, confiando em db_utils para isso.
    # Pelo trecho de código fornecido, db_utils.py parece inicializar o Firestore por conta própria.
    # Então, a importação aqui está ok, mas a lógica de inicialização em app_main.py precisa ser revista
    # para não duplicar ou conflitar com db_utils.py
    pass # Removendo o try/except original para db_utils, pois ele será importado abaixo
except ImportError:
    st.error("ERRO CRÍTICO: O módulo 'db_utils' não foi encontrado. Por favor, certifique-se de que 'db_utils.py' está no diretório 'app_logic' e que todas as dependências estão instaladas.")
    st.stop() # Interrompe a execução do aplicativo se o db_utils não puder ser importado
from app_logic import followup_db_manager
from app_logic import custo_item_page
from app_logic import analise_xml_di_page
from app_logic import detalhes_di_calculos_page
from app_logic import descricoes_page
from app_logic import calculo_portonave_page
from app_logic import calculo_itapoa_page
from app_logic import followup_importacao_page
from app_logic import user_management_page
from app_logic import dashboard_page
from app_logic import notification_page
from app_logic import calculo_frete_internacional_page
from app_logic import pdf_analyzer_page
from app_logic import ncm_list_page
from app_logic import process_form_page
from app_logic import produtos_page
from app_logic import clonagem_processo_page
from app_logic import process_query_page
from app_logic import vincular_consolidado_page
from app_logic import mass_process_manager_page
from app_logic import mass_edit_processes_page
from app_logic import update_process_data_page # <-- NOVA LINHA
from app_logic import portonave_lineup_page # <-- NOVA LINHA
from app_logic import calculo_futura_page
from app_logic import calculo_paclog_elo_page
from app_logic import calculo_fechamento_page
from app_logic import calculo_fn_transportes_page
from app_logic import rateios_carga_page
from app_logic import cotacao_frete
from app_logic import inserir_cotacao_agente

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Autenticação e Usuário ---
def authenticate_user(username, password):
    """
    Autentica o usuário usando a função real do db_utils.
    """
    return db_utils.verify_credentials(username, password)

data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

if not os.path.exists(data_dir):
    try:
        os.makedirs(data_dir)
        logger.info(f"Diretório de dados '{data_dir}' criado.")
    except OSError as e:
        logger.error(f"Erro ao criar o diretório de dados '{data_dir}': {e}")
        st.error(f"ERRO: Não foi possível criar o diretório de dados em '{data_dir}'. Detalhes: {e}")
        st.session_state.db_initialized = False # Define como False se a criação do dir falhar
        st.stop()
else:
    logger.info(f"Diretório de dados '{data_dir}' já existe.")


if 'db_initialized' not in st.session_state:
    st.session_state.db_initialized = db_utils.create_tables()
    if not st.session_state.get('firebase_ready', False): # Certifica que o Firebase é o ponto crítico
        logger.error("Falha na conexão inicial com Firebase. O aplicativo não pode continuar.")
        st.error("ERRO CRÍTICO: Falha na conexão inicial com Firebase. Verifique logs e secrets.toml.")
        st.stop()
    else:
        st.session_state.db_initialized = True
        logger.info("Bancos de dados e tabelas inicializados com sucesso (Firestore pronto).")


# --- Estado da Sessão ---
if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False
if 'user_info' not in st.session_state:
    st.session_state.user_info = None
if 'current_page' not in st.session_state:
    st.session_state.current_page = "Home"

# Mapeamento de nomes de páginas para as funções de exibição
PAGES = {
    "Home": None, # Home é tratada separadamente para cotação e notificações
    "Dashboard": dashboard_page.show_dashboard_page,
    "Descrições": descricoes_page.show_page,
    "Listagem NCM": ncm_list_page.show_ncm_list_page,
    "Follow-up Importação": followup_importacao_page.show_page, # Aponta para a página principal de listagem
    "Importar XML DI": analise_xml_di_page.show_page,
    "Pagamentos": detalhes_di_calculos_page.show_page,
    "Custo do Processo": custo_item_page.show_page,
    "Cálculo Portonave": calculo_portonave_page.show_page,
    "Cálculo Itapoa": calculo_itapoa_page.show_page,
    "Cálculo Futura": calculo_futura_page.show_calculo_futura_page,
    "Cálculo Pac Log - Elo": calculo_paclog_elo_page.show_calculo_paclog_elo_page,
    "Cálculo Fechamento": calculo_fechamento_page.show_calculo_fechamento_page,
    "Cálculo FN Transportes": calculo_fn_transportes_page.show_calculo_fn_transportes_page,
    "Cálculo Frete Internacional": calculo_frete_internacional_page.show_calculo_frete_internacional_page,
    "Análise de Faturas/PL (PDF)": pdf_analyzer_page.show_pdf_analyzer_page,
    "Análise de Documentos": None, # Em desenvolvimento
    "Pagamentos Container": None, # Em desenvolvimento
    "Cálculo de Tributos TTCE": None, # Em desenvolvimento
    "Gerenciamento de Usuários": user_management_page.show_page,
    "Gerenciar Notificações": notification_page.show_admin_notification_page,
    "Formulário Processo": process_form_page.show_process_form_page, # Página dedicada para o formulário de edição/criação
    "Clonagem de Processo": clonagem_processo_page.show_clonagem_processo_page, # NOVO: Página dedicada para clonagem
    "Produtos": produtos_page.show_produtos_page, # Nova página para produtos
    "Consulta de Processo": process_query_page.show_process_query_page,
    "Rateios de Carga": rateios_carga_page.show_rateios_carga_page, # ADICIONADO: Nova página de Rateios de Carga
    "Vincular Consolidado": vincular_consolidado_page.show_vincular_consolidado_page, # NOVO: Página para vincular processos consolidados
    "Gerenciar Processos em Massa": mass_process_manager_page.show_mass_process_manager_page, # NOVO: Página para gerenciar processos em massa
    "Editar Múltiplos Processos": mass_edit_processes_page.show_page, # NOVO: Página para edição em massa de processos
    "Atualizar Dados de Processo": update_process_data_page.show_update_process_data_page, # <-- NOVA LINHA
    "Testar API Portonave Lineup": portonave_lineup_page.show_portonave_lineup_page, # NOVO: Adicionando a nova tela de API
    "Cotação de Frete Internacional": cotacao_frete.show_cotacao_frete_page, # Nova tela 1
    "Inserir Cotação Agente": inserir_cotacao_agente.show_inserir_cotacao_agente_page, # Nova tela 2
}

# --- Tela de Login ---
if not st.session_state.authenticated:
    login_background_image_path = os.path.join(os.path.dirname(__file__), 'assets', 'comexwall.jpg')
    logo_sidebar_path = os.path.join(os.path.dirname(__file__), 'assets', 'Logo.png')

    if os.path.exists(login_background_image_path):
        set_background_image(login_background_image_path, opacity=1.0) # Opacidade 1.0 para imagem sólida
    else:
        logger.warning(f"Logo da sidebar não encontrada em: {logo_sidebar_path}")
        st.markdown("""
        <style>
        body {
            background-color: #1a202c; /* Cor de fundo escura padrão se a imagem falhar */
        }
        </style>
        """, unsafe_allow_html=True)


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
        
        
        st.markdown("**Versão da Aplicação:** 3.0.1")
        st.info("Informe as credenciais de login ao sistema para continuar.")
             
             
# --- Conteúdo Principal (Baseado na Página Selecionada) ---
else:
    # --- Barra Lateral de Navegação (Menu) ---
    logo_sidebar_path = os.path.join(os.path.dirname(__file__), 'assets', 'Logo.png')
    if os.path.exists(logo_sidebar_path):
        st.sidebar.image(logo_sidebar_path, use_container_width=True)
    else:
        # Se a imagem não for encontrada, exibe um placeholder ou loga um aviso
        logger.warning(f"Logo da sidebar não encontrada em: {logo_sidebar_path}")
        st.sidebar.subheader("Gerenciamento COMEX") # Fallback para texto

    current_username = st.session_state.get('user_info', {}).get('username', 'Convidado')
    
    num_notifications = 0
    if st.session_state.get('firebase_ready', False): # Verifica a flag de inicialização do Firebase
        try:
            num_notifications = notification_page.get_notification_count_for_user(current_username)
        except Exception as e:
            logger.error(f"Erro ao obter notificações: {e}")
            num_notifications = "Erro"
    else:
        num_notifications = "N/A" # Firebase não pronto

    st.sidebar.markdown(f"""
        <div style="display: flex; align-items: center; justify-content: space-between; margin-top: 10px; margin-bottom: 10px;">
            <div style="display: flex; align-items: center;">
                <span style="font-size: 1rem; font-weight: bold; color: white;">Usuário: {current_username}</span>
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

    # Get allowed screens for the current user
    allowed_screens = st.session_state.user_info.get('allowed_screens', [])
    is_admin = st.session_state.user_info.get('is_admin', False)

    # Menu "Início"
    if "Home" in allowed_screens or is_admin:
        if st.sidebar.button("Tela Inicial", key="menu_home", use_container_width=True):
            navigate_to("Home")
    # Menu "Dashboard"
    if "Dashboard" in allowed_screens or is_admin:
        if st.sidebar.button("Dashboard", key="menu_dashboard", use_container_width=True):
            navigate_to("Dashboard")
    # Menu "Descrições"
    if "Descrições" in allowed_screens or is_admin:
        if st.sidebar.button("Descrições", key="menu_descricoes", use_container_width=True):
            navigate_to("Descrições")
    # Menu "Listagem NCM" (em desenvolvimento)
    if "Listagem NCM" in allowed_screens or is_admin:
        if st.sidebar.button("Listagem NCM", key="menu_ncm", use_container_width=True):
            navigate_to("Listagem NCM")
    # Menu "Follow-up"
    if "Follow-up Importação" in allowed_screens or is_admin:
        if st.sidebar.button("Follow-up Importação", key="menu_followup", use_container_width=True):
            navigate_to("Follow-up Importação")
    # Menu "Produtos"
    if "Produtos" in allowed_screens or is_admin:
        if st.sidebar.button("Produtos", key="menu_produtos", use_container_width=True):
            navigate_to("Produtos")

    # Menu "Registros"
    # Check if any "Registros" page is allowed
    registros_pages = [
        "Importar XML DI", "Pagamentos", "Custo do Processo",
        "Cálculo Frete Internacional", "Análise de Faturas/PL (PDF)",
        "Rateios de Carga", "Vincular Consolidado", "Gerenciar Processos em Massa",
        "Editar Múltiplos Processos", "Atualizar Dados de Processo",
        "Testar API Portonave Lineup",
        "Cotação de Frete Internacional", # NOVO: Adicionando a nova tela de cotação
        "Inserir Cotação Agente" # NOVO: Adicionando a nova tela de inserção de cotação do agente
    ]
    if any(page in allowed_screens for page in registros_pages) or is_admin:
        st.sidebar.subheader("Registros")
        if "Importar XML DI" in allowed_screens or is_admin:
            if st.sidebar.button("Importar XML DI", key="menu_xml_di", use_container_width=True):
                navigate_to("Importar XML DI")
        if "Pagamentos" in allowed_screens or is_admin:
            if st.sidebar.button("Cálculos para Pagamentos", key="menu_pagamentos", use_container_width=True):
                navigate_to("Pagamentos")
        if "Custo do Processo" in allowed_screens or is_admin:
            if st.sidebar.button("Custo do Processo", key="menu_custo_processo", use_container_width=True):
                navigate_to("Custo do Processo")
        if "Cálculo Frete Internacional" in allowed_screens or is_admin:
            if st.sidebar.button("Cálculo Frete Internacional", key="menu_frete_internacional", use_container_width=True):
                navigate_to("Cálculo Frete Internacional")
        if "Análise de Faturas/PL (PDF)" in allowed_screens or is_admin:
            if st.sidebar.button("Análise de Faturas/PL (PDF)", key="menu_pdf_analyzer", use_container_width=True):
                navigate_to("Análise de Faturas/PL (PDF)")
        if "Rateios de Carga" in allowed_screens or is_admin:
            if st.sidebar.button("Rateios de Carga", key="menu_rateios_carga", use_container_width=True):
                navigate_to("Rateios de Carga")
        if "Vincular Consolidado" in allowed_screens or is_admin:
            if st.sidebar.button("Vincular Consolidado", key="menu_vincular_consolidado", use_container_width=True):
                navigate_to("Vincular Consolidado")
        if "Gerenciar Processos em Massa" in allowed_screens or is_admin:
            if st.sidebar.button("Gerenciar Processos em Massa", key="menu_mass_process_manager", use_container_width=True):
                navigate_to("Gerenciar Processos em Massa", mass_process_manager_reload_callback=followup_importacao_page._fetch_initial_processes)
        if "Editar Múltiplos Processos" in allowed_screens or is_admin:
            if st.sidebar.button("Editar Múltiplos Processos", key="menu_mass_edit_processes", use_container_width=True):
                navigate_to("Editar Múltiplos Processos", mass_edit_processes_reload_callback=followup_importacao_page._fetch_initial_processes)
        if "Atualizar Dados de Processo" in allowed_screens or is_admin: # <-- VERIFICA PERMISSÃO
            if st.sidebar.button("Atualizar Dados de Processo", key="menu_update_process_data", use_container_width=True):
                navigate_to("Atualizar Dados de Processo")
        if "Testar API Portonave Lineup" in allowed_screens or is_admin: # <-- VERIFICA PERMISSÃO
            if st.sidebar.button("Testar API Portonave Lineup", key="menu_portonave_api_lineup", use_container_width=True):
                navigate_to("Testar API Portonave Lineup")
        if "Cotação de Frete Internacional" in allowed_screens or is_admin:
            if st.sidebar.button("Cotação de Frete Internacional", key="menu_cotacao_frete", use_container_width=True):
                navigate_to("Cotação de Frete Internacional")
        if "Inserir Cotação Agente" in allowed_screens or is_admin:
            if st.sidebar.button("Inserir Cotação Agente", key="menu_inserir_cotacao_agente", use_container_width=True):
                navigate_to("Inserir Cotação Agente")


    # Menu "Telas em desenvolvimento"
    development_pages = [
        "Análise de Documentos", "Pagamentos Container", "Cálculo de Tributos TTCE"
    ]
    if any(page in allowed_screens for page in development_pages) or is_admin:
        st.sidebar.subheader("Telas em desenvolvimento")
        if "Análise de Documentos" in allowed_screens or is_admin:
            if st.sidebar.button("Análise de Documentos", key="menu_analise_documentos", use_container_width=True):
                navigate_to("Análise de Documentos")
        if "Pagamentos Container" in allowed_screens or is_admin:
            if st.sidebar.button("Pagamentos Container", key="menu_pagamento_container", use_container_width=True):
                navigate_to("Pagamentos Container")
        if "Cálculo de Tributos TTCE" in allowed_screens or is_admin:
            if st.sidebar.button("Cálculo de Tributos TTCE", key="menu_ttce_api", use_container_width=True):
                navigate_to("Cálculo de Tributos TTCE")

    # Menu "Administrador" (visível apenas para admin)
    if st.session_state.user_info and st.session_state.user_info.get('is_admin'):
        st.sidebar.subheader("Administrador")
        if "Gerenciamento de Usuários" in allowed_screens or is_admin: # Admin pages also check explicit permission
            if st.sidebar.button("Gerenciamento de Usuários", key="menu_user_management", use_container_width=True):
                navigate_to("Gerenciamento de Usuários")
        if "Gerenciar Notificações" in allowed_screens or is_admin: # Admin pages also check explicit permission
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
    
    with st.container():
        if st.session_state.current_page == "Home":
            background_image_path = os.path.join(os.path.dirname(__file__), 'assets', 'logo_navio_atracado.png')
            set_background_image(background_image_path, opacity=0.5)

            st.header("Bem-vindo ao Gerenciamento COMEX")
            st.write("Use o menu lateral para navegar.")
            
            st.subheader("Cotação do Dólar (USD)")
            
            # Configurar timezone de Brasília
            brasilia_tz = pytz.timezone('America/Sao_Paulo')  # GMT-3 (ou GMT-2 no horário de verão)
            now_brasilia = datetime.now(brasilia_tz)
            
            # Buscar cotação atual da API
            dolar_data_api = get_dolar_cotacao()
            
            # Buscar última cotação do banco de dados para cada tipo de dólar (agora mais robusta)
            latest_dolar_cotacoes_db = {}
            if st.session_state.get('firebase_ready', False):
                latest_dolar_cotacoes_db = db_utils.get_latest_dolar_cotacao_from_db()
            
            # Dicionário para armazenar os valores finais e suas datas/timestamps
            cotacoes_para_exibir = {
                'abertura_compra': {'valor': 'N/A', 'data_fmt': 'N/A', 'fonte': 'N/A', 'timestamp': None},
                'abertura_venda': {'valor': 'N/A', 'data_fmt': 'N/A', 'fonte': 'N/A', 'timestamp': None},
                'ptax_compra': {'valor': 'N/A', 'data_fmt': 'N/A', 'fonte': 'N/A', 'timestamp': None},
                'ptax_venda': {'valor': 'N/A', 'data_fmt': 'N/A', 'fonte': 'N/A', 'timestamp': None},
            }
            
            api_fetch_successful_for_all = True # Flag para indicar se a API forneceu dados válidos para *todos* os tipos

            # 1. Tentar obter da API e salvar no banco de dados
            if dolar_data_api:
                for key in cotacoes_para_exibir.keys():
                    api_value = dolar_data_api.get(key)
                    # Verifica se o valor da API é válido e não vazio
                    if api_value is not None and str(api_value).strip() != '':
                        try:
                            # Substitui a vírgula por ponto antes de converter para float
                            float_api_value = float(str(api_value).replace(',', '.'))
                            cotacoes_para_exibir[key]['valor'] = float_api_value
                            cotacoes_para_exibir[key]['data_fmt'] = now_brasilia.strftime('%d/%m/%Y %H:%M')
                            cotacoes_para_exibir[key]['fonte'] = "API"
                            cotacoes_para_exibir[key]['timestamp'] = now_brasilia.isoformat()
                            
                            # Salvar no banco de dados, se o valor da API for válido
                            if st.session_state.get('firebase_ready', False):
                                db_utils.save_dolar_cotacao_daily(key, float_api_value, now_brasilia.isoformat())
                        except ValueError:
                            api_fetch_successful_for_all = False # Marcar como falha se um valor da API não for numérico
                            logger.warning(f"Valor da API para '{key}' não é numérico: '{api_value}'.")
                    else:
                        api_fetch_successful_for_all = False # Marcar como falha se um valor da API for None ou vazio
            else:
                api_fetch_successful_for_all = False # Se dolar_data_api é None, a API falhou completamente

            # 2. Se o valor ainda é 'N/A' (não veio da API ou era inválido da API), tentar do banco de dados
            # Este loop agora se beneficia do `get_latest_dolar_cotacao_from_db` mais robusto
            for key in cotacoes_para_exibir.keys():
                if not isinstance(cotacoes_para_exibir[key]['valor'], float): # Se ainda não é um float (ou seja, é 'N/A')
                    if key in latest_dolar_cotacoes_db:
                        db_entry = latest_dolar_cotacoes_db[key]
                        
                        # O db_utils.get_latest_dolar_cotacao_from_db já deve ter garantido que db_entry['valor'] é float
                        cotacoes_para_exibir[key]['valor'] = db_entry['valor']
                        
                        data_timestamp_db = db_entry.get('timestamp')
                        if isinstance(data_timestamp_db, str) and data_timestamp_db.strip() != '':
                            try:
                                # Tenta parsear como ISO format (com ou sem timezone)
                                if 'T' in data_timestamp_db or '+' in data_timestamp_db or 'Z' in data_timestamp_db:
                                    data_obj = datetime.fromisoformat(data_timestamp_db.replace('Z', '+00:00'))
                                else: # Tenta parsear como AAAA-MM-DD se não tiver T ou +
                                    data_obj = datetime.strptime(data_timestamp_db, '%Y-%m-%d')
                                
                                # Converte para o fuso horário de Brasília se não tiver timezone ou se tiver
                                data_obj_brasilia = data_obj.astimezone(brasilia_tz) if data_obj.tzinfo else brasilia_tz.localize(data_obj)
                                cotacoes_para_exibir[key]['data_fmt'] = data_obj_brasilia.strftime('%d/%m/%Y %H:%M')
                                cotacoes_para_exibir[key]['fonte'] = f"Banco ({data_obj_brasilia.strftime('%d/%m/%Y')})" # Indica a data do banco
                                cotacoes_para_exibir[key]['timestamp'] = data_timestamp_db
                            except Exception as e:
                                logger.warning(f"Erro ao processar timestamp da cotação do banco para {key} ('{data_timestamp_db}'): {e}")
                                cotacoes_para_exibir[key]['data_fmt'] = "Data inválida"
                                cotacoes_para_exibir[key]['fonte'] = "Banco (Data inválida)"
                        else:
                            cotacoes_para_exibir[key]['data_fmt'] = "Sem data"
                            cotacoes_para_exibir[key]['fonte'] = "Banco (Sem data)"
            
            # Exibir as cotações
            # Verifica se pelo menos um valor de cotação é diferente de 'N/A' (ou seja, foi preenchido com um float)
            if any(isinstance(c['valor'], float) for c in cotacoes_para_exibir.values()):
                st.info(f"💰 Cotações do dólar mais recentes:")
                
                col1, col2, col3, col4 = st.columns(4)
                
                with col1:
                    st.metric(
                        label="Dólar Abertura Compra �", 
                        value=f"{cotacoes_para_exibir['abertura_compra']['valor']:.4f}" if isinstance(cotacoes_para_exibir['abertura_compra']['valor'], float) else "N/A",
                        help=f"Última atualização: {cotacoes_para_exibir['abertura_compra']['fonte']}"
                    )
                
                with col2:
                    st.metric(
                        label="Dólar Abertura Venda 💹", 
                        value=f"{cotacoes_para_exibir['abertura_venda']['valor']:.4f}" if isinstance(cotacoes_para_exibir['abertura_venda']['valor'], float) else "N/A",
                        help=f"Última atualização: {cotacoes_para_exibir['abertura_venda']['fonte']}"
                    )
                
                with col3:
                    st.metric(
                        label="Dólar PTAX Compra 📊",
                        value=f"{cotacoes_para_exibir['ptax_compra']['valor']:.4f}" if isinstance(cotacoes_para_exibir['ptax_compra']['valor'], float) else "N/A",
                        help=f"Última atualização: {cotacoes_para_exibir['ptax_compra']['fonte']}"
                    )
                
                with col4:
                    st.metric(
                        label="Dólar PTAX Venda 📈",
                        value=f"{cotacoes_para_exibir['ptax_venda']['valor']:.4f}" if isinstance(cotacoes_para_exibir['ptax_venda']['valor'], float) else "N/A",
                        help=f"Última atualização: {cotacoes_para_exibir['ptax_venda']['fonte']}"
                    )
                
                # Mostrar status da atualização
                if api_fetch_successful_for_all:
                    st.success(f"✅ Cotação atualizada com sucesso para {now_brasilia.strftime('%d/%m/%Y às %H:%M')} (Horário de Brasília) via API.")
                else:
                    st.warning(f"⚠️ Não foi possível obter cotação atual completa da API. Exibindo últimas cotações válidas disponíveis (pode incluir dados de dias anteriores).")
                    
            else:
                st.error("❌ Não há cotações do dólar disponíveis. Verifique sua conexão com a internet e com o banco de dados.")
            
            st.markdown("---")

            current_username = st.session_state.get('user_info', {}).get('username', 'Desconhecido')
            notification_page.display_notifications_on_home(current_username)
            st.markdown("---")
            
            st.write(f"Versão da Aplicação: {st.session_state.get('app_version', '3.0.1')}")
            st.write("Status dos Bancos de Dados:")
            if st.session_state.get('firebase_ready', False): # Verifica a flag de inicialização do Firebase
                st.success("- Conexão com Firebase estabelecida. DBs prontos.")
            else:
                st.error("- Falha na conexão com Firebase. Verifique os logs e secrets.toml.")
            
        elif st.session_state.current_page == "Dashboard":
            # Check if user has permission or is admin
            if "Dashboard" in allowed_screens or is_admin:
                dashboard_page.show_dashboard_page()
            else:
                st.warning("Você não tem permissão para acessar esta tela.")

        elif st.session_state.current_page in PAGES and PAGES[st.session_state.current_page] is not None:
            # Check if user has permission for the current page
            if st.session_state.current_page in allowed_screens or is_admin:
                if st.session_state.current_page in ["Análise de Documentos", "Pagamentos Container", "Cálculo de Tributos TTCE"]:
                    st.warning(f"Tela de {st.session_state.current_page} (em desenvolvimento)")
                
                # Se a página atual é "Formulário Processo", chame-a com os dados do session_state
                if st.session_state.current_page == "Formulário Processo":
                    process_form_page.show_process_form_page(
                        process_identifier=st.session_state.get('form_process_identifier'),
                        reload_processes_callback=st.session_state.get('form_reload_processes_callback'),
                        is_cloning=st.session_state.get('form_is_cloning', False) # Certifica que a flag é passada
                    )
                elif st.session_state.current_page == "Clonagem de Processo":
                    clonagem_processo_page.show_clonagem_processo_page(
                        original_process_identifier=st.session_state.get('form_process_identifier'),
                        reload_processes_callback=st.session_state.get('form_reload_processes_callback')
                    )
                elif st.session_state.current_page == "Consulta de Processo":
                    process_query_page.show_process_query_page(
                        process_identifier=st.session_state.get('query_process_identifier'),
                        return_callback=lambda: setattr(st.session_state, 'current_page', "Follow-up Importação")
                    )
                elif st.session_state.current_page == "Vincular Consolidado":
                    vincular_consolidado_page.show_vincular_consolidado_page(
                        process_id=st.session_state.get('process_id_to_vincular')
                    )
                elif st.session_state.current_page == "Gerenciar Processos em Massa":
                    mass_process_manager_page.show_mass_process_manager_page(
                        reload_processes_callback=st.session_state.get('mass_process_manager_reload_callback')
                    )
                elif st.session_state.current_page == "Editar Múltiplos Processos":
                    mass_edit_processes_page.show_page()
                elif st.session_state.current_page == "Testar API Portonave Lineup":
                    portonave_lineup_page.show_portonave_lineup_page()
                elif st.session_state.current_page == "Cotação de Frete Internacional":
                    cotacao_frete.show_cotacao_frete_page()
                elif st.session_state.current_page == "Inserir Cotação Agente":
                    inserir_cotacao_agente.show_inserir_cotacao_agente_page()
                else:
                    PAGES[st.session_state.current_page]()
            else:
                st.warning("Você não tem permissão para acessar esta tela.")
        else:
            st.info(f"Página '{st.session_state.current_page}' em desenvolvimento ou não encontrada.")
