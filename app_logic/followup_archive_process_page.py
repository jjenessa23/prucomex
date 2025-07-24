import streamlit as st
from typing import Any, Optional
import sys
import os

# Configuração de logging para este módulo
import logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Adiciona o diretório pai ao sys.path para importações relativas
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Importar db_manager (assumindo que está no diretório pai)
import followup_db_manager as db_manager

# Importar funções de utilidade do módulo utils
try:
    from app_logic.utils import set_background_image
except ImportError:
    logging.warning("Módulo 'app_logic.utils' não encontrado. Funções de imagem de fundo podem não funcionar.")
    def set_background_image(image_path, opacity=None):
        pass # Função mock se utils não for encontrado

# Importar funções de callback da página principal, pois elas manipulam o cache global
# e o estado de navegação.
try:
    from app_logic.followup_importacao_page import _partial_cache_update_after_edit
except ImportError:
    logger.error("Não foi possível importar _partial_cache_update_after_edit de followup_importacao_page.")
    def _partial_cache_update_after_edit(process_id: Any, update_type: str):
        st.error("Erro interno: Função de atualização de cache não carregada.")
        return False


def _delete_process_action(process_id: Any, current_username: str):
    """Arquiva um processo no banco de dados (não exclui permanentemente)."""
    with st.spinner("Arquivando processo..."):
        if db_manager.arquivar_processo(process_id):
            st.success(f"Processo ID {process_id} arquivado com sucesso! Ele não aparecerá mais na tela principal por padrão.")
        else:
            st.error(f"Falha ao arquivar processo ID {process_id}.")
        
        # Atualiza o cache da página principal
        success = _partial_cache_update_after_edit(process_id, "archive")
        if not success:
            # Se a atualização parcial falhou, força reload completo
            # st.session_state.last_db_update = datetime.now() # datetime não está importado aqui, mas a função de callback deve lidar
            st.session_state.all_processes_raw_data_cache = []
            st.session_state.consolidated_groups_data_raw_cache = []
        
        st.session_state.current_page = "Follow-up Importação" # Retorna à página principal
        st.rerun()


def display_archive_process_page():
    """Exibe a página dedicada para confirmar o arquivamento de um processo."""
    background_image_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'assets', 'logo_navio_atracado.png')
    set_background_image(background_image_path)

    st.subheader("Arquivar Processo")

    process_id_to_delete = st.session_state.get('delete_process_id_to_confirm')
    process_name_to_delete = st.session_state.get('delete_process_name_to_confirm')
    current_username = st.session_state.get('user_info', {}).get('username', 'Desconhecido')

    if process_id_to_delete is None:
        st.warning("Nenhum processo selecionado para arquivar. Retornando para a página principal.")
        st.session_state.current_page = "Follow-up Importação"
        st.rerun()
        return

    with st.form(key=f"archive_confirm_form_page_{process_id_to_delete}"):
        st.markdown(f"### Confirmar Arquivamento")
        st.warning(f"Tem certeza que deseja arquivar o processo '{process_name_to_delete}' (ID: {process_id_to_delete})? Ele não será excluído do banco de dados, mas não aparecerá na tela principal por padrão.")
        
        col_yes, col_no = st.columns(2)
        with col_yes:
            if st.form_submit_button("Sim, Arquivar"):
                _delete_process_action(process_id_to_delete, current_username)
        with col_no:
            if st.form_submit_button("Não, Cancelar"):
                st.session_state.current_page = "Follow-up Importação"
                st.rerun()

