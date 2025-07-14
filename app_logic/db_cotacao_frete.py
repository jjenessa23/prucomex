import streamlit as st
import logging
import hashlib
from datetime import datetime
from typing import Dict, List, Any, Optional
from google.cloud import firestore # Adicionado: Importar firestore

# Importar o cliente Firestore do session_state (inicializado em app_main.py)
# Certifique-se de que app_main.py inicializa st.session_state.db_firestore
# e st.session_state.firebase_ready = True
# Se db_utils já tem acesso ao db_firestore, podemos reutilizar.
import app_logic.db_utils as db_utils # Para hash_password e acesso ao db_firestore

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# --- Funções para Gerenciamento de Agentes de Carga (AGORA GERENCIADAS EM db_utils.py) ---
# As funções CRUD de agentes foram movidas ou adaptadas para db_utils.py
# para usar a coleção 'users'.

def get_all_freight_agents() -> List[Dict[str, Any]]:
    """
    Retorna uma lista de todos os usuários que são agentes de carga (da coleção 'users').
    """
    if not st.session_state.get('firebase_ready', False):
        logger.warning("Firestore não está pronto. Não é possível obter agentes de carga.")
        return []

    db = st.session_state.db_firestore
    agents = []
    try:
        users_ref = db.collection("users")
        # Busca todos os documentos na coleção 'users' onde 'is_freight_agent' é True
        # Usando FieldFilter para compatibilidade futura
        query = users_ref.where(filter=firestore.FieldFilter("is_freight_agent", "==", True))
        docs = query.stream()

        for doc in docs:
            agent_data = doc.to_dict()
            agent_data['id'] = doc.id # Adiciona o ID do documento (que é o username)
            # Garante que os campos 'email' e 'allowed_screens' existam, mesmo que vazios
            agent_data['email'] = agent_data.get('email', '')
            agent_data['allowed_screens'] = agent_data.get('allowed_screens', [])
            agents.append(agent_data)
        
        logger.info(f"Carregados {len(agents)} agentes de carga do Firestore (da coleção 'users').")
        return agents
    except Exception as e:
        logger.error(f"Erro ao obter agentes de carga do Firestore (da coleção 'users'): {e}")
        return []

def get_freight_agent_by_username(username: str) -> Optional[Dict[str, Any]]:
    """
    Obtém os dados de um agente de carga pelo seu nome de usuário (da coleção 'users').
    """
    if not st.session_state.get('firebase_ready', False):
        logger.error("Firestore não está pronto. Não é possível obter agente por username.")
        return None
    db = st.session_state.db_firestore
    try:
        doc_ref = db.collection("users").document(username) # Busca na coleção 'users'
        doc = doc_ref.get()
        if doc.exists:
            agent_data = doc.to_dict()
            # Verifica se o usuário encontrado é de fato um agente de carga
            if agent_data.get('is_freight_agent', False):
                agent_data['id'] = doc.id
                agent_data['email'] = agent_data.get('email', '')
                agent_data['allowed_screens'] = agent_data.get('allowed_screens', [])
                logger.info(f"Agente de carga '{username}' encontrado (na coleção 'users').")
                return agent_data
            else:
                logger.warning(f"Usuário '{username}' encontrado, mas não é um agente de carga.")
                return None
        else:
            logger.warning(f"Agente de carga '{username}' não encontrado (na coleção 'users').")
            return None
    except Exception as e:
        logger.error(f"Erro ao obter agente de carga '{username}' (da coleção 'users'): {e}")
        return None

def verify_agent_credentials(username: str, password: str) -> Optional[Dict[str, Any]]:
    """
    Verifica as credenciais de um agente de carga.
    Usa a função verify_credentials de db_utils para autenticar o usuário
    e então verifica se ele é um agente de carga.
    """
    if not st.session_state.get('firebase_ready', False):
        logger.error("Firestore não está pronto. Não é possível verificar credenciais do agente.")
        return None

    # Tenta autenticar o usuário normalmente através de db_utils
    user_info = db_utils.verify_credentials(username, password)
    
    if user_info:
        # Se o usuário foi autenticado, verifica se ele é um agente de carga
        if user_info.get('is_freight_agent', False):
            logger.info(f"Credenciais válidas e usuário '{username}' é um agente de carga.")
            return user_info # Retorna os dados do usuário, que agora incluem a flag de agente
        else:
            logger.warning(f"Usuário '{username}' autenticado, mas não é um agente de carga.")
            return None
    else:
        logger.warning(f"Falha na autenticação para o usuário '{username}'.")
        return None


# --- Funções para Solicitações de Cotação ---

def add_quotation_request(request_details: Dict[str, Any]) -> bool:
    """
    Adiciona uma nova solicitação de cotação ao Firestore.
    O ID do documento é fornecido nos detalhes da requisição.
    """
    if not st.session_state.get('firebase_ready', False):
        logger.error("Firestore não está pronto. Não é possível adicionar solicitação de cotação.")
        return False

    db = st.session_state.db_firestore
    try:
        request_id = request_details.get('id')
        if not request_id:
            logger.error("ID da solicitação não fornecido para adicionar cotação.")
            return False

        doc_ref = db.collection("quotation_requests").document(request_id)
        doc_ref.set(request_details)
        logger.info(f"Solicitação de cotação adicionada com sucesso. ID: {request_id}")
        return True
    except Exception as e:
        logger.error(f"Erro ao adicionar solicitação de cotação: {e}")
        return False

def get_all_quotation_requests() -> List[Dict[str, Any]]:
    """
    Retorna todas as solicitações de cotação do Firestore.
    """
    if not st.session_state.get('firebase_ready', False):
        logger.warning("Firestore não está pronto. Não é possível obter solicitações de cotação.")
        return []

    db = st.session_state.db_firestore
    requests = []
    try:
        docs = db.collection("quotation_requests").stream()
        for doc in docs:
            req_data = doc.to_dict()
            req_data['id'] = doc.id # Garante que o ID do documento esteja incluído
            requests.append(req_data)
        logger.info(f"Carregadas {len(requests)} solicitações de cotação do Firestore.")
        return requests
    except Exception as e:
        logger.error(f"Erro ao obter solicitações de cotação do Firestore: {e}")
        return []

def get_quotation_request_by_id(request_id: str) -> Optional[Dict[str, Any]]:
    """
    Retorna uma solicitação de cotação específica pelo seu ID.
    """
    if not st.session_state.get('firebase_ready', False):
        logger.error("Firestore não está pronto. Não é possível obter solicitação de cotação por ID.")
        return None

    db = st.session_state.db_firestore
    try:
        doc_ref = db.collection("quotation_requests").document(request_id)
        doc = doc_ref.get()
        if doc.exists:
            req_data = doc.to_dict()
            req_data['id'] = doc.id
            logger.info(f"Solicitação de cotação '{request_id}' encontrada.")
            return req_data
        else:
            logger.warning(f"Solicitação de cotação '{request_id}' não encontrada.")
            return None
    except Exception as e:
        logger.error(f"Erro ao obter solicitação de cotação '{request_id}': {e}")
        return None

def update_quotation_request_status(request_id: str, new_status: str) -> bool:
    """
    Atualiza o status de uma solicitação de cotação.
    """
    if not st.session_state.get('firebase_ready', False):
        logger.error("Firestore não está pronto. Não é possível atualizar o status da solicitação.")
        return False

    db = st.session_state.db_firestore
    try:
        doc_ref = db.collection("quotation_requests").document(request_id)
        doc_ref.update({"status": new_status})
        logger.info(f"Status da solicitação '{request_id}' atualizado para '{new_status}'.")
        return True
    except Exception as e:
        logger.error(f"Erro ao atualizar status da solicitação '{request_id}': {e}")
        return False

def delete_quotation_request(request_id: str) -> bool:
    """
    Deleta uma solicitação de cotação e todas as respostas de cotação associadas.
    """
    logger.info(f"db_cotacao_frete: [DELETE_REQUEST] Tentando deletar solicitação de cotação: {request_id}")
    if not st.session_state.get('firebase_ready', False):
        logger.error("db_cotacao_frete: [DELETE_REQUEST] Firestore não está pronto. Não é possível deletar solicitação de cotação.")
        return False

    db = st.session_state.db_firestore
    try:
        batch = db.batch()

        # 1. Deletar todas as respostas de cotação associadas a esta solicitação
        # A referência correta para a subcoleção é obtida a partir do documento da solicitação.
        quotations_subcollection_ref = db.collection("quotation_requests").document(request_id).collection("quotations")
        
        logger.info(f"db_cotacao_frete: [DELETE_REQUEST] Buscando respostas na subcoleção: quotation_requests/{request_id}/quotations")
        
        # Converte o stream para uma lista para garantir que todas as referências sejam coletadas antes de iterar
        docs_to_delete_responses = list(quotations_subcollection_ref.stream())
        
        responses_found_count = len(docs_to_delete_responses)
        logger.info(f"db_cotacao_frete: [DELETE_REQUEST] {responses_found_count} respostas encontradas para solicitação '{request_id}'.")

        if responses_found_count > 0:
            for doc in docs_to_delete_responses:
                batch.delete(doc.reference)
                logger.debug(f"db_cotacao_frete: [DELETE_REQUEST] Adicionado delete para resposta: {doc.id}")
        else:
            logger.info(f"db_cotacao_frete: [DELETE_REQUEST] Nenhuma resposta encontrada para adicionar ao batch para solicitação '{request_id}'.")


        # 2. Deletar a solicitação de cotação principal
        request_doc_ref = db.collection("quotation_requests").document(request_id)
        
        request_doc_exists = request_doc_ref.get().exists
        logger.info(f"db_cotacao_frete: [DELETE_REQUEST] Documento principal '{request_id}' existe: {request_doc_exists}")

        if request_doc_exists:
            batch.delete(request_doc_ref)
            logger.info(f"db_cotacao_frete: [DELETE_REQUEST] Solicitação de cotação '{request_id}' adicionada ao batch para exclusão principal.")
        else:
            logger.warning(f"db_cotacao_frete: [DELETE_REQUEST] Solicitação de cotação '{request_id}' não encontrada para exclusão principal. Pode já ter sido excluída.")

        logger.info(f"db_cotacao_frete: [DELETE_REQUEST] Tentando commitar o batch para solicitação '{request_id}'.")
        batch.commit()
        logger.info(f"db_cotacao_frete: [DELETE_REQUEST] Batch commit concluído com sucesso para solicitação '{request_id}'.")
        return True
    except Exception as e:
        logger.error(f"db_cotacao_frete: [DELETE_REQUEST] Erro crítico ao deletar solicitação de cotação '{request_id}': {e}", exc_info=True)
        return False


# --- Funções para Respostas de Cotação ---

def add_quotation_response(quotation_data: Dict[str, Any]) -> bool:
    """
    Adiciona uma nova resposta de cotação ao Firestore.
    """
    if not st.session_state.get('firebase_ready', False):
        logger.error("Firestore não está pronto. Não é possível adicionar resposta de cotação.")
        return False

    db = st.session_state.db_firestore
    try:
        # Adiciona a resposta de cotação em uma subcoleção da solicitação original
        # Isso associa a resposta diretamente à solicitação.
        doc_ref = db.collection("quotation_requests").document(quotation_data['request_id']).collection("quotations").document()
        doc_ref.set(quotation_data)
        logger.info(f"Resposta de cotação adicionada com sucesso para a solicitação '{quotation_data['request_id']}'.")
        return True
    except Exception as e:
        logger.error(f"Erro ao adicionar resposta de cotação para a solicitação '{quotation_data['request_id']}': {e}")
        return False

def get_quotations_for_request(request_id: str) -> List[Dict[str, Any]]:
    """
    Retorna todas as cotações recebidas para uma solicitação específica.
    """
    if not st.session_state.get('firebase_ready', False):
        logger.warning("Firestore não está pronto. Não é possível obter cotações para a solicitação.")
        return []

    db = st.session_state.db_firestore
    quotations = []
    try:
        docs = db.collection("quotation_requests").document(request_id).collection("quotations").stream()
        for doc in docs:
            quot_data = doc.to_dict()
            quot_data['id'] = doc.id # Garante que o ID do documento esteja incluído
            quotations.append(quot_data)
        logger.info(f"Carregadas {len(quotations)} cotações para a solicitação '{request_id}'.")
        return quotations
    except Exception as e:
        logger.error(f"Erro ao obter cotações para a solicitação '{request_id}': {e}")
        return False

def has_agent_responded(request_id: str, agent_username: str) -> bool:
    """
    Verifica se um agente específico já respondeu a uma solicitação de cotação.
    """
    if not st.session_state.get('firebase_ready', False):
        logger.warning("Firestore não está pronto. Não é possível verificar se o agente respondeu.")
        return False

    db = st.session_state.db_firestore
    try:
        # Busca na subcoleção 'quotations' por uma resposta com o request_id e agent_username
        # Usando FieldFilter para compatibilidade futura
        query = db.collection("quotation_requests").document(request_id).collection("quotations").where(filter=firestore.FieldFilter("agent_username", "==", agent_username)).limit(1)
        
        docs = query.get() # Use .get() para obter os documentos diretamente
        
        if len(docs) > 0:
            logger.info(f"Agente '{agent_username}' JÁ respondeu à solicitação '{request_id}'.")
            return True
        else:
            logger.info(f"Agente '{agent_username}' AINDA NÃO respondeu à solicitação '{request_id}'.")
            return False
    except Exception as e:
        logger.error(f"Erro ao verificar se o agente '{agent_username}' respondeu à solicitação '{request_id}': {e}")
        return False
