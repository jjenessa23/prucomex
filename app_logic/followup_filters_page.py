import streamlit as st
from datetime import datetime, date
from typing import Dict, Any, Optional, List
import sys
import os
import pandas as pd # Importar pandas

# Configuração de logging para este módulo
import logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Adiciona o diretório pai ao sys.path para importações relativas
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Importar o db_manager (assumindo que está no diretório pai)
import followup_db_manager as db_manager

# Funções auxiliares de UI (Popups e Ações) - Copiadas de followup_importacao_page.py
def _on_process_search_change_filters():
    """Callback para mudança no campo de pesquisa de processo principal na tela de filtros."""
    # Esta função será chamada quando o termo de pesquisa mudar no popup de filtros
    # e precisa invalidar os caches e forçar o recarregamento.
    # O Streamlit lida com o rerun automaticamente quando um callback de on_change é acionado.
    st.session_state.followup_main_process_search_term = st.session_state.filter_popup_search_processo_novo
    st.session_state._invalidate_filter_cache = True 
    st.session_state.all_processes_raw_data_cache = [] # Limpa os dados em cache para forçar recarregamento
    st.session_state.consolidated_groups_data_raw_cache = []

def _on_status_multiselect_change_filters():
    """Callback para mudança no multiselect de status na tela de filtros."""
    selected_options_with_counts = st.session_state.filter_popup_status_multiselect
    new_selected_raw_statuses = []
    if not selected_options_with_counts or 'Todos' in selected_options_with_counts:
        new_selected_raw_statuses.append('Todos')
    else:
        for opt in selected_options_with_counts:
            new_selected_raw_statuses.append(opt.split(' (')[0]) # Remove a contagem
    st.session_state.followup_selected_statuses = new_selected_raw_statuses
    
    st.session_state._invalidate_filter_cache = True 
    st.session_state.all_processes_raw_data_cache = [] # Limpa os dados em cache para forçar recarregamento
    st.session_state.consolidated_groups_data_raw_cache = []


def display_filter_search_page():
    """Exibe a página dedicada de filtros e pesquisa avançada para o Follow-up."""
    st.subheader("Mais Filtros e Pesquisa de Processos")

    # Garante que os estados da sessão para filtros existam
    st.session_state.setdefault('followup_popup_search_terms', {})
    st.session_state.setdefault('followup_main_process_search_term', '')
    st.session_state.setdefault('followup_selected_statuses', ['Todos'])
    st.session_state.setdefault('followup_all_status_options', []) # Para o multiselect de status

    # Carrega as opções de status para o multiselect (copiado de followup_importacao_page.py)
    # Esta parte idealmente deveria vir de uma função que não dependa do df_followup completo
    # ou que receba o df_followup como argumento. Por enquanto, vamos mockar ou garantir que
    # o session_state já tenha sido preenchido por followup_importacao_page.py.
    if not st.session_state.followup_all_status_options:
        # Fallback para carregar opções de status se não estiverem no session_state
        # Isso pode ser um problema se o db_manager.get_active_notifications() não for chamado
        # antes de esta página ser acessada.
        all_processes_raw_data = db_manager.obter_todos_processos() # Pode ser pesado se houver muitos processos
        if all_processes_raw_data:
            df_all_processes_for_options = pd.DataFrame(all_processes_raw_data)
            _update_status_filter_options(df_all_processes_for_options)
        else:
            st.session_state.followup_all_status_options = ["Todos"]
            st.session_state.followup_raw_status_options_for_multiselect = ["Todos"]


    with st.form(key="filter_search_form_page"):
        st.markdown("### Ajustar Filtros e Pesquisa")

        # Filtro de pesquisa principal (Processo_Novo)
        st.text_input(
            "Pesquisar Processo (Referência):", 
            value=st.session_state.get('followup_main_process_search_term', ''),
            key="filter_popup_search_processo_novo",
            on_change=_on_process_search_change_filters # Usa o callback local
        )

        # Filtro de status
        all_status_options_formatted = st.session_state.get('followup_all_status_options', ["Todos"])
        current_selected_statuses_raw = st.session_state.get('followup_selected_statuses', ['Todos'])

        default_multiselect_value = []
        for raw_s in current_selected_statuses_raw:
            if raw_s == 'Todos':
                if 'Todos' in all_status_options_formatted:
                    default_multiselect_value.append("Todos")
            else:
                found_formatted_opt = next((opt for opt in all_status_options_formatted if opt.startswith(raw_s + ' (')), None)
                if found_formatted_opt:
                    default_multiselect_value.append(found_formatted_opt)

        st.multiselect(
            "Filtrar por Status:",
            options=all_status_options_formatted,
            default=default_multiselect_value,
            key="filter_popup_status_multiselect",
            on_change=_on_status_multiselect_change_filters # Usa o callback local
        )


        st.markdown("---")
        st.markdown("##### Filtros Adicionais:")

        col_left, col_right = st.columns(2)

        with col_left:
            st.text_input("Pesquisar N. Invoice:", key="popup_followup_search_n_invoice",
                          value=st.session_state.get('followup_popup_search_terms', {}).get('N_Invoice', '') or "")
            st.text_input("Pesquisar Modal:", key="popup_followup_search_Modal",
                          value=st.session_state.get('followup_popup_search_terms', {}).get('Modal', '') or "")
            st.text_input("Pesquisar Origem:", key="popup_followup_search_Origem",
                          value=st.session_state.get('followup_popup_search_terms', {}).get('Origem', '') or "")
            
            current_eta_recinto_start = st.session_state.get('followup_popup_search_terms', {}).get('ETA_Recinto_Start', None)
            current_eta_recinto_end = st.session_state.get('followup_popup_search_terms', {}).get('ETA_Recinto_End', None)
            # Convert string dates back to datetime.date objects for date_input
            if current_eta_recinto_start and isinstance(current_eta_recinto_start, str):
                try: current_eta_recinto_start = datetime.strptime(current_eta_recinto_start, "%Y-%m-%d").date()
                except ValueError: current_eta_recinto_start = None
            if current_eta_recinto_end and isinstance(current_eta_recinto_end, str):
                try: current_eta_recinto_end = datetime.strptime(current_eta_recinto_end, "%Y-%m-%d").date()
                except ValueError: current_eta_recinto_end = None

            st.date_input("Data no Recinto (Início):", value=current_eta_recinto_start, key="popup_followup_search_eta_recinto_start", format="DD/MM/YYYY")
            st.date_input("Data no Recinto (Fim):", value=current_eta_recinto_end, key="popup_followup_search_eta_recinto_end", format="DD/MM/YYYY")


        with col_right:
            st.text_input("Pesquisar Fornecedor:", key="popup_followup_search_fornecedor",
                          value=st.session_state.get('followup_popup_search_terms', {}).get('Fornecedor', '') or "")
            st.text_input("Pesquisar Tipos de Item:", key="popup_followup_search_Tipos_de_item",
                          value=st.session_state.get('followup_popup_search_terms', {}).get('Tipos_de_item', '') or "")
            st.text_input("Pesquisar Navio:", key="popup_followup_search_Navio",        
                          value=st.session_state.get('followup_popup_search_terms', {}).get('Navio', '') or "")
            st.text_input("Pesquisar Comprador:", key="popup_followup_search_Comprador",
                          value=st.session_state.get('followup_popup_search_terms', {}).get('Comprador', '') or "")

            current_data_registro_start = st.session_state.get('followup_popup_search_terms', {}).get('Data_Registro_Start', None)
            current_data_registro_end = st.session_state.get('followup_popup_search_terms', {}).get('Data_Registro_End', None)
            # Convert string dates back to datetime.date objects for date_input
            if current_data_registro_start and isinstance(current_data_registro_start, str):
                try: current_data_registro_start = datetime.strptime(current_data_registro_start, "%Y-%m-%d").date()
                except ValueError: current_data_registro_start = None
            if current_data_registro_end and isinstance(current_data_registro_end, str):
                try: current_data_registro_end = datetime.strptime(current_data_registro_end, "%Y-%m-%d").date()
                except ValueError: current_data_registro_end = None

            st.date_input("Data de Registro (Início):", value=current_data_registro_start, key="popup_followup_search_data_registro_start", format="DD/MM/YYYY")
            st.date_input("Data de Registro (Fim):", value=current_data_registro_end, key="popup_followup_search_data_registro_end", format="DD/MM/YYYY")


        col_buttons_popup = st.columns(2)
        with col_buttons_popup[0]:
            if st.form_submit_button("Aplicar Mais Filtros"):
                search_terms_to_apply = {
                    "N_Invoice": st.session_state.popup_followup_search_n_invoice,
                    "Fornecedor": st.session_state.popup_followup_search_fornecedor,
                    "Tipos_de_item": st.session_state.popup_followup_search_Tipos_de_item,
                    "Modal": st.session_state.popup_followup_search_Modal,
                    "Navio": st.session_state.popup_followup_search_Navio,
                    "Origem": st.session_state.popup_followup_search_Origem,
                    "Comprador": st.session_state.popup_followup_search_Comprador
                }

                if st.session_state.popup_followup_search_eta_recinto_start:
                    search_terms_to_apply['ETA_Recinto_Start'] = st.session_state.popup_followup_search_eta_recinto_start.strftime("%Y-%m-%d")
                else:
                    search_terms_to_apply['ETA_Recinto_Start'] = None
                
                if st.session_state.popup_followup_search_eta_recinto_end:
                    search_terms_to_apply['ETA_Recinto_End'] = st.session_state.popup_followup_search_eta_recinto_end.strftime("%Y-%m-%d")
                else:
                    search_terms_to_apply['ETA_Recinto_End'] = None

                if st.session_state.popup_followup_search_data_registro_start:
                    search_terms_to_apply['Data_Registro_Start'] = st.session_state.popup_followup_search_data_registro_start.strftime("%Y-%m-%d")
                else:
                    search_terms_to_apply['Data_Registro_Start'] = None

                if st.session_state.popup_followup_search_data_registro_end:
                    search_terms_to_apply['Data_Registro_End'] = st.session_state.popup_followup_search_data_registro_end.strftime("%Y-%m-%d")
                else:
                    search_terms_to_apply['Data_Registro_End'] = None
                
                st.session_state.followup_popup_search_terms = {k: v for k, v in search_terms_to_apply.items() if v} 
                # Invalida os caches ao mudar os filtros principais
                st.session_state._invalidate_filter_cache = True 
                st.session_state.all_processes_raw_data_cache = [] # Limpa os dados em cache para forçar recarregamento
                st.session_state.consolidated_groups_data_raw_cache = []
                st.session_state.current_page = "Follow-up Importação" # Retorna à página principal
                st.rerun()
        with col_buttons_popup[1]:
            if st.form_submit_button("Limpar Mais Filtros"):
                st.session_state.followup_popup_search_terms = {} 
                # Invalida os caches ao mudar os filtros principais
                st.session_state._invalidate_filter_cache = True 
                st.session_state.all_processes_raw_data_cache = [] # Limpa os dados em cache para forçar recarregamento
                st.session_state.consolidated_groups_data_raw_cache = []
                st.session_state.current_page = "Follow-up Importação" # Retorna à página principal
                st.rerun()
        
        # Botão para fechar o formulário e retornar à página principal
        if st.form_submit_button("Fechar Filtros"):
            st.session_state.current_page = "Follow-up Importação"
            st.rerun()

# Função auxiliar para atualizar opções de status (copiada de followup_importacao_page.py)
# Esta função é necessária aqui porque o multiselect precisa das opções formatadas.
# Idealmente, ela deveria ser uma função de utilidade ou o db_manager deveria fornecer as opções.
def _update_status_filter_options(df_all_processes_for_options: pd.DataFrame):
    """Atualiza as opções do filtro de status com base nos status do DB, incluindo contagens."""
    # Importa CUSTOM_STATUS_ORDER aqui para evitar circular import com followup_importacao_page
    # Se CUSTOM_STATUS_ORDER for uma constante global que pode ser acessada de forma limpa,
    # considere movê-la para um módulo de utilidades ou db_manager.
    try:
        from followup_importacao_page import CUSTOM_STATUS_ORDER 
    except ImportError:
        # Fallback se não conseguir importar (ex: durante testes isolados)
        CUSTOM_STATUS_ORDER = [
            'Encerrado','Chegada Pichau', 'Agendado', 'Liberado', 'Registrado',
            'Chegada Recinto', 'Embarcado', 'Verificando','Limbo Consolidado','Limbo Saldo', 'Pré Embarque',
            'Em Produção', 'Processo Criado', 
            'Sem Status', 'Status Desconhecido', 'Arquivados' 
        ]

    if df_all_processes_for_options.empty:
        st.session_state.followup_raw_status_options_for_multiselect = ["Todos"]
        st.session_state.followup_all_status_options = ["Todos"]
        return

    status_counts = df_all_processes_for_options['Status_Geral'].replace(pd.NA, 'Sem Status').astype(str).value_counts().to_dict()
    
    arquivados_count = df_all_processes_for_options[
        (df_all_processes_for_options['Status_Arquivado'] == 'Arquivado') | 
        (df_all_processes_for_options['Status_Geral'] == 'Arquivados') 
    ].shape[0]
    
    all_raw_status_options = list(status_counts.keys())
    
    custom_order_for_options = [status for status in CUSTOM_STATUS_ORDER if status != 'Arquivados']
    
    sorted_status_options = sorted([s for s in all_raw_status_options if s not in custom_order_for_options and s != "Arquivados"])
    final_ordered_status_options = [s for s in custom_order_for_options if s in all_raw_status_options] + sorted_status_options

    formatted_options_with_counts = []
    for status in final_ordered_status_options:
        count = status_counts.get(status, 0)
        formatted_options_with_counts.append(f"{status} ({count})")
    
    if arquivados_count > 0:
        formatted_options_with_counts.append(f"Arquivados ({arquivados_count})")
    
    st.session_state.followup_all_status_options = ["Todos"] + formatted_options_with_counts
    st.session_state.followup_raw_status_options_for_multiselect = ["Todos"] + final_ordered_status_options + (["Arquivados"] if arquivados_count > 0 else [])

