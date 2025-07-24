import streamlit as st
from datetime import datetime
from typing import Dict, Any, Optional, List
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


def display_edit_checklist_page():
    """Exibe a página dedicada para alterar os itens de checklist Sim/Não de um processo."""
    background_image_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'assets', 'logo_navio_atracado.png')
    set_background_image(background_image_path)

    st.subheader("Editar Checklist do Processo")

    process_id = st.session_state.get('checklist_process_id_to_edit')
    process_name = st.session_state.get('checklist_process_name_to_edit')

    if process_id is None:
        st.warning("Nenhum processo selecionado para edição de checklist. Retornando para a página principal.")
        st.session_state.current_page = "Follow-up Importação"
        st.rerun()
        return

    # Tenta obter os dados mais recentes do processo
    current_process_data = db_manager.obter_processo_por_id(process_id)
    if not current_process_data:
        # Fallback se não encontrar por ID numérico, tenta por Processo_Novo (string)
        current_process_data = db_manager.obter_processo_by_processo_novo(process_id)

    if not current_process_data:
        st.error(f"Processo '{process_name}' (ID: {process_id}) não encontrado para edição do checklist.")
        st.session_state.current_page = "Follow-up Importação"
        st.rerun()
        return

    with st.form(key=f"edit_checklist_form_page_{process_id}"):
        st.markdown(f"### Ajustar Checklist para: **{process_name}**")
        st.info("Marque 'Sim', 'Não' ou '➖' (vazio) para cada item do checklist.")

        checklist_fields = {
            "Pago": "Pago",
            "Documentos_Revisados": "Docs Revisados",
            "Conhecimento_Embarque": "Conhecimento Embarque",
            "Descricao_Feita": "Descrição Feita",
            "Descricao_Enviada": "Descrição Enviada",
            "Nota_feita": "Nota Feita",
            "Conferido": "Conferido"
        }
        
        updated_checklist_values = {}
        options_sim_nao_vazio = ["➖", "Sim", "Não"] 

        for db_field, display_name in checklist_fields.items():
            current_value = current_process_data.get(db_field)
            if str(current_value).lower() == "sim":
                default_index = 1
            elif str(current_value).lower() == "não":
                default_index = 2
            else:
                default_index = 0

            selected_option = st.radio(
                f"{display_name}:",
                options_sim_nao_vazio,
                index=default_index,
                key=f"radio_{db_field}_{process_id}"
            )
            if selected_option == "Sim":
                updated_checklist_values[db_field] = "Sim"
            elif selected_option == "Não":
                updated_checklist_values[db_field] = "Não"
            else:
                updated_checklist_values[db_field] = None # Salva como None no DB para "➖"


        col_apply, col_cancel = st.columns(2)
        with col_apply:
            if st.form_submit_button("Salvar Checklist"):
                user_info = st.session_state.get('user_info', {'username': 'Desconhecido'})
                username = user_info.get('username')
                
                changes_for_history = {}
                for field, new_val in updated_checklist_values.items():
                    old_val = current_process_data.get(field)
                    # Compara como string para tratar None, "Sim", "Não" de forma consistente
                    if str(old_val) != str(new_val): 
                        changes_for_history[field] = (old_val, new_val)

                if db_manager.atualizar_processo(process_id, updated_checklist_values):
                    st.success(f"Checklist do processo {process_name} atualizado com sucesso!")
                    for field_name, (old_val, new_val) in changes_for_history.items():
                        db_manager.inserir_historico_processo(
                            process_id, field_name, old_val, new_val,
                            username, db_type="Firestore" if db_manager._USE_FIRESTORE_AS_PRIMARY else "SQLite"
                        )
                    
                    # Atualiza o cache da página principal
                    _partial_cache_update_after_edit(process_id, "checklist_edit")
                    st.session_state.current_page = "Follow-up Importação" # Retorna à página principal
                    st.rerun()
                else:
                    st.error(f"Falha ao atualizar checklist do processo {process_name}.")
        with col_cancel:
            if st.form_submit_button("Cancelar"):
                st.session_state.current_page = "Follow-up Importação" # Retorna à página principal
                st.rerun()

