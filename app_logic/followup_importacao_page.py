import streamlit as st
import pandas as pd
from datetime import datetime
import logging
import os
import subprocess
import sys
import io
import xlsxwriter
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from typing import Optional, Any, Dict, List, Union, Tuple # Importar Tuple
import numpy as np
import base64
import warnings
import followup_db_manager as db_manager
from app_logic import process_form_page
from app_logic import process_query_page
import uuid
import gc  # Para otimizações de memória baseadas no OTIMIZACOES_PERFORMANCE.md
import threading  # Para limpeza agendada de memória
import time  # Para cálculos de performance

# Configuração de logging aprimorado


# Configura o logger para a aplicação
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO) # Definir um nível de logging mais informativo para debug

# --- Constante da Ordem de Status ---
# Ordem pré-determinada para exibição dos status na interface
CUSTOM_STATUS_ORDER = [
    'Encerrado','Chegada Pichau', 'Agendado', 'Liberado', 'Registrado',
    'Chegada Recinto', 'Embarcado', 'Verificando','Limbo Consolidado','Limbo Saldo', 'Pré Embarque',
    'Em Produção', 'Processo Criado', 
    'Sem Status', 'Status Desconhecido', 'Arquivados' 
]

# --- NOVO: Definindo a constante INITIAL_CARDS_PER_CHUNK ---
INITIAL_CARDS_PER_CHUNK = 15 # Número otimizado: 15 cards por vez (vs 20 original)
TABLE_ROWS_INCREMENT = 50 # Incremento para carregamento de linhas na visualização de tabela

# --- Mock de Utilitários de Banco de Dados (para simulação, caso o módulo real não esteja disponível) ---
class MockDbUtils:
    """Classe mock para simular funções de acesso ao banco de dados, útil em ambientes de desenvolvimento."""
    def get_db_path(self, db_name: str) -> str:
        _base_path = os.path.dirname(os.path.abspath(__file__))
        _app_root_path = os.path.dirname(_base_path) if os.path.basename(_base_path) == 'app_logic' else _base_path
        _DEFAULT_DB_FOLDER = "data"
        return os.path.join(_app_root_path, _DEFAULT_DB_FOLDER, f"{db_name}.db")
    
    def get_declaracao_by_id(self, di_id: int) -> Optional[dict]:
        """Função mock para simulação de obtenção de DI por ID."""
        # Retorna um mock de dados de DI. Adapte conforme a necessidade do mock.
        if di_id == 'DI_MOCK_12345':
            return {
                'id': 'DI_MOCK_12345',
                'numero_di': '1234567890',
                'informacao_complementar': 'PROCESSO_ABC',
                'frete_nacional': 150.00,
                'armazenagem': 200.00,
                'Honorarios_Despachante': 1000.00,
                'Modal': 'Aéreo',
                'taxa_cambial_usd': 5.00,
                'imposto_importacao': 100.00,
                'ipi': 50.00,
                'pis_pasep': 20.00,
                'cofins': 30.00,
                'taxa_siscomex': 10.00,
                'vmld': 5000.00,
                'data_registro': '2023-01-15'
            }
        return None
    
    def get_declaracao_by_referencia(self, process_number: str) -> Optional[dict]:
        """Função mock para simulação de obtenção de DI por número de processo."""
        # Retorna um mock de dados de DI. Adapte conforme a necessidade do mock.
        if process_number == "PROCESSO_ABC":
            return {
                'id': 'DI_MOCK_12345',
                'numero_di': '1234567890',
                'informacao_complementar': 'PROCESSO_ABC',
                'frete_nacional': 150.00,
                'armazenagem': 200.00,
                'Honorarios_Despachante': 1000.00,
                'Modal': 'Aéreo',
                'taxa_cambial_usd': 5.00,
                'imposto_importacao': 100.00,
                'ipi': 50.00,
                'pis_pasep': 20.00,
                'cofins': 30.00,
                'taxa_siscomex': 10.00,
                'vmld': 5000.00,
                'data_registro': '2023-01-15'
            }
        return None

    def get_frete_internacional_by_referencia(self, referencia_processo: str) -> Optional[Dict[str, Any]]:
        """Função mock para simulação de obtenção de frete internacional."""
        if referencia_processo == "PROCESSO_ABC":
            return {
                'referencia_processo': 'PROCESSO_ABC',
                'tipo_frete': 'Aéreo',
                'total_aereo_brl': 500.00
            }
        return None

    def get_declaracoes_by_referencias(self, referencias: List[str]) -> Dict[str, Any]:
        """Função mock para simulação de obtenção de DI por lista de referências."""
        mock_data = {}
        for ref in referencias:
            # Simula dados para cada referência, se necessário
            mock_data[ref] = {
                'id': f'DI_MOCK_{ref}',
                'numero_di': f'123456789{len(ref)}',
                'informacao_complementar': ref,
                'frete_nacional': 150.00 + len(ref),
                'armazenagem': 200.00 + len(ref),
                'Honorarios_Despachante': 1000.00 + len(ref),
                'Modal': 'Aéreo',
                'taxa_cambial_usd': 5.00,
                'imposto_importacao': 100.00,
                'ipi': 50.00,
                'pis_pasep': 20.00,
                'cofins': 30.00,
                'taxa_siscomex': 10.00,
                'vmld': 5000.00,
                'data_registro': '2023-01-15'
            }
        return mock_data

    def get_fretes_internacionais_by_referencias(self, referencias: List[str]) -> Dict[str, Any]:
        """Função mock para simulação de obtenção de frete internacional por lista de referências."""
        mock_data = {}
        for ref in referencias:
            # Simula dados para cada referência, se necessário
            mock_data[ref] = {
                'referencia_processo': ref,
                'tipo_frete': 'Aéreo',
                'total_aereo_brl': 500.00 + len(ref)
            }
        return mock_data

# Tenta importar o db_utils real; caso contrário, usa o mock
db_utils: Union[Any, MockDbUtils] 
try:
    import db_utils # type: ignore
    if not hasattr(db_utils, 'get_declaracao_by_id') or \
       not hasattr(db_utils, 'get_declaracao_by_referencia') or \
       not hasattr(db_utils, 'get_frete_internacional_by_referencia') or \
       not hasattr(db_utils, 'get_declaracoes_by_referencias') or \
       not hasattr(db_utils, 'get_fretes_internacionais_by_referencias'): # Adicionado
        logger.warning("Módulo 'db_utils' real não contém funções esperadas. Usando MockDbUtils.")
        db_utils = MockDbUtils()
except ImportError:
    logger.warning("Módulo 'db_utils' não encontrado. Usando MockDbUtils.")
    db_utils = MockDbUtils()
except Exception as e:
    logger.error(f"Erro ao importar ou inicializar 'db_utils': {e}. Usando MockDbUtils.")

# Importar vincular_utils (assumindo que está no mesmo diretório ou acessível via PYTHONPATH)
try:
    from app_logic import vincular_utils
except ImportError:
    logger.error("Módulo 'vincular_utils' não encontrado. Funções relacionadas a consolidados podem não funcionar.")
    class MockVincularUtils:
        def listar_grupos_consolidados(self) -> List[Dict[str, Any]]:
            return []
    vincular_utils = MockVincularUtils()


# --- Função para definir imagem de fundo com opacidade ---
def set_background_image(image_path: str):
    """Define uma imagem de fundo para o aplicativo Streamlit com opacidade."""
    try:
        with open(image_path, "rb") as image_file:
            encoded_string = base64.b64encode(image_file.read()).decode()
        st.markdown(
            f"""
            <style>
            .stApp {{
                background-color: transparent !important;
            }}
            .stApp::before {{
                content: "";
                position: fixed;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
                background-image: url("data:image/png;base64,{encoded_string}");
                background-size: cover;
                background-position: center;
                background-repeat: no-repeat;
                background-attachment: fixed;
                opacity: 0.20;
                z-index: -1;
            }}
            </style>
            """,
            unsafe_allow_html=True
        )
    except FileNotFoundError:
        st.warning(f"A imagem de fundo não foi encontrada no caminho: {image_path}")
    except Exception as e:
        st.error(f"Erro ao carregar a imagem de fundo: {e}")


# --- Funções Auxiliares de Formatação ---
def _format_date_display(date_str: Optional[str]) -> str:
    """Formata uma string de data (YYYY-MM-DD) para exibição (DD/MM/YYYY)."""
    if date_str and isinstance(date_str, str):
        try:
            return datetime.strptime(date_str, "%Y-%m-%d").strftime("%d/%m/%Y")
        except ValueError:
            return date_str
    return ""

def _format_currency_display(value: Any) -> str:
    """Formata um valor numérico para o formato de moeda R$ X.XXX,XX."""
    try:
        val = safe_float(value)
        return f"R$ {val:,.2f}".replace('.', '#').replace(',', '.').replace('#', ',')
    except (ValueError, TypeError):
        return "R$ 0,00"

def _format_usd_display(value: Any) -> str:
    """Formata um valor numérico para o formato de moeda US$ X.XXX,XX."""
    try:
        val = safe_float(value)
        return f"US$ {val:,.2f}".replace('.', '#').replace(',', '.').replace('#', ',')
    except (ValueError, TypeError):
        return "US$ 0,00"

def _format_int_display(value: Any) -> str:
    """Formata um valor para inteiro."""
    try:
        val = int(value)
        return str(val)
    except (ValueError, TypeError):
        return ""

def _format_di_number(di_number: Optional[str]) -> str:
    """Formata o número da DI para o padrão **/*******-*."""
    if di_number and isinstance(di_number, str) and len(di_number) == 10:
        return f"{di_number[0:2]}/{di_number[2:9]}-{di_number[9]}"
    return di_number if di_number is not None else ""

def _get_di_number_from_id(di_id: Optional[str]) -> str: # Alterado para string
    """Obtém o número da DI a partir do seu ID no banco de dados de XML DI."""
    if di_id is None:
        return "N/A"
    di_data = db_utils.get_declaracao_by_id(di_id)
    if di_data:
        return _format_di_number(str(di_data.get('numero_di')))
    return "DI Não Encontrada"

# Adicionado safe_float para robustez
def safe_float(value: Any, default_value: float = 0.0) -> float:
    """
    Tenta converter um valor para float. Retorna default_value se a conversão falhar.
    Útil para lidar com valores potencialmente não numéricos em dados.
    """
    if value is None:
        return default_value
    try:
        if isinstance(value, str):
            # Tenta remover caracteres de moeda e separadores de milhar comuns
            value = value.replace('R$', '').replace('US$', '').replace('.', '').replace(',', '.').strip()
        return float(value)
    except (ValueError, TypeError):
        return default_value

# --- Funções Auxiliares de UI (Popups e Ações) ---
def _display_message_box(message: str, type: str = "info"):
    """Exibe uma caixa de mensagem customizada (substitui alert()/confirm())."""
    if type == "info":
        st.info(message)
    elif type == "success":
        st.success(message)
    elif type == "warning":
        st.warning(message)
    elif type == "error":
        st.error(message)

def _display_delete_confirm_popup():
    """Exibe um pop-up de confirmação antes de excluir/arquivar um processo."""
    if not st.session_state.get('show_delete_confirm_popup', False):
        return

    process_id_to_delete = st.session_state.get('delete_process_id_to_confirm')
    process_name_to_delete = st.session_state.get('delete_process_name_to_confirm')

    if process_id_to_delete is None:
        st.session_state.show_delete_confirm_popup = False
        return

    with st.form(key=f"delete_confirm_form_{process_id_to_delete}"):
        st.markdown(f"### Confirmar Arquivamento")
        st.warning(f"Tem certeza que deseja arquivar o processo '{process_name_to_delete}' (ID: {process_id_to_delete})? Ele não será excluído do banco de dados, mas não aparecerá na tela principal.")
        
        col_yes, col_no = st.columns(2)
        with col_yes:
            if st.form_submit_button("Sim, Arquivar"):
                _delete_process_action(process_id_to_delete)
        with col_no:
            if st.form_submit_button("Não, Cancelar"):
                st.session_state.show_delete_confirm_popup = False
                st.session_state.delete_process_id_to_confirm = None
                st.session_state.delete_process_name_to_confirm = None
                # Removido st.rerun() - formulários já fazem rerun automaticamente

def _on_status_multiselect_change():
    """Callback para mudança no multiselect de status."""
    selected_options_with_counts = st.session_state.main_followup_status_multiselect
    new_selected_raw_statuses = []
    if not selected_options_with_counts or 'Todos' in selected_options_with_counts:
        new_selected_raw_statuses.append('Todos')
    else:
        for opt in selected_options_with_counts:
            new_selected_raw_statuses.append(opt.split(' (')[0])
    st.session_state.followup_selected_statuses = new_selected_raw_statuses
    
    # Invalida os caches e força recarregamento de todos os dados
    st.session_state._invalidate_filter_cache = True 
    st.session_state.all_processes_raw_data_cache = [] # Limpa os dados em cache para forçar recarregamento
    st.session_state.consolidated_groups_data_raw_cache = []
    # Removido st.rerun() - callbacks não precisam de rerun manual

def _on_process_search_change():
    """Callback para mudança no campo de pesquisa de processo principal."""
    st.session_state.followup_main_process_search_term = st.session_state.main_followup_search_processo_novo
    
    # Invalida os caches e força recarregamento de todos os dados
    st.session_state._invalidate_filter_cache = True 
    st.session_state.all_processes_raw_data_cache = [] # Limpa os dados em cache para forçar recarregamento
    st.session_state.consolidated_groups_data_raw_cache = []
    # Removido st.rerun() - callbacks não precisam de rerun manual


@st.cache_data(ttl=300) # Aplicando cache à função de filtragem global (TTL aumentado para 300s/5min)
def _apply_in_memory_filters_cached(
    last_db_update_timestamp: datetime, # Dependência do cache de dados brutos
    all_processes_raw_data: List[Dict[str, Any]], # Dados brutos (já carregados, possivelmente paginados)
    consolidated_groups_data_raw: List[Dict[str, Any]], # Grupos brutos (já carregados)
    selected_statuses: List[str],
    main_search_term: str,
    popup_search_terms: Dict[str, Any]
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]: # Corrigido para retornar uma Tupla
    """
    Aplica todos os filtros (status, pesquisa principal, pesquisa popup) aos dados em cache.
    Esta função é cacheada e só re-executa se os argumentos (filtros ou timestamp de atualização) mudarem.
    
    OTIMIZAÇÃO: Implementa filtros ultra-otimizados com máscaras booleanas e operações vetorizadas.
    """
    # Validação rápida para casos vazios
    if not all_processes_raw_data:
        return [], []
    
    # Converte para DataFrame apenas uma vez
    df_processes_all_unfiltered = pd.DataFrame(all_processes_raw_data)
    
    # Se o DataFrame estiver vazio, retorna listas vazias para evitar erros
    if df_processes_all_unfiltered.empty:
        return [], []

    # OTIMIZAÇÃO: Pré-processamento de colunas em lote com operações vetorizadas
    default_columns = {
        'Status_Geral': 'Sem Status',
        'Modal': 'Sem Modal',
        'Consolidado': 'Não',
        'Status_Arquivado': 'Não Arquivado'
    }
    
    # Aplica valores padrão em uma única operação
    for col, default_val in default_columns.items():
        if col not in df_processes_all_unfiltered.columns:
            df_processes_all_unfiltered[col] = default_val
        else:
            # Usa fillna em vez de replace para maior performance
            df_processes_all_unfiltered[col] = df_processes_all_unfiltered[col].fillna(default_val)
    
    # Garantimos que Processo_Novo existe 
    if 'Processo_Novo' not in df_processes_all_unfiltered.columns:
        if 'id' in df_processes_all_unfiltered.columns:
            df_processes_all_unfiltered['Processo_Novo'] = df_processes_all_unfiltered['id']
        else:
            df_processes_all_unfiltered['Processo_Novo'] = 'UNKNOWN_PROCESS_' + pd.Series(range(len(df_processes_all_unfiltered))).astype(str)

    # OTIMIZAÇÃO: Converte Status_Geral para categorical para ordenação rápida
    df_processes_all_unfiltered['Status_Geral'] = pd.Categorical(
        df_processes_all_unfiltered['Status_Geral'], 
        categories=CUSTOM_STATUS_ORDER, 
        ordered=True
    )
    
    # Trabalhamos com o mesmo DataFrame, evitando cópia desnecessária inicialmente
    df_filtered_in_memory = df_processes_all_unfiltered

    # Verificação otimizada
    is_main_process_name_search_active = bool(main_search_term.strip())
    
    # OTIMIZAÇÃO: Usa máscaras booleanas em vez de filtros em cascata
    mask = pd.Series(True, index=df_filtered_in_memory.index)
    
    # Filtro de arquivados
    if 'Arquivados' not in selected_statuses and not is_main_process_name_search_active:
        mask &= df_filtered_in_memory['Status_Arquivado'].isin([None, "Não Arquivado"])
    
    # Filtro de status gerais
    if 'Todos' not in selected_statuses:
        general_statuses_to_filter = [s for s in selected_statuses if s != 'Todos' and s != 'Arquivados']
        if general_statuses_to_filter:
            status_mask = df_filtered_in_memory['Status_Geral'].isin(general_statuses_to_filter)
            if 'Arquivados' in selected_statuses:
                # Combina status gerais com arquivados usando OR
                status_mask |= (df_filtered_in_memory['Status_Arquivado'] == 'Arquivado')
            mask &= status_mask
    
    # Filtro de pesquisa principal (processo)
    if main_search_term:
        mask &= df_filtered_in_memory['Processo_Novo'].astype(str).str.lower().str.contains(main_search_term.lower(), na=False)
    
    # Filtros de popup com máscaras vetorizadas
    if popup_search_terms:
        # Pré-converte as datas para evitar múltiplas conversões
        date_columns = {'ETA_Recinto': None, 'Data_Registro': None}
        date_columns_needed = any(col.startswith(('ETA_Recinto', 'Data_Registro')) for col in popup_search_terms.keys() if popup_search_terms[col])
        
        if date_columns_needed:
            for col in date_columns.keys():
                if col in df_filtered_in_memory.columns:
                    date_columns[col] = pd.to_datetime(df_filtered_in_memory[col], errors='coerce')
        
        # Aplica filtros de popup
        for col, term in popup_search_terms.items():
            if not term:  # Pula filtros vazios
                continue
                
            # Filtros de texto
            if col not in ['Processo_Novo', 'ETA_Recinto_Start', 'ETA_Recinto_End', 'Data_Registro_Start', 'Data_Registro_End']:
                if col in df_filtered_in_memory.columns:
                    mask &= df_filtered_in_memory[col].astype(str).str.lower().str.contains(str(term).lower(), na=False)
            
            # Filtros de data otimizados (evita conversões repetidas)
            elif col == 'ETA_Recinto_Start':
                if date_columns['ETA_Recinto'] is not None:
                    mask &= date_columns['ETA_Recinto'] >= pd.to_datetime(term)
            elif col == 'ETA_Recinto_End':
                if date_columns['ETA_Recinto'] is not None:
                    mask &= date_columns['ETA_Recinto'] <= pd.to_datetime(term)
            elif col == 'Data_Registro_Start':
                if date_columns['Data_Registro'] is not None:
                    mask &= date_columns['Data_Registro'] >= pd.to_datetime(term)
            elif col == 'Data_Registro_End':
                if date_columns['Data_Registro'] is not None:
                    mask &= date_columns['Data_Registro'] <= pd.to_datetime(term)
    # Aplica a máscara final e faz uma cópia eficiente apenas após todos os filtros
    df_filtered_in_memory = df_filtered_in_memory[mask]
    
    # Filtra processos não consolidados
    consolidado_mask = df_filtered_in_memory['Consolidado'] != 'Sim'
    df_non_consolidated_and_non_grouped = df_filtered_in_memory[consolidado_mask].copy()
    
    # OTIMIZAÇÃO: Converte 'Previsao_Pichau' para datetime apenas uma vez
    df_non_consolidated_and_non_grouped['Previsao_Pichau_dt'] = pd.to_datetime(
        df_non_consolidated_and_non_grouped['Previsao_Pichau'], 
        errors='coerce'
    )

    # MELHORIA: Nova ordenação solicitada - Status, Previsão Pichau, Navio, Modal
    df_non_consolidated_and_non_grouped = df_non_consolidated_and_non_grouped.sort_values(
        by=['Status_Geral', 'Previsao_Pichau_dt', 'Navio', 'Modal', 'Processo_Novo'], 
        ascending=[True, True, True, True, True], 
        na_position='last' 
    )
    # Remove a coluna temporária após a ordenação
    df_non_consolidated_and_non_grouped = df_non_consolidated_and_non_grouped.drop(columns=['Previsao_Pichau_dt'])

    # OTIMIZAÇÃO: Filtragem otimizada de grupos consolidados
    filtered_consolidated_groups_final = []
    
    # Verificação rápida para casos vazios
    if not consolidated_groups_data_raw:
        return df_non_consolidated_and_non_grouped.to_dict(orient='records'), []
    
    # Filtro de grupos consolidados otimizado com compreensão de lista
    if is_main_process_name_search_active:
        search_term_lower = main_search_term.lower()
        
        # Usa compreensão de lista em vez de loop para melhor performance
        filtered_consolidated_groups_final = [
            group for group in consolidated_groups_data_raw 
            if (str(group.get('principal_id', '')).lower() == search_term_lower) or 
               any(str(member.get('Processo_Novo', '')).lower().startswith(search_term_lower) 
                   for member in group.get('members_data', []))
        ]
    else:
        if 'Todos' not in selected_statuses:
            general_statuses_to_filter = [s for s in selected_statuses if s != 'Todos' and s != 'Arquivados']
            
            for group in consolidated_groups_data_raw:
                # Encontra o processo principal
                principal_process_data = next(
                    (m for m in group['members_data'] if str(m.get('id')) == str(group['principal_id'])), 
                    None
                )
                
                if principal_process_data:
                    group_status = principal_process_data.get('Status_Geral', 'Sem Status')
                    group_archived_status = principal_process_data.get('Status_Arquivado', 'Não Arquivado')
                    
                    is_matching_status = group_status in general_statuses_to_filter
                    is_archived = group_archived_status == 'Arquivado'

                    # Condições simplificadas com lógica mais clara
                    if any([
                        ('Arquivados' in selected_statuses and is_archived),
                        (not is_archived and is_matching_status),
                        (not is_main_process_name_search_active and not is_archived and 
                         'Arquivados' not in selected_statuses and not general_statuses_to_filter)
                    ]):
                        filtered_consolidated_groups_final.append(group)
        else:
            # Se 'Todos' está selecionado, inclui todos os grupos
            filtered_consolidated_groups_final = consolidated_groups_data_raw

    # Retorna os resultados filtrados
    return df_non_consolidated_and_non_grouped.to_dict(orient='records'), filtered_consolidated_groups_final


@st.cache_data(ttl=300) # NOVO: Cacheando a estrutura final dos expanders (TTL aumentado para 300s)
def _prepare_expander_data_cached(
    last_db_update_timestamp: datetime, # Dependência do cache de dados brutos e filtrados
    non_consolidated_data: List[Dict[str, Any]],
    consolidated_groups_data: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Prepara e organiza os dados para a exibição nos expanders, incluindo agrupamento por status e ordenação.
    Esta função é agora cacheadas e só re-executa se os argumentos (filtros ou timestamp de atualização) mudarem.
    """
    # Usar a ordem de status global definida na constante
    current_custom_status_order = list(CUSTOM_STATUS_ORDER)
    status_order_map = {status: i for i, status in enumerate(current_custom_status_order)}

    processes_by_status_non_consolidated = {}
    # Preserva a ordem dos dados já ordenados por Status → Previsão Pichau → Navio → Modal
    for row_dict_item in non_consolidated_data: # Renomeado para evitar conflito
        status = row_dict_item.get('Status_Geral', 'Sem Status')
        # Adiciona status dinamicamente se não estiver na ordem personalizada (para evitar KeyError)
        if status not in current_custom_status_order:
            current_custom_status_order.append(status) # Adiciona à lista de ordenação para mapeamento
            status_order_map[status] = len(current_custom_status_order) - 1 # Mapeia para o final

        if status not in processes_by_status_non_consolidated:
            processes_by_status_non_consolidated[status] = []
        processes_by_status_non_consolidated[status].append(row_dict_item)
    
    consolidated_groups_by_status = {}
    for group in consolidated_groups_data:
        principal_process_data = next((m for m in group['members_data'] if str(m.get('id')) == str(group['principal_id'])), None)
        if principal_process_data:
            group_status = principal_process_data.get('Status_Geral', 'Sem Status')
            # Adiciona status dinamicamente se não estiver na ordem personalizada
            if group_status not in current_custom_status_order:
                current_custom_status_order.append(group_status)
                status_order_map[group_status] = len(current_custom_status_order) - 1

            if group_status not in consolidated_groups_by_status:
                consolidated_groups_by_status[group_status] = []
            consolidated_groups_by_status[group_status].append(group)
    
    # Combina processos não consolidados e grupos consolidados sob o mesmo status
    for status, groups in consolidated_groups_by_status.items():
        if status not in processes_by_status_non_consolidated:
            processes_by_status_non_consolidated[status] = []
        for group in groups:
            processes_by_status_non_consolidated[status].append({'_is_consolidated_group': True, 'group_data': group})

    all_expander_keys_with_sort_data = []
    # Usar a ordem de status final (que pode ter sido modificada dinamicamente)
    for status in current_custom_status_order: 
        if status in processes_by_status_non_consolidated: # Verifica se o status tem dados associados
            all_expander_keys_with_sort_data.append({
                'type': 'status_group',
                'sort_key': status_order_map.get(status, len(current_custom_status_order)),
                'status': status,
                'processes_and_groups': processes_by_status_non_consolidated[status]  # Mudança: usar 'processes_and_groups' em vez de 'data'
            })

    # Retorna a lista final de informações dos expanders, já ordenada
    sorted_all_expander_keys = sorted(all_expander_keys_with_sort_data, key=lambda x: x['sort_key'])
    return sorted_all_expander_keys


def _fetch_initial_processes():
    """
    Busca TODOS os processos do DB e inicializa o cache de dados brutos.
    Agora tentará usar o carregamento progressivo otimizado, com fallback para carregamento simples.
    """
    try:
        # Tenta usar o carregamento progressivo avançado
        return _fetch_initial_processes_optimized()
    except Exception as e:
        # Em caso de erro, faz fallback para o carregamento simples
        logger.error(f"Erro no carregamento progressivo: {e}. Usando carregamento simples.")
        return _fetch_initial_processes_simple()


def _fetch_initial_processes_optimized():
    """
    NOVA FUNCIONALIDADE: Carregamento progressivo otimizado conforme OTIMIZACOES_PERFORMANCE.md.
    Carrega processos em batches controlados com feedback visual de progresso.
    """
    logger.info("Iniciando carregamento progressivo otimizado de processos")
    
    # Limpa os caches antes de iniciar
    st.session_state.all_processes_raw_data_cache = [] 
    st.session_state.consolidated_groups_data_raw_cache = []
    
    # Variáveis para controle de progresso
    total_loaded = 0
    start_time = time.time()
    processes_per_second = 0
    estimated_total = 0
    
    # Elementos da UI para feedback de progresso
    progress_container = st.empty()
    stats_container = st.empty()
    
    # Carrega processos em batches
    # Define um limite máximo de batches para evitar loops infinitos em caso de erro na contagem
    MAX_BATCHES = 100 # Ajuste conforme a expectativa de volume de dados
    BATCH_SIZE = 50 # Número de processos a buscar por batch

    for batch_num in range(MAX_BATCHES):
        batch_start_time = time.time()
        
        # Define o ponto de início para paginação baseada em cursor
        last_doc_id = None if batch_num == 0 else st.session_state.all_processes_raw_data_cache[-1].get('id')
        
        with progress_container:
            if estimated_total > 0:
                progress = min(total_loaded / estimated_total, 0.99)
                st.progress(progress, text=f"Carregando processos: {total_loaded}/{estimated_total}")
            else:
                st.progress(0.1 * batch_num, text=f"Carregando batch {batch_num+1}/{MAX_BATCHES}")
        
        # Busca o próximo batch de processos
        batch_processes, has_more = db_manager.obter_processos_filtrados(
            status_filtro=st.session_state.get('followup_selected_statuses', ['Todos']),
            termos_pesquisa=st.session_state.get('followup_popup_search_terms', {}),
            limit=BATCH_SIZE,
            start_after_doc_id=last_doc_id
        )
        
        # Adiciona ao cache
        st.session_state.all_processes_raw_data_cache.extend(batch_processes)
        
        # Atualiza métricas de progresso
        batch_size = len(batch_processes)
        total_loaded += batch_size
        batch_time = time.time() - batch_start_time
        
        # Estima o total se ainda temos mais dados
        if has_more and batch_size > 0:
            # Ajusta a estimativa baseado no que já vimos
            if batch_num == 0:
                # Primeira estimativa: assumimos distribuição uniforme entre status
                estimated_total = batch_size * 5  # Estimativa inicial conservadora
            else:
                # Refina estimativa com o que já carregamos
                estimated_total = max(estimated_total, int(total_loaded * 1.2))
        else:
            # Se não há mais, o total é o que já carregamos
            estimated_total = total_loaded
        
        # Calcula velocidade e ETA
        elapsed = time.time() - start_time
        processes_per_second = total_loaded / elapsed if elapsed > 0 else 0
        remaining = estimated_total - total_loaded
        eta_seconds = remaining / processes_per_second if processes_per_second > 0 else 0
        
        # Atualiza estatísticas
        with stats_container:
            st.caption(f"Velocidade: {processes_per_second:.1f} processos/s | ETA: {eta_seconds:.1f}s | Batch {batch_num+1}: {batch_size} processos em {batch_time:.2f}s")
        
        # Para se não há mais processos ou o batch veio vazio
        if not has_more or batch_size == 0:
            break
    
    # Finaliza a barra de progresso
    with progress_container:
        st.progress(1.0, text=f"Carregamento completo: {total_loaded} processos")
    
    # Carrega os grupos consolidados
    with st.spinner("Carregando grupos consolidados..."):
        from app_logic import vincular_utils  # Import aqui para evitar circular import
        all_consolidated_groups = vincular_utils.listar_grupos_consolidados()
        st.session_state.consolidated_groups_data_raw_cache = all_consolidated_groups
    
    # Limpa os elementos de progresso
    progress_container.empty()
    stats_container.empty()
    
    # Log de performance
    total_time = time.time() - start_time
    logger.info(f"Carregamento progressivo otimizado: {total_loaded} processos, {len(all_consolidated_groups)} grupos em {total_time:.1f}s ({processes_per_second:.1f} proc/s)")
    
    return total_loaded


def _fetch_initial_processes_simple():
    """
    Versão simplificada da busca de processos original, usado como fallback.
    """
    logger.info("Usando carregamento simples como fallback")
    with st.spinner("Carregando todos os processos..."):
        # Limpa os dados em cache antes de buscar
        st.session_state.all_processes_raw_data_cache = [] 
        st.session_state.consolidated_groups_data_raw_cache = []
        st.session_state.has_more_processes = False # Não há mais processos, pois carregamos tudo

        if db_manager._USE_FIRESTORE_AS_PRIMARY and not st.session_state.get('firebase_ready', False):
            st.error("Conexão com Firestore não estabelecida. Não é possível carregar os processos de Follow-up.")
            return 0
        
        if not db_manager.criar_tabela_followup():
            st.error(f"Não foi possível verificar/criar as coleções do banco de dados de Follow-up. Verifique sua configuração e logs.")
            return 0

        # Carrega TODOS os processos de uma vez (limit=None)
        all_processes, _ = db_manager.obter_processos_filtrados(
            status_filtro=st.session_state.get('followup_selected_statuses', ['Todos']),
            termos_pesquisa=st.session_state.get('followup_popup_search_terms', {}),
            limit=None, # Carrega todos os processos
            start_after_doc_id=None
        )
        st.session_state.all_processes_raw_data_cache = all_processes
        
        # Carrega os grupos consolidados
        from app_logic import vincular_utils  # Import aqui para evitar circular import
        all_consolidated_groups = vincular_utils.listar_grupos_consolidados()
        st.session_state.consolidated_groups_data_raw_cache = all_consolidated_groups
        
        # Atualiza as opções de filtro de status
        _update_status_filter_options(pd.DataFrame(st.session_state.all_processes_raw_data_cache))
        
        logger.info(f"_fetch_initial_processes: Carregados {len(all_processes)} processos totais.")
        # Força a invalidação dos caches de filtragem e preparação do expander
        _apply_in_memory_filters_cached.clear()
        _prepare_expander_data_cached.clear()


# Função para encapsular a chamada às funções de filtro/preparação cacheada e atualizar o session_state
def _call_apply_filters_and_update_session_state():
    """
    Chama as funções de filtro/preparação cacheada e atualiza os dados no session_state.
    Força a invalidação do cache de filtros e da estrutura do expander se _invalidate_filter_cache for True.
    Esta função opera sobre `all_processes_raw_data_cache` que é gerenciado pela paginação.
    """
    # Se a flag de invalidação estiver setada, limpa os caches relevantes
    if st.session_state.get('_invalidate_filter_cache', False):
        _apply_in_memory_filters_cached.clear()
        _prepare_expander_data_cached.clear()
        _reset_cards_loading_state()  # Reseta estado de carregamento de cards quando filtros mudam
        _initialize_table_loading_state() # Reseta estado de carregamento de tabela quando filtros mudam
        st.session_state._invalidate_filter_cache = False # Reseta a flag
    
    # Adiciona o filtro de 'Arquivados' explicitamente para _apply_in_memory_filters_cached se 'Arquivados' está em selected_statuses
    selected_statuses_for_filter = st.session_state.get('followup_selected_statuses', ['Todos'])
    if 'Arquivados' in st.session_state.get('followup_selected_statuses', []):
        if 'Arquivados' not in selected_statuses_for_filter: # Garante que 'Arquivados' esteja na lista se foi selecionado
            selected_statuses_for_filter.append('Arquivados')

    # Chama a função de filtro cacheada (ela agora trabalha com os dados já carregados no cache de raw_data)
    df_non_consolidated_data, consolidated_groups_data = _apply_in_memory_filters_cached(
        st.session_state.get('last_db_update', datetime.min), # Passa o timestamp como argumento de cache
        st.session_state.all_processes_raw_data_cache,
        st.session_state.consolidated_groups_data_raw_cache,
        selected_statuses_for_filter, # Usa a lista de status ajustada
        st.session_state.get('followup_main_process_search_term', ''),
        st.session_state.get('followup_popup_search_terms', {})
    )
    st.session_state.followup_processes_data_non_consolidated = df_non_consolidated_data
    st.session_state.consolidated_groups_data = consolidated_groups_data
    
    # Chama a função de preparação do expander cacheada
    expander_data = _prepare_expander_data_cached(
        st.session_state.get('last_db_update', datetime.min), # Passa o timestamp como argumento de cache
        st.session_state.followup_processes_data_non_consolidated,
        st.session_state.consolidated_groups_data
    )
    st.session_state.sorted_all_expander_keys = expander_data
    
    # Inicializa o estado de carregamento de cards para os status disponíveis
    available_statuses = [item['status'] for item in expander_data]
    _reset_cards_loading_state()  # Inicializa cards para os status disponíveis
    _initialize_table_loading_state()

def _update_status_filter_options(df_all_processes_for_options: pd.DataFrame):
    """Atualiza as opções do filtro de status com base nos status do DB, incluindo contagens."""
    # Se o DataFrame estiver vazio, retorna apenas "Todos"
    if df_all_processes_for_options.empty:
        st.session_state.followup_raw_status_options_for_multiselect = ["Todos"]
        st.session_state.followup_all_status_options = ["Todos"]
        return

    status_counts = df_all_processes_for_options['Status_Geral'].replace(np.nan, 'Sem Status').astype(str).value_counts().to_dict()
    
    arquivados_count = df_all_processes_for_options[
        (df_all_processes_for_options['Status_Arquivado'] == 'Arquivado') | 
        (df_all_processes_for_options['Status_Geral'] == 'Arquivados') 
    ].shape[0]
    
    all_raw_status_options = list(status_counts.keys())
    
    # Usa a ordem de status pré-determinada definida na constante global
    custom_order_for_options = [status for status in CUSTOM_STATUS_ORDER if status != 'Arquivados']
    
    sorted_status_options = sorted([s for s in all_raw_status_options if s not in custom_order_for_options and s != "Arquivados"])
    final_ordered_status_options = [s for s in custom_order_for_options if s in all_raw_status_options] + sorted_status_options

    formatted_options_with_counts = []
    for status in final_ordered_status_options:
        count = status_counts.get(status, 0)
        formatted_options_with_counts.append(f"{status} ({count})")
    
    if arquivados_count > 0:
        formatted_options_with_counts.append(f"Arquivados ({arquivados_count})")
        if 'Arquivados' not in db_manager.STATUS_OPTIONS: 
             st.session_state.followup_raw_status_options_for_multiselect = ["Todos"] + final_ordered_status_options + ["Arquivados"]
        else:
            st.session_state.followup_raw_status_options_for_multiselect = ["Todos"] + final_ordered_status_options
    else:
        st.session_state.followup_raw_status_options_for_multiselect = ["Todos"] + final_ordered_status_options

    st.session_state.followup_all_status_options = ["Todos"] + formatted_options_with_counts


def _open_edit_process_popup(process_identifier: Optional[Any] = None, is_cloning: bool = False):
    """Navega para a página dedicada de formulário de processo."""
    st.session_state.form_process_identifier = process_identifier
    st.session_state.form_is_cloning = is_cloning
    # MELHORIA: Usa callback otimizado para edição de processo específico
    st.session_state.form_reload_processes_callback = lambda: _optimized_reload_after_process_edit(process_identifier)
    st.session_state.current_page = "Formulário Processo"
    st.session_state.show_filter_search_popup = False
    st.session_state.show_delete_confirm_popup = False
    st.session_state.show_change_status_popup = False 
    st.session_state.show_edit_checklist_popup = False 
    # Removido st.rerun() - não necessário

def _open_process_query_page(process_identifier: Any):
    """Navega para a nova página de consulta de processo."""
    st.session_state.query_process_identifier = process_identifier
    st.session_state.current_page = "Consulta de Processo"
    st.session_state.show_filter_search_popup = False
    st.session_state.show_delete_confirm_popup = False
    st.session_state.show_change_status_popup = False 
    st.session_state.show_edit_checklist_popup = False 
    # Removido st.rerun() - não necessário

def _open_vincular_consolidado_page(process_id: Any):
    """Navega para a nova página de vincular consolidado."""
    st.session_state.process_id_to_vincular = process_id
    st.session_state.current_page = "Vincular Consolidado"
    st.session_state.show_filter_search_popup = False
    st.session_state.show_delete_confirm_popup = False
    st.session_state.show_change_status_popup = False 
    st.session_state.show_edit_checklist_popup = False
    # Removido st.rerun() - não necessário


def _navigate_from_card_action(action_type: str, process_id_or_data: Any, is_cloning: bool = False):
    """
    Controla a navegação e atualização de session_state para ações do card.
    O Streamlit faz o rerun automaticamente quando necessário.
    """
    if action_type == "query":
        st.session_state.query_process_identifier = process_id_or_data
        st.session_state.current_page = "Consulta de Processo"
    elif action_type == "change_status":
        st.session_state.show_change_status_popup = True
        st.session_state.process_id_to_change_status = process_id_or_data.get('id')
        st.session_state.process_name_to_change_status = process_id_or_data.get('Processo_Novo')
        st.session_state.process_current_observacao = process_id_or_data.get('Observacao')
    elif action_type == "edit":
        st.session_state.selected_process_data = process_id_or_data
        st.session_state.form_process_identifier = process_id_or_data.get('id')
        st.session_state.current_page = "Formulário Processo"
    elif action_type == "clone":
        st.session_state.selected_process_data = process_id_or_data 
        st.session_state.form_process_identifier = process_id_or_data.get('id')
        st.session_state.form_is_cloning = True
        st.session_state.current_page = "Formulário Processo"
    elif action_type == "edit_checklist":
        st.session_state.show_edit_checklist_popup = True
        st.session_state.checklist_process_id_to_edit = process_id_or_data.get('id')
        st.session_state.checklist_process_name_to_edit = process_id_or_data.get('Processo_Novo')
    elif action_type == "group_consolidated":
        st.session_state.process_id_to_vincular = process_id_or_data.get('id')
        st.session_state.current_page = "Vincular Consolidado"
    elif action_type == "archive":
        st.session_state.show_delete_confirm_popup = True
        st.session_state.delete_process_id_to_confirm = process_id_or_data.get('id')
        st.session_state.delete_process_name_to_confirm = process_id_or_data.get('Processo_Novo')
    
    # Reintroduzindo st.rerun() aqui para garantir que a navegação e o estado do popup sejam processados.
    st.rerun()


def _delete_process_action(process_id: Any):
    """Arquiva um processo no banco de dados (não exclui permanentemente)."""
    with st.spinner("Arquivando processo..."):
        if db_manager.arquivar_processo(process_id):
            st.success(f"Processo ID {process_id} arquivado com sucesso! Ele não aparecerá mais na tela principal por padrão.")
        else:
            st.error(f"Falha ao arquivar processo ID {process_id}.")
        
        st.session_state.show_delete_confirm_popup = False
        st.session_state.delete_process_id_to_confirm = None
        st.session_state.delete_process_name_to_confirm = None
        st.session_state.selected_process_data = None 
        
        # MELHORIA: Usa atualização parcial em vez de reload completo
        success = _partial_cache_update_after_edit(process_id, "archive")
        if not success:
            # Se a atualização parcial falhou, força reload completo
            st.session_state.last_db_update = datetime.now()
            st.session_state.all_processes_raw_data_cache = []
            st.session_state.consolidated_groups_data_raw_cache = []
        # Removido st.rerun() - não necessário

def _change_process_status_action(process_id: Any, new_status: str, new_observacao: Optional[str]): 
    """Altera o status e a observação de um processo no banco de dados."""
    with st.spinner("Atualizando status do processo..."):
        user_info = st.session_state.get('user_info', {'username': 'Desconhecido'})
        current_username = user_info.get('username', 'Desconhecido')

        original_process_data_raw = db_manager.obter_processo_por_id(process_id) if isinstance(process_id, int) else db_manager.obter_processo_by_processo_novo(process_id)
        if not original_process_data_raw:
            st.error(f"Processo ID {process_id} não encontrado para alteração de status/observação.")
            return

        original_process_data = dict(original_process_data_raw)
        original_status = original_process_data.get('Status_Geral')
        original_observacao = original_process_data.get('Observacao')

        updates = {}
        if new_status != original_status:
            updates["Status_Geral"] = new_status
        if new_observacao != original_observacao: 
            updates["Observacao"] = new_observacao

        if updates: 
            if db_manager.atualizar_processo(process_id, updates):
                if "Status_Geral" in updates:
                    db_manager.inserir_historico_processo(
                        process_id, "Status_Geral", original_status, new_status,
                        current_username, db_type="Firestore" if db_manager._USE_FIRESTORE_AS_PRIMARY else "SQLite"
                    )
                if "Observacao" in updates:
                    db_manager.inserir_historico_processo(
                        process_id, "Observacao", original_observacao, new_observacao,
                        current_username, db_type="Firestore" if db_manager._USE_FIRESTORE_AS_PRIMARY else "SQLite"
                    )
                st.success(f"Processo ID {process_id} atualizado com sucesso!")
            else:
                st.error(f"Falha ao atualizar processo ID {process_id}.")
        else:
            st.info("Nenhuma alteração de status ou observação detectada.")
        
        st.session_state.show_change_status_popup = False
        st.session_state.process_id_to_change_status = None
        st.session_state.process_name_to_change_status = None
        st.session_state.process_current_observacao = None 
        
        # MELHORIA: Usa atualização parcial em vez de reload completo
        success = _partial_cache_update_after_edit(process_id, "status_change")
        if not success:
            # Se a atualização parcial falhou, força reload completo
            st.session_state.last_db_update = datetime.now()
            st.session_state.all_processes_raw_data_cache = []
            st.session_state.consolidated_groups_data_raw_cache = []
        # Removido st.rerun() - não necessário


def _display_change_status_popup():
    """Exibe um pop-up para alterar o status e a observação de um processo."""
    if not st.session_state.get('show_change_status_popup', False):
        return

    process_id = st.session_state.get('process_id_to_change_status')
    process_name = st.session_state.get('process_name_to_change_status')

    if process_id is None:
        st.session_state.show_change_status_popup = False
        return

    current_process_data = db_manager.obter_processo_por_id(process_id) if isinstance(process_id, int) else db_manager.obter_processo_by_processo_novo(process_id)
    current_status = current_process_data.get('Status_Geral') if current_process_data else None
    current_observacao = current_process_data.get('Observacao', '') if current_process_data else ''

    with st.form(key=f"change_status_form_{process_id}"):
        st.markdown(f"### Alterar Status e Observação do Processo")
        st.info(f"Ajuste para o processo: **{process_name}**")

        status_options = db_manager.STATUS_OPTIONS
        default_index_status = 0
        if current_status in status_options:
            default_index_status = status_options.index(current_status)
        new_status = st.selectbox("Novo Status:", options=status_options, index=default_index_status, key="new_status_selectbox_popup")

        new_observacao = st.text_area("Observação:", value=current_observacao, key="new_observacao_textarea_popup")

        col_apply, col_cancel = st.columns(2)
        with col_apply:
            if st.form_submit_button("Aplicar Alterações"):
                _change_process_status_action(process_id, new_status, new_observacao)
        with col_cancel:
            if st.form_submit_button("Cancelar"):
                st.session_state.show_change_status_popup = False
                st.session_state.process_id_to_change_status = None
                st.session_state.process_name_to_change_status = None
                st.session_state.process_current_observacao = None
                # Removido st.rerun() - formulários já fazem rerun automaticamente

def _display_edit_checklist_popup():
    """Exibe um pop-up para alterar os itens de checklist Sim/Não de um processo."""
    if not st.session_state.get('show_edit_checklist_popup', False):
        return

    process_id = st.session_state.get('checklist_process_id_to_edit')
    process_name = st.session_state.get('checklist_process_name_to_edit')

    if process_id is None:
        st.session_state.show_edit_checklist_popup = False
        return

    current_process_data = db_manager.obter_processo_por_id(process_id) if isinstance(process_id, int) else db_manager.obter_processo_by_processo_novo(process_id)
    if not current_process_data:
        st.error(f"Processo ID {process_id} não encontrado para edição do checklist.")
        st.session_state.show_edit_checklist_popup = False
        return

    with st.form(key=f"edit_checklist_form_{process_id}"):
        st.markdown(f"### Editar Checklist do Processo")
        st.info(f"Ajustar itens de checklist para: **{process_name}**")

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
                updated_checklist_values[db_field] = None 


        col_apply, col_cancel = st.columns(2)
        with col_apply:
            if st.form_submit_button("Salvar Checklist"):
                user_info = st.session_state.get('user_info', {'username': 'Desconhecido'})
                username = user_info.get('username')
                
                changes_for_history = {}
                for field, new_val in updated_checklist_values.items():
                    old_val = current_process_data.get(field)
                    if str(old_val) != str(new_val): 
                        changes_for_history[field] = (old_val, new_val)

                if db_manager.atualizar_processo(process_id, updated_checklist_values):
                    st.success(f"Checklist do processo {process_id} atualizado com sucesso!")
                    for field_name, (old_val, new_val) in changes_for_history.items():
                        db_manager.inserir_historico_processo(
                            process_id, field_name, old_val, new_val,
                            username, db_type="Firestore" if db_manager._USE_FIRESTORE_AS_PRIMARY else "SQLite"
                        )
                    
                    st.session_state.show_edit_checklist_popup = False
                    st.session_state.checklist_process_id_to_edit = None
                    
                    # MELHORIA: Usa atualização parcial em vez de reload completo
                    success = _partial_cache_update_after_edit(process_id, "checklist_edit")
                    if not success:
                        # Se a atualização parcial falhou, força reload completo
                        st.session_state.last_db_update = datetime.now()
                        st.session_state.all_processes_raw_data_cache = []
                        st.session_state.consolidated_groups_data_raw_cache = []
                    # Removido st.rerun() - não necessário
                else:
                    st.error(f"Falha ao atualizar checklist do processo {process_id}.")
        with col_cancel:
            if st.form_submit_button("Cancelar"):
                st.session_state.show_edit_checklist_popup = False
                st.session_state.checklist_process_id_to_edit = None
                # Removido st.rerun() - não necessário

def _open_filter_search_popup():
    """Abre um pop-up para a seleção de filtros e termos de pesquisa."""
    st.session_state.show_filter_search_popup = True
    # Removido st.rerun() - não necessário

def _display_filter_search_popup():
    """Exibe o pop-up de filtros e pesquisa."""
    if not st.session_state.get('show_filter_search_popup', False):
        return

    with st.form(key="filter_search_form"):
        st.markdown("### Mais Filtros e Pesquisa de Processos")

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
                # Removido st.rerun() - não necessário
        with col_buttons_popup[1]:
            if st.form_submit_button("Limpar Mais Filtros"):
                st.session_state.followup_popup_search_terms = {} 
                # Invalida os caches ao mudar os filtros principais
                st.session_state._invalidate_filter_cache = True 
                st.session_state.all_processes_raw_data_cache = [] # Limpa os dados em cache para forçar recarregamento
                st.session_state.consolidated_groups_data_raw_cache = []
                # Removido st.rerun() - não necessário
        
        if st.form_submit_button("Fechar"):
            st.session_state.show_filter_search_popup = False
            # Removido st.rerun() - não necessário

def _export_processes_to_excel(df_data: pd.DataFrame):
    """Exporta os dados do DataFrame para um arquivo Excel em memória."""
    output = io.BytesIO()
    writer = pd.ExcelWriter(output, engine='xlsxwriter')

    column_display_names = {
        "Processo_Novo": "Processo", "Fornecedor": "Fornecedor", "Tipos_de_item": "Tipo de Item",
        "Observacao": "Observação", "Data_Embarque": "Data Embarque", "ETA_Recinto": "ETA Recinto",
        "Previsao_Pichau": "Previsão Pichau", "Documentos_Revisados": "Docs Revisados",
        "Conhecimento_Embarque": "Conhecimento Embarque", "Descricao_Feita": "Descrição Feita",
        "Descricao_Enviada": "Descrição Enviada", "Nota_feita": "Nota Feita", "N_Invoice": "Nº Invoice",
        "Quantidade": "Quantidade", "Valor_USD": "Valor (USD)", "Pago": "Pago?",
        "Nº Ordem Compra": "Nº Ordem Compra", "Data Compra": "Data Compra",
        "Estimativa_Frete_USD": "Estimativa Frete (USD)", "Agente_de_Carga_Novo": "Agente de Carga",
        "Status_Geral": "Status Geral", "Modal": "Modal", "Navio": "Navio", "Origem": "Origem",
        "Destino": "Destino", "INCOTERM": "INCOTERM", "Comprador": "Comprador",
        "Quantidade_Containers": "Qtd. Containers", "Data_Registro": "Data Registro",
        "Estimativa_Impostos_Total": "Imp. Totais (R$)", "Estimativa_Dolar_BRL": "Câmbio Estimado (R$)", 
        "Estimativa_Seguro_BRL": "Estimativa Seguro (R$)", "Estimativa_II_BR": "Estimativa II (R$)", 
        "Estimativa_IPI_BR": "Estimativa IPI (R$)", "Estimativa_PIS_BR": "Estimativa PIS (R$)", 
        "Estimativa_COFSINS_BR": "Estimativa COFINS (R$)", "Estimativa_ICMS_BR": "Estimativa ICMS (R$)", 
        "id": "ID do Processo",
        "Consolidado": "Consolidado?", 
        "LCL_Processos_Quantidade": "Quantos processos - LCL", 
    }
    
    cols_to_export = [col for col in column_display_names.keys() if col in df_data.columns]
    df_export = df_data[cols_to_export].copy()
    df_export = df_export.rename(columns={k: v for k, v in column_display_names.items() if k in df_export.columns})

    date_cols = ["Data Embarque", "ETA Recinto", "Previsão Pichau", "Data Compra", "Data Registro"]
    currency_usd_cols = ["Valor (USD)", "Estimativa Frete (USD)"]
    currency_brl_cols = ["Imp. Totais (R$)", "Câmbio Estimado (R$)", "Estimativa Seguro (R$)", "Estimativa II (R$)", 
                         "Estimativa IPI (R$)", "Estimativa PIS (R$)", 
                         "Estimativa COFINS (R$)", "Estimativa ICMS (R$)"] 
    
    for col in date_cols:
        if col in df_export.columns:
            df_export[col] = df_export[col].apply(lambda x: _format_date_display(x) if pd.notna(x) else '')
            
    for col in currency_usd_cols:
        if col in df_export.columns:
            df_export[col] = pd.to_numeric(df_export[col], errors='coerce').fillna(0).apply(lambda x: f"{x:,.2f}".replace('.', '#').replace(',', '.').replace('#', ','))

    for col in currency_brl_cols:
        if col in df_export.columns:
            df_export[col] = pd.to_numeric(df_export[col], errors='coerce').fillna(0).apply(lambda x: f"R$ {x:,.2f}".replace('.', '#').replace(',', '.').replace('#', ','))
    
    df_export.to_excel(writer, index=False, sheet_name='Processos de Importação')
    writer.close()
    output.seek(0)
    return output

# Cores para os status (revisadas para um visual más agradável e claro)
STATUS_COLORS_HEX = {
    'Encerrado': "#FFFDFD",        # Cinza Neutro
    'Chegada Pichau': "#636464",   # Azul Padrão
    'Agendado': "#888888",         # Roxo Suave
    'Liberado': '#28A745',         # Verde Sucesso
    'Registrado': "#CFE600",       # Azul Ciano Claro
    'Chegada Recinto': "#0787FF",  # Amarelo Alerta
    'Embarcado': '#DC3545',        # Vermelho Erro/Perigo
    'Limbo Consolidado': '#6C757D',# Cinza Chumbo
    'Limbo Saldo': "#0A6D05",      # Cinza Chumbo
    'Pré Embarque': '#20C997',     # Verde Água Suave
    'Verificando': '#FD7E14',      # Laranja Alerta
    'Em Produção': '#6F42C1',      # Roxo Médio
    'Processo Criado': '#A9A9A9',  # Cinza Claro para o padrão
    'Arquivados': '#DC3545',       # Vermelho para status "Arquivado"
    'Sem Status': '#343A40',       # Cinza Escuro para campos vazios/desconhecidos
    'Status Desconhecido': '#343A40', # Cinza Escuro
}

def _get_text_color(background_hex_color: str) -> str:
    """Determina a cor do texto (branco ou preto) com base na cor de fundo para melhor contraste."""
    # Lógica para determinar a cor do texto (simplificada para exemplo)
    # Uma implementação mais robusta calcularia a luminância
    if background_hex_color in ['#FFFDFD', '#CFE600']: # Cores claras
        return '#333333' # Texto escuro
    return '#F8F8F8' # Texto claro


def _format_status_display(status_geral: str, status_arquivado: str) -> Tuple[str, str]:
    """Formata o texto e a cor do status para exibição no card."""
    display_status = status_geral
    
    if status_arquivado == 'Arquivado':
        display_status = "Arquivado"
        status_color = STATUS_COLORS_HEX.get('Arquivados', '#DC3545') # Vermelho para arquivados
    else:
        status_color = STATUS_COLORS_HEX.get(status_geral, '#343A40') # Default para cinza escuro

    return display_status, status_color

def _format_checkbox_display(value: Any) -> str:
    """Formata valores para ícones de checkbox (✅, ❌, ➖)."""
    if str(value).lower() == "sim":
        return "✅"
    elif str(value).lower() == "não":
        return "❌"
    return "➖"

@st.cache_resource # Cacheia as permissões do usuário para evitar recomputação
def _get_cached_user_permissions():
    """Obtém e cacheia as permissões do usuário."""
    user_info = st.session_state.get('user_info', {})
    is_admin = user_info.get('is_admin', False)
    allowed_screens = user_info.get('allowed_screens', [])
    
    # Mapeia telas para permissões específicas, se necessário
    permission_map = {
        "Consulta de Processo": "Consulta de Processo" in allowed_screens,
        "Atualizar Dados de Processo": "Atualizar Dados de Processo" in allowed_screens,
        "Formulário Processo": "Formulário Processo" in allowed_screens,
        "Vincular Consolidado": "Vincular Consolidado" in allowed_screens,
        "Gerenciamento de Processos em Massa": "Gerenciamento de Processos em Massa" in allowed_screens,
        "Ações do Processo (Popover)": "Ações do Processo (Popover)" in allowed_screens,
        "Mais Opções (Popover)": "Mais Opções (Popover)" in allowed_screens,
        "Exportar Excel": "Exportar Excel" in allowed_screens,
    }
    
    return {
        "is_admin": is_admin,
        "user_allowed_screens": allowed_screens,
        "permission_map": permission_map
    }

def _reset_cards_loading_state():
    """Reseta o estado de carregamento dos cards para todos os status, mas só se ainda não existe (evita sobrescrever após load more)."""
    if 'loaded_cards_per_status' not in st.session_state:
        st.session_state.loaded_cards_per_status = {status: INITIAL_CARDS_PER_CHUNK for status in [item['status'] for item in st.session_state.sorted_all_expander_keys]}
        # print('[DEBUG] Inicializou loaded_cards_per_status') # Comentado para evitar poluir o log
    if 'show_load_more_buttons' not in st.session_state:
        st.session_state.show_load_more_buttons = {status: True for status in [item['status'] for item in st.session_state.sorted_all_expander_keys]}
        # print('[DEBUG] Inicializou show_load_more_buttons') # Comentado para evitar poluir o log

def _load_more_cards_for_status(status: str):
    """Carrega mais cards para um status específico."""
    current_loaded = st.session_state.loaded_cards_per_status.get(status, INITIAL_CARDS_PER_CHUNK)
    st.session_state.loaded_cards_per_status[status] = current_loaded + st.session_state.cards_per_chunk
    # print(f"[DEBUG] Carregando mais cards para status: {status} (total agora: {st.session_state.loaded_cards_per_status[status]})") # Comentado para evitar poluir o log
    st.rerun() # O Streamlit fará o rerun automaticamente

def _reset_main_filters():
    """Reseta os filtros principais de status e pesquisa de processo."""
    st.session_state.followup_selected_statuses = ['Todos']
    st.session_state.followup_main_process_search_term = ''
    st.session_state.followup_popup_search_terms = {}
    st.session_state.last_db_update = datetime.now() # Força recarregamento de todos os caches
    
    # Limpa os dados em cache para forçar recarregamento completo
    st.session_state.all_processes_raw_data_cache = []
    st.session_state.consolidated_groups_data_raw_cache = []
    # Removido st.rerun() - não necessário

def _toggle_view_mode():
    """Alterna o modo de visualização entre 'cards' e 'tables'."""
    if st.session_state.view_mode == 'cards':
        st.session_state.view_mode = 'tables' 
    else:
        st.session_state.view_mode = 'cards'
    # Removido st.rerun() - não necessário

def _partial_cache_update_after_edit(process_id: Any, update_type: str):
    """
    Tenta atualizar parcialmente o cache de dados brutos após uma edição.
    Retorna True se a atualização parcial foi bem-sucedida, False caso contrário (forçando um reload completo).
    """
    try:
        updated_process_data = db_manager.obter_processo_por_id(process_id) if isinstance(process_id, int) else db_manager.obter_processo_by_processo_novo(process_id)
        if not updated_process_data:
            logger.warning(f"Processo {process_id} não encontrado após edição. Forçando recarregamento completo.")
            return False

        found_and_updated = False
        # Atualiza o cache de dados brutos
        for i, proc in enumerate(st.session_state.all_processes_raw_data_cache):
            if proc.get('id') == process_id:
                st.session_state.all_processes_raw_data_cache[i] = updated_process_data
                found_and_updated = True
                break
        
        # Se o processo não foi encontrado no cache principal, pode ser um novo processo (no caso de adição)
        # ou um processo que foi filtrado e não está no cache atual. Neste caso, força recarregamento completo.
        if not found_and_updated and update_type != "add":
            logger.warning(f"Processo {process_id} não encontrado no cache para atualização parcial. Forçando recarregamento completo.")
            return False
        elif update_type == "add": # Se for uma adição, adiciona ao cache
            st.session_state.all_processes_raw_data_cache.append(updated_process_data)
            logger.info(f"Novo processo {process_id} adicionado ao cache.")

        # Invalida os caches de filtro e preparação do expander para que sejam recomputados com os dados atualizados
        st.session_state._invalidate_filter_cache = True
        return True
    except Exception as e:
        logger.error(f"Erro na atualização parcial do cache para processo {process_id}: {e}")
        return False

def _optimized_reload_after_process_edit(process_identifier: Any):
    """
    Callback otimizado para recarregar processos após edição no formulário.
    Tenta uma atualização parcial do cache. Se falhar, força um recarregamento completo.
    """
    success = _partial_cache_update_after_edit(process_identifier, "edit")
    if not success:
        st.session_state.last_db_update = datetime.now()
        st.session_state.all_processes_raw_data_cache = []
        st.session_state.consolidated_groups_data_raw_cache = []
    _call_apply_filters_and_update_session_state() # Re-aplica filtros e prepara UI

def _render_consolidated_group_card(group_data: Dict[str, Any], unique_id_for_key: str):
    """Renderiza um card para um grupo consolidado com informações agregadas e layout similar ao card individual."""
    principal_id = group_data.get('principal_id', 'N/A')
    members_data = group_data.get('members_data', [])
    
    # Encontra o processo principal para pegar status e previsão
    principal_process_data = next((m for m in members_data if str(m.get('id')) == str(principal_id)), None)
    
    group_status = principal_process_data.get('Status_Geral', 'Consolidado') if principal_process_data else 'Consolidado'
    previsao_pichau = _format_date_display(principal_process_data.get('Previsao_Pichau')) if principal_process_data else 'N/A'
    
    display_status, status_display_color = _format_status_display(group_status, 'Não Arquivado') # Grupos não são "arquivados" diretamente

    # Agregação de dados dos membros
    total_quantidade = sum(safe_float(member.get('Quantidade', 0)) for member in members_data)
    total_valor_usd = sum(safe_float(member.get('Valor_USD', 0.0)) for member in members_data)
    
    unique_fornecedores = set(member.get('Fornecedor', 'N/A') for member in members_data if member.get('Fornecedor'))
    fornecedores_display = ", ".join(unique_fornecedores) if unique_fornecedores else "N/A"
    
    unique_invoices = set(member.get('N_Invoice', 'N/A') for member in members_data if member.get('N_Invoice'))
    invoices_display = ", ".join(unique_invoices) if unique_invoices else "N/A"

    earliest_data_compra = None
    earliest_data_embarque = None
    
    for member in members_data:
        if member.get('Data_Compra'):
            try:
                current_date = datetime.strptime(member['Data_Compra'], "%Y-%m-%d")
                if earliest_data_compra is None or current_date < earliest_data_compra:
                    earliest_data_compra = current_date
            except ValueError:
                pass
        if member.get('Data_Embarque'):
            try:
                current_date = datetime.strptime(member['Data_Embarque'], "%Y-%m-%d")
                if earliest_data_embarque is None or current_date < earliest_data_embarque:
                    earliest_data_embarque = current_date
            except ValueError:
                pass

    earliest_data_compra_display = _format_date_display(earliest_data_compra.strftime("%Y-%m-%d")) if earliest_data_compra else 'N/A'
    earliest_data_embarque_display = _format_date_display(earliest_data_embarque.strftime("%Y-%m-%d")) if earliest_data_embarque else 'N/A'

    # Mock de dados de checklist para o grupo consolidado (poderiam ser agregados dos membros)
    # Para simplificar, vamos usar um status padrão para o grupo consolidado
    pago = "➖"
    docs_revisados = "➖"
    conhecimento_embarque = "➖"
    descricao_feita = "➖"
    descricao_enviada = "➖"
    nota_feita = "➖"
    conferido = "➖"

    modal_icon = '📦' # Ícone de caixa para grupo consolidado
    
    with st.container():
        st.markdown(f"<div class='process-card-container-inner' style='padding: 5px; margin-bottom: 2px;'>", unsafe_allow_html=True)

        col_main_info, col_dates_status, col_docs_status, col_actions = st.columns([0.15, 0.25, 0.35, 0.05])
        with col_main_info:
            st.markdown(f"<div style='font-size: 2.5em; text-align: center; color: #F8F8F8;'>{modal_icon}</div>", unsafe_allow_html=True)
            st.markdown(f"""
                <div style='color: #E0E0E0; text-align: center;'>
                    <strong>{principal_id}</strong><br>
                    <small>({len(members_data)} processos)</small><br>
                </div>
            """, unsafe_allow_html=True)

        with col_dates_status:
            st.markdown(f"""
                <div style='color: #E0E0E0;'>
                    <span class="process-card-status-text" style="background-color: {status_display_color}; color: {_get_text_color(status_display_color)}; font-size: 1.2em;">{display_status}</span><br>
                    <strong>Qtd Total:</strong> {_format_int_display(total_quantidade)} | <strong>Valor Total (US$):</strong> {_format_usd_display(total_valor_usd).replace('US$', '')}<br>
                    <small>Nº Invoices: {invoices_display}</small><br>
                    <strong>Previsão Pichau (Principal):</strong> {previsao_pichau}<br>
                </div>
            """, unsafe_allow_html=True)

        with col_docs_status:
            st.markdown(f"""
                <div style='color: #E0E0E0;'>
                    <strong>Fornecedores:</strong> {fornecedores_display}<br>
                    <strong>Data Compra (Earliest):</strong> {earliest_data_compra_display}<br>
                    <strong>Data Embarque (Earliest):</strong> {earliest_data_embarque_display}<br>
                </div>
            """, unsafe_allow_html=True)

        with col_actions:
            # Para o card consolidado, podemos ter ações específicas para o grupo
            # Por exemplo, ver detalhes do grupo, desvincular, etc.
            # Por enquanto, deixaremos um popover genérico
            with st.popover("⚙️", help="Opções do Grupo Consolidado", use_container_width=True):
                st.button("Ver Detalhes do Grupo (Em breve) 🔎", key=f"menu_query_group_{unique_id_for_key}")
                # Adicione outras ações específicas para o grupo aqui, se necessário

        col1_empty, col1_docs_status, col3_empty = st.columns([0.08, 0.32, 0.11])
        with col1_docs_status:
            st.markdown(f"""
                        <div style='display: flex; justify-content: space-around; font-size: 0.9em; color: #E0E0E0;'>
                            <span>Pago: <span class="process-card-doc-status">{pago}</span></span>
                            <span>Docs Rev.: <span class="process-card-doc-status">{docs_revisados}</span></span>
                            <span>Conh. Emb.: <span class="process-card-doc-status">{conhecimento_embarque}</span></span>                  
                            <span>Desc. Feita: <span class="process-card-doc-status">{descricao_feita}</span></span>
                            <span>Nota feita: <span class="process-card-doc-status">{nota_feita}</span></span>
                            <span>Conferido: <span class="process-card-doc-status">{conferido}</span></span>
                        </div>
                    """, unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

        # Seção de detalhes dos membros (ainda dentro do card consolidado, mas como um expander)
        st.markdown(f"""
            <details style='color: #E0E0E0; margin-top: 10px;'>
                <summary>Ver Processos Membros (Detalhes)</summary>
                <div style='max-height: 250px; overflow-y: auto; border: 1px solid #444; padding: 10px; border-radius: 5px; background-color: #2A2A2A; margin-top: 10px;'>
        """, unsafe_allow_html=True)
        
        for member in members_data:
            st.markdown(f"""
                <div style='margin-bottom: 8px; padding: 8px; border-bottom: 1px dashed #444;'>
                    - <strong>Processo:</strong> {member.get('Processo_Novo', 'N/A')}<br>
                    &nbsp;&nbsp;<strong>Fornecedor:</strong> {member.get('Fornecedor', 'N/A')}<br>
                    &nbsp;&nbsp;<strong>Status:</strong> {member.get('Status_Geral', 'Sem Status')}<br>
                    &nbsp;&nbsp;<strong>Nº Invoice:</strong> {member.get('N_Invoice', 'N/A')}<br>
                    &nbsp;&nbsp;<strong>Qtd:</strong> {_format_int_display(member.get('Quantidade', 0))} | <strong>Valor (US$):</strong> {_format_usd_display(member.get('Valor_USD', 0.0))}
                </div>
            """, unsafe_allow_html=True)
        
        st.markdown("""
                </div>
            </details>
        """, unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)


def _render_process_card(row_dict: Dict[str, Any], unique_id_for_key: str):
    """Renderiza um único card de processo."""
    
    # OTIMIZAÇÃO: Usa cache de permissões para reduzir cálulos repetitivos
    permissions = _get_cached_user_permissions()
    is_admin = permissions["is_admin"]
    
    # Função auxiliar otimizada para verificar permissão
    def has_permission(screen_name: str) -> bool:
        # Garante que administradores sempre veem o popover
        if is_admin:
            return True
        # Se a permissão está explicitamente no mapa, respeita
        if screen_name in permissions["permission_map"]:
            return permissions["permission_map"][screen_name]
        # Se não está no mapa, verifica se está na lista de telas permitidas
        return screen_name in permissions["user_allowed_screens"]

    # Extrai dados do processo com tratamento de valores padrão
    processo_novo = row_dict.get('Processo_Novo', 'N/A')
    status_geral = row_dict.get('Status_Geral', 'Sem Status')
    modal = row_dict.get('Modal', 'Sem Modal')
    fornecedor = row_dict.get('Fornecedor', 'N/A')
    n_invoice = row_dict.get('N_Invoice', 'N/A')
    quantidade = row_dict.get('Quantidade', 0)
    valor_usd = row_dict.get('Valor_USD', 0.0)
    
    # OTIMIZAÇÃO: Formatação de datas otimizada para reduzir chamadas de função
    data_compra = _format_date_display(row_dict.get('Data_Compra'))
    data_embarque = _format_date_display(row_dict.get('Data_Embarque'))
    eta_recinto = _format_date_display(row_dict.get('ETA_Recinto'))
    previsao_pichau = _format_date_display(row_dict.get('Previsao_Pichau'))
    
    observacao = row_dict.get('Observacao', 'N/A')
    consolidado_flag = row_dict.get('Consolidado', 'Não') 

    # OTIMIZAÇÃO: Formatação de status com função auxiliar
    status_arquivado = row_dict.get('Status_Arquivado', 'Não Arquivado')
    display_status, status_display_color = _format_status_display(status_geral, status_arquivado)

    # OTIMIZAÇÃO: Formatação de checkboxes com função auxiliar
    pago = _format_checkbox_display(row_dict.get('Pago', ''))
    docs_revisados = _format_checkbox_display(row_dict.get('Documentos_Revisados', ''))
    conhecimento_embarque = _format_checkbox_display(row_dict.get('Conhecimento_Embarque', ''))
    descricao_feita = _format_checkbox_display(row_dict.get('Descricao_Feita', ''))
    descricao_enviada = _format_checkbox_display(row_dict.get('Descricao_Enviada', ''))
    nota_feita = _format_checkbox_display(row_dict.get('Nota_feita', ''))
    conferido = _format_checkbox_display(row_dict.get('Conferido', ''))

    modal_icon = '✈️' if modal == 'Aéreo' else ('🚢' if modal == 'Maritimo' else ('📦' if modal == 'Consolidado' else '➖')) 
    
    with st.container():
        st.markdown(f"<div class='process-card-container-inner' style='padding: 5px; margin-bottom: 2px;'>", unsafe_allow_html=True)

        col_main_info, col_dates_status, col_docs_status, col_actions = st.columns([0.15, 0.25, 0.35, 0.05])
        with col_main_info:
            st.markdown(f"<div style='font-size: 2.5em; text-align: center; color: #F8F8F8;'>{modal_icon}</div>", unsafe_allow_html=True)
            st.markdown(f"""
                <div style='color: #E0E0E0; text-align: center;'>
                    <strong>{processo_novo}</strong><br>
                    <small>{fornecedor}</small><br>
                </div>
            """, unsafe_allow_html=True)

        with col_dates_status:
            st.markdown(f"""
                <div style='color: #E0E0E0;'>
                    <span class="process-card-status-text" style="background-color: {status_display_color}; color: {_get_text_color(status_display_color)}; font-size: 1.2em;">{display_status}</span><br>
                    <strong>Qtd:</strong> {quantidade} | <strong>Valor (US$):</strong> {_format_usd_display(valor_usd).replace('US$', '')}<br>
                    <small>Nº Invoice: {n_invoice}</small><br>
                    <strong>Observação:</strong> <span style="color:{'#FF0000' if observacao not in ['N/A', 'None', '', None] else '#E0E0E0'}">{observacao if observacao not in ['N/A', 'None', '', None] else 'Nenhuma'}</span><br>
                </div>
            """, unsafe_allow_html=True)

        with col_docs_status:
            st.markdown(f"""
                <div style='color: #E0E0E0;'>
                    <br><strong>Data Compra:</strong> {data_compra}<br>
                    <strong>Data Emb.:</strong> {data_embarque} |
                    <strong>Prev. Pichau:</strong> {previsao_pichau}
                </div>
            """, unsafe_allow_html=True)

        with col_actions:
            if has_permission("Ações do Processo (Popover)"):
                with st.popover("⚙️", help="Opções do Processo", use_container_width=True):
                    if has_permission("Consulta de Processo"):
                        if st.button("Consultar Processo 🔎", key=f"menu_query_{unique_id_for_key}"):
                            _navigate_from_card_action("query", row_dict.get('id'))
                    if has_permission("Atualizar Dados de Processo"):
                        if st.button("Alterar Status do Processo 🔄", key=f"menu_change_status_{unique_id_for_key}"):
                            _navigate_from_card_action("change_status", row_dict)
                        if st.button("Editar Checklist ✅", key=f"menu_edit_checklist_{unique_id_for_key}"):
                            _navigate_from_card_action("edit_checklist", row_dict)
                    if has_permission("Formulário Processo"):
                        if st.button("Editar Processo ✏️", key=f"menu_edit_{unique_id_for_key}"):
                            _navigate_from_card_action("edit", row_dict)
                        if st.button("Clonar Processo 🗒️", key=f"menu_clone_{unique_id_for_key}"):
                            _navigate_from_card_action("clone", row_dict)
                    if has_permission("Vincular Consolidado"):
                        if consolidado_flag.lower() != 'sim':
                            if st.button("Agrupar Consolidado ➕", key=f"menu_group_consolidated_{unique_id_for_key}"):
                                _navigate_from_card_action("group_consolidated", row_dict)
                    if has_permission("Gerenciamento de Processos em Massa"):
                        if st.button("Arquivar Processo 🗑️", key=f"menu_archive_{unique_id_for_key}"):
                            _navigate_from_card_action("archive", row_dict)

        col1_empty, col1_docs_status, col3_empty = st.columns([0.08, 0.32, 0.11])
        with col1_docs_status:
            st.markdown(f"""
                        <div style='display: flex; justify-content: space-around; font-size: 0.9em; color: #E0E0E0;'>
                            <span>Pago: <span class="process-card-doc-status">{pago}</span></span>
                            <span>Docs Rev.: <span class="process-card-doc-status">{docs_revisados}</span></span>
                            <span>Conh. Emb.: <span class="process-card-doc-status">{conhecimento_embarque}</span></span>                  
                            <span>Desc. Feita: <span class="process-card-doc-status">{descricao_feita}</span></span>
                            <span>Nota feita: <span class="process-card-doc-status">{nota_feita}</span></span>
                            <span>Conferido: <span class="process-card-doc-status">{conferido}</span></span>
                        </div>
                    """, unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)


def _render_payment_card(row_dict: Dict[str, Any], unique_id_for_key: str, di_data=None, frete_internacional_data=None):
    """Renderiza um card de processo na visualização de pagamentos, exibindo os campos batchados de DI e frete internacional."""
    permissions = _get_cached_user_permissions()
    is_admin = permissions["is_admin"]
    def has_permission(screen_name: str) -> bool:
        if is_admin:
            return True
        if screen_name in permissions["permission_map"]:
            return permissions["permission_map"][screen_name]
        return screen_name in permissions["user_allowed_screens"]

    processo_novo = row_dict.get('Processo_Novo', 'N/A')
    fornecedor = row_dict.get('Fornecedor', 'N/A')
    status_geral = row_dict.get('Status_Geral', 'Sem Status')
    status_arquivado = row_dict.get('Status_Arquivado', 'Não Arquivado')
    display_status, status_display_color = _format_status_display(status_geral, status_arquivado)
    modal = row_dict.get('Modal', 'Sem Modal')
    n_invoice = row_dict.get('N_Invoice', 'N/A')
    quantidade = row_dict.get('Quantidade', 0)
    valor_usd = row_dict.get('Valor_USD', 0.0)
    observacao = row_dict.get('Observacao', 'N/A')
    consolidado_flag = row_dict.get('Consolidado', 'Não')
    data_compra = _format_date_display(row_dict.get('Data_Compra'))
    data_embarque = _format_date_display(row_dict.get('Data_Embarque'))
    previsao_pichau = _format_date_display(row_dict.get('Previsao_Pichau'))

    # Dados de pagamento batchados
    # Valores brutos para lógica de cor
    frete_nacional_val = di_data.get('frete_nacional', 0.0) if di_data else 0.0
    armazenagem_val = di_data.get('armazenagem', 0.0) if di_data else 0.0
    honorarios_despachante_val = di_data.get('Honorarios_Despachante', 0.0) if di_data else 0.0
    frete_internacional_val = frete_internacional_data.get('total_aereo_brl', 0.0) if frete_internacional_data else 0.0

    frete_nacional = _format_currency_display(frete_nacional_val)
    armazenagem = _format_currency_display(armazenagem_val)
    honorarios_despachante = _format_currency_display(honorarios_despachante_val)
    di_number = _format_di_number(str(di_data.get('numero_di'))) if di_data else "N/A"
    frete_internacional_display = _format_currency_display(frete_internacional_val)

    # Cores: verde se >0, vermelho se 0
    def get_payment_color(valor):
        try:
            return '#28a745' if float(valor) > 0 else '#dc3545'
        except:
            return '#dc3545'

    cor_frete_int = get_payment_color(frete_internacional_val)
    cor_frete_nac = get_payment_color(frete_nacional_val)
    cor_armazenagem = get_payment_color(armazenagem_val)
    cor_honorarios = get_payment_color(honorarios_despachante_val)

    modal_icon = '✈️' if modal == 'Aéreo' else ('🚢' if modal == 'Maritimo' else ('📦' if modal == 'Consolidado' else '➖'))

    with st.container():
        st.markdown(f"<div class='process-card-container-inner' style='padding: 5px; margin-bottom: 2px;'>", unsafe_allow_html=True)
        col_main_info, col_pagamentos, col_actions = st.columns([0.18, 0.65, 0.07])
        with col_main_info:
            st.markdown(f"<div style='font-size: 2.5em; text-align: center; color: #F8F8F8;'>{modal_icon}</div>", unsafe_allow_html=True)
            st.markdown(f"""
                <div style='color: #E0E0E0; text-align: center;'>
                    <strong>{processo_novo}</strong><br>
                    <small>{fornecedor}</small><br>
                </div>
            """, unsafe_allow_html=True)
        with col_pagamentos:
            st.markdown(f"""
                <div style='color: #E0E0E0; font-size: 1.1em;'>
                    <span class="process-card-status-text" style="background-color: {status_display_color}; color: {_get_text_color(status_display_color)}; font-size: 1.2em;">{display_status}</span><br>
                    <strong>Frete Int.:</strong> <span style='color: {cor_frete_int};'>{frete_internacional_display}</span> &nbsp;|&nbsp; 
                    <strong>Frete Nac.:</strong> <span style='color: {cor_frete_nac};'>{frete_nacional}</span> &nbsp;|&nbsp; 
                    <strong>Armazenagem:</strong> <span style='color: {cor_armazenagem};'>{armazenagem}</span> &nbsp;|&nbsp; 
                    <strong>Honorários Desp.:</strong> <span style='color: {cor_honorarios};'>{honorarios_despachante}</span><br>
                    <strong>Detalhes DI:</strong> {di_number}
                </div>
            """, unsafe_allow_html=True)
        with col_actions:
            if has_permission("Ações do Processo (Popover)"):
                with st.popover("⚙️", help="Opções do Processo"):
                    if has_permission("Consulta de Processo"):
                        if st.button("Consultar Processo 🔎", key=f"menu_query_{unique_id_for_key}"):
                            _navigate_from_card_action("query", row_dict.get('id'))
                    if has_permission("Atualizar Dados de Processo"):
                        if st.button("Alterar Status do Processo 🔄", key=f"menu_change_status_{unique_id_for_key}"):
                            _navigate_from_card_action("change_status", row_dict)
                        if st.button("Editar Checklist ✅", key=f"menu_edit_checklist_{unique_id_for_key}"):
                            _navigate_from_card_action("edit_checklist", row_dict)
                    if has_permission("Formulário Processo"):
                        if st.button("Editar Processo ✏️", key=f"menu_edit_{unique_id_for_key}"):
                            _navigate_from_card_action("edit", row_dict)
                        if st.button("Clonar Processo 🗒️", key=f"menu_clone_{unique_id_for_key}"):
                            _navigate_from_card_action("clone", row_dict)
                    if has_permission("Vincular Consolidado"):
                        if consolidado_flag.lower() != 'sim':
                            if st.button("Agrupar Consolidado ➕", key=f"menu_group_consolidated_{unique_id_for_key}"):
                                _navigate_from_card_action("group_consolidated", row_dict)
                    if has_permission("Gerenciamento de Processos em Massa"):
                        if st.button("Arquivar Processo 🗑️", key=f"menu_archive_{unique_id_for_key}"):
                            _navigate_from_card_action("archive", row_dict)
        st.markdown("</div>", unsafe_allow_html=True)

@st.cache_data(ttl=300) # Cache para os dados de pagamento de um processo
def _get_payment_data_for_process(process_data: Dict[str, Any], last_db_update: datetime) -> Dict[str, Any]:
    """
    Obtém e formata os dados de pagamento para um único processo.
    Cacheada para evitar chamadas repetitivas ao DB para dados de DI/frete.
    """
    process_id = process_data.get('id')
    process_novo = process_data.get('Processo_Novo', 'N/A')

    # Dados da DI
    di_data = db_utils.get_declaracao_by_referencia(process_novo)
    frete_nacional = _format_currency_display(di_data.get('frete_nacional', 0.0)) if di_data else "R$ 0,00"
    armazenagem = _format_currency_display(di_data.get('armazenagem', 0.0)) if di_data else "R$ 0,00"
    honorarios_despachante = _format_currency_display(di_data.get('Honorarios_Despachante', 0.0)) if di_data else "R$ 0,00"
    di_number = _format_di_number(str(di_data.get('numero_di'))) if di_data else "N/A"
    
    # Dados de frete internacional
    frete_internacional_data = db_utils.get_frete_internacional_by_referencia(process_novo)
    frete_internacional_display = _format_currency_display(frete_internacional_data.get('total_aereo_brl', 0.0)) if frete_internacional_data else "R$ 0,00"

    return {
        "Processo": process_novo,
        "Fornecedor": process_data.get('Fornecedor', 'N/A'),
        "Status": process_data.get('Status_Geral', 'Sem Status'),
        "Frete Int.": frete_internacional_display,
        "Frete Nac.": frete_nacional,
        "Armazenagem": armazenagem,
        "Honorários Desp.": honorarios_despachante,
        "Detalhes DI": di_number
    }

@st.cache_data(ttl=300) # Cache para os dados de pagamento da tabela
def _prepare_payment_table_data_cached(
    processes_data: List[Dict[str, Any]],
    last_db_update: datetime,
    max_rows: Optional[int] = None
) -> List[Dict[str, Any]]:
    """
    Prepara os dados para a tabela de pagamentos, processando em lote e usando cache.
    """
    # NOVO: Busca em lote (batch) para DI e Frete Internacional
    table_data = []
    items_to_process = processes_data[:max_rows] if max_rows is not None else processes_data

    # Coleta todas as referências de processo (Processo_Novo)
    referencias = [proc.get('Processo_Novo', 'N/A') for proc in items_to_process]

    # Busca em lote (batch) os dados de DI e Frete Internacional
    # As funções abaixo devem ser implementadas no db_utils
    di_dict = db_utils.get_declaracoes_by_referencias(referencias)  # Dict[str, dict]
    frete_int_dict = db_utils.get_fretes_internacionais_by_referencias(referencias)  # Dict[str, dict]

    for process_data in items_to_process:
        process_id = process_data.get('id')
        process_novo = process_data.get('Processo_Novo', 'N/A')

        # Dados da DI (batch)
        di_data = di_dict.get(process_novo)
        frete_nacional = _format_currency_display(di_data.get('frete_nacional', 0.0)) if di_data else "R$ 0,00"
        armazenagem = _format_currency_display(di_data.get('armazenagem', 0.0)) if di_data else "R$ 0,00"
        honorarios_despachante = _format_currency_display(di_data.get('Honorarios_Despachante', 0.0)) if di_data else "R$ 0,00"
        di_number = _format_di_number(str(di_data.get('numero_di'))) if di_data else "N/A"

        # Dados de frete internacional (batch)
        frete_internacional_data = frete_int_dict.get(process_novo)
        frete_internacional_display = _format_currency_display(frete_internacional_data.get('total_aereo_brl', 0.0)) if frete_internacional_data else "R$ 0,00"

        payment_info = {
            "Processo": process_novo,
            "Fornecedor": process_data.get('Fornecedor', 'N/A'),
            "Status": process_data.get('Status_Geral', 'Sem Status'),
            "Frete Int.": frete_internacional_display,
            "Frete Nac.": frete_nacional,
            "Armazenagem": armazenagem,
            "Honorários Desp.": honorarios_despachante,
            "Detalhes DI": di_number
        }
        table_data.append(payment_info)
    return table_data

def _initialize_table_loading_state():
    """Inicializa o estado de carregamento da tabela."""
    st.session_state.setdefault('table_rows_loaded', TABLE_ROWS_INCREMENT)
    st.session_state.setdefault('total_rows_available', 0)
    st.session_state.setdefault('show_load_more_table_button', True)

def _load_more_table_rows():
    """Carrega mais linhas para a tabela."""
    st.session_state.table_rows_loaded += TABLE_ROWS_INCREMENT
    if st.session_state.table_rows_loaded >= st.session_state.total_rows_available:
        st.session_state.show_load_more_table_button = False
    # st.rerun() # Streamlit fará o rerun automaticamente


def _render_payment_table_with_lazy_loading(sorted_items_in_status: List[Dict[str, Any]], status: str):
    """
    Renderiza a tabela de pagamentos com suporte a lazy loading.
    Carrega apenas as primeiras 50 linhas inicialmente, melhorando o tempo de renderização.
    
    Args:
        sorted_items_in_status: Lista de itens a serem exibidos
        status: Status atual sendo renderizado
    """
    # Inicializa o estado de carregamento se necessário
    _initialize_table_loading_state()
    
    # Atualiza o total de linhas disponíveis
    st.session_state.total_rows_available = len(sorted_items_in_status)
    
    # Define as colunas da tabela de pagamentos
    table_columns = ["Processo", "Fornecedor", "Status", "Frete Int.", "Frete Nac.", 
                    "Armazenagem", "Honorários Desp.", "Detalhes DI"]
    
    # Prepara os dados limitados ao número atual de linhas carregadas
    limited_items = sorted_items_in_status[:st.session_state.table_rows_loaded]
    
    # Separa itens consolidados e não consolidados
    non_consolidated_items = [item for item in limited_items if not item.get('_is_consolidated_group')]
    consolidated_items = [item for item in limited_items if item.get('_is_consolidated_group')]
    
    # Prepara os dados da tabela
    table_data = []
    
    # Processa itens não consolidados com lazy loading
    if non_consolidated_items:
        payment_rows_non_consolidated = _prepare_payment_table_data_cached(
            non_consolidated_items,
            st.session_state.get('last_db_update', datetime.min),
            max_rows=st.session_state.table_rows_loaded
        )
        table_data.extend(payment_rows_non_consolidated)
    
    # Processa grupos consolidados
    for item in consolidated_items:
        if item.get('_is_consolidated_group'):
            group_data = item['group_data']
            principal_id = group_data.get('principal_id', 'N/A')
            principal_process_data = next(
                (m for m in group_data.get('members_data', []) 
                 if str(m.get('id')) == str(principal_id)), None)
            
            # Adiciona cabeçalho do grupo
            group_header_row = {col: "" for col in table_columns}
            group_header_row["Processo"] = f"📦 Grupo: {principal_id}"
            group_header_row["Status"] = (principal_process_data.get('Status_Geral', 'Consolidado') 
                                        if principal_process_data else 'Consolidado')
            group_header_row["Detalhes DI"] = f"Membros: {len(group_data.get('members_data', []))}"
            table_data.append(group_header_row)
            
            # Processa membros do grupo com lazy loading
            member_payment_rows = _prepare_payment_table_data_cached(
                group_data.get('members_data', []),
                st.session_state.get('last_db_update', datetime.min),
                max_rows=st.session_state.table_rows_loaded
            )
            # Indenta os processos membros
            for row in member_payment_rows:
                row["Processo"] = f"  - {row['Processo']}"
            table_data.extend(member_payment_rows)
    
    # Exibe a tabela com os dados preparados
    if table_data:
        df_display = pd.DataFrame(table_data, columns=table_columns)
        st.dataframe(df_display, use_container_width=True, hide_index=True)
        
        # Mostra botão "Carregar Mais" se houver mais dados
        if (st.session_state.table_rows_loaded < st.session_state.total_rows_available and 
            st.session_state.show_load_more_table_button):
            
            col_center = st.columns([1, 2, 1])[1]
            with col_center:
                if st.button(f"📋 Carregar mais {TABLE_ROWS_INCREMENT} linhas " +
                            f"({st.session_state.table_rows_loaded}/{st.session_state.total_rows_available})", 
                            key=f"load_more_table_{status}"):
                    _load_more_table_rows()
                    # st.rerun() # Streamlit fará o rerun automaticamente
        
        # Mostra estatísticas de carregamento
        if st.session_state.table_rows_loaded < st.session_state.total_rows_available:
            st.info(f"📊 Exibindo {st.session_state.table_rows_loaded} de {st.session_state.total_rows_available} processos. " + 
                    f"Use o botão 'Carregar Mais' para ver mais {TABLE_ROWS_INCREMENT} linhas.")
    else:
        st.info(f"Nenhum processo encontrado para o status {status}")


def _clear_payment_cache():
    """Limpa o cache de dados de pagamento quando necessário."""
    # Limpa cache de sessão
    keys_to_remove = [key for key in st.session_state.keys() if key.startswith('payment_data_')]
    for key in keys_to_remove:
        del st.session_state[key]
    
    # Limpa cache do Streamlit
    _get_payment_data_for_process.clear()
    _prepare_payment_table_data_cached.clear()

def show_page():
    """Função principal para rotear entre as páginas do Follow-up e Formulário de Processo."""
    if 'current_page' not in st.session_state:
        st.session_state.current_page = "Follow-up Importação"

    # A callback de reload agora chama a função que gerencia o cache dos filtros
    st.session_state.form_reload_processes_callback = _call_apply_filters_and_update_session_state
    
    if st.session_state.current_page == "Formulário Processo":
        process_form_page.show_process_form_page(
            process_identifier=st.session_state.get('form_process_identifier'),
            reload_processes_callback=st.session_state.form_reload_processes_callback,
            is_cloning=st.session_state.get('form_is_cloning', False)
        )
    elif st.session_state.current_page == "Consulta de Processo":
        process_query_page.show_process_query_page(
            process_identifier=st.session_state.get('query_process_identifier'),
            return_callback=lambda: setattr(st.session_state, 'current_page', "Follow-up Importação")
        )
    elif st.session_state.current_page == "Vincular Consolidado":
        from app_logic.vincular_consolidado_page import show_vincular_consolidado_page
        show_vincular_consolidado_page(process_id=st.session_state.get('process_id_to_vincular'))
    else: # Default para "Follow-up Importação"
        _display_followup_list_page()


def _display_followup_list_page():
    """
    Função principal para exibir a página da lista de Follow-up de Importação.
    
    ATUALIZAÇÃO: Sistema otimizado com virtualização/lazy loading de cards.
    - Carrega TODOS os processos na primeira chamada para garantir ordem correta
    - Implementa carregamento progressivo dos cards (renderiza apenas os visíveis)
    - Remove sistema de paginação para melhor UX
    """
    background_image_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'assets', 'logo_navio_atracado.png')
    set_background_image(background_image_path)

    st.subheader("Follow-up Importação")

    # Inicialização dos estados da sessão (state management)
    st.session_state.setdefault('followup_processes_data_non_consolidated', [])
    st.session_state.setdefault('consolidated_groups_data', [])
    st.session_state.setdefault('selected_process_data', None)
    st.session_state.setdefault('followup_search_terms', {})
    st.session_state.setdefault('followup_all_status_options', [])
    st.session_state.setdefault('followup_raw_status_options_for_multiselect', [])
    st.session_state.setdefault('followup_selected_statuses', ['Todos'])
    st.session_state.setdefault('followup_main_process_search_term', '')
    st.session_state.setdefault('followup_popup_search_terms', {})
    st.session_state.setdefault('show_filter_search_popup', False)
    st.session_state.setdefault('show_delete_confirm_popup', False)
    st.session_state.setdefault('delete_process_id_to_confirm', None)
    st.session_state.setdefault('delete_process_name_to_confirm', None)
    st.session_state.setdefault('form_is_cloning', False)
    st.session_state.setdefault('show_change_status_popup', False) 
    st.session_state.setdefault('process_id_to_change_status', None)
    st.session_state.setdefault('process_name_to_change_status', None)
    st.session_state.setdefault('show_edit_checklist_popup', False)
    st.session_state.setdefault('checklist_process_id_to_edit', None)
    st.session_state.setdefault('checklist_process_name_to_edit', None)
    st.session_state.setdefault('view_mode', 'cards')
    st.session_state.setdefault('all_processes_raw_data_cache', []) # Dados brutos do DB, acumulados via paginação
    st.session_state.setdefault('consolidated_groups_data_raw_cache', []) # Grupos consolidados brutos do DB
    st.session_state.setdefault('last_db_update', datetime.now()) # NOVO: Timestamp da última atualização do DB
    st.session_state.setdefault('sorted_all_expander_keys', []) # Cache para a estrutura final dos expanders
    st.session_state.setdefault('show_payment_view', False) # NOVO: Estado para alternar a visualização de pagamentos
    
    # --- Configuração do Sistema de Virtualização ---
    # Controla quantos cards são renderizados por vez para melhorar performance
    st.session_state.setdefault('cards_per_chunk', INITIAL_CARDS_PER_CHUNK)  # Número otimizado: 15 cards por vez (vs 20 original)
    # Inicializa loaded_cards_per_status para todos os status presentes, se ainda não inicializado corretamente
    if not st.session_state.get('loaded_cards_per_status') or set(st.session_state.get('loaded_cards_per_status', {}).keys()) != set([item['status'] for item in st.session_state.get('sorted_all_expander_keys', [])]):
        st.session_state.loaded_cards_per_status = {item['status']: INITIAL_CARDS_PER_CHUNK for item in st.session_state.get('sorted_all_expander_keys', [])}
        st.session_state.show_load_more_buttons = {item['status']: True for item in st.session_state.get('sorted_all_expander_keys', [])}
    # --- Configuração do Sistema de Lazy Loading para Tabelas ---
    st.session_state.setdefault('table_rows_loaded', TABLE_ROWS_INCREMENT)
    st.session_state.setdefault('total_rows_available', 0)
    st.session_state.setdefault('show_load_more_table_button', True)

    # --- Etapa 1: Carregamento Inicial de Dados (ocorre apenas quando necessário) ---
    # Sempre carrega TODOS os processos para garantir ordem correta e melhor UX
    if not st.session_state.all_processes_raw_data_cache or st.session_state.get('_invalidate_filter_cache', False):
        _fetch_initial_processes()
        st.session_state._invalidate_filter_cache = False # Reseta a flag após a busca inicial

    # --- Etapa 2: Aplicação de Filtros e Preparação da UI (sempre que um rerun ocorre) ---
    # Estes passos aplicam os filtros aos dados JÁ CARREGADOS no cache e preparam os expanders.
    _call_apply_filters_and_update_session_state() 

    # Exibe popups de ações (eles sobrepõem o conteúdo principal se estiverem ativos)
    _display_filter_search_popup()
    _display_delete_confirm_popup()
    _display_change_status_popup() 
    _display_edit_checklist_popup() 

    # Se qualquer popup estiver visível, o restante da UI principal não é renderizado
    if st.session_state.get('show_filter_search_popup', False) or \
       st.session_state.get('show_delete_confirm_popup', False) or \
       st.session_state.get('show_change_status_popup', False) or \
       st.session_state.get('show_edit_checklist_popup', False): 
        return

    st.markdown("---")
    
    # --- Controles de Filtro e Visualização da UI Principal ---
    col_main_filters_1, col_main_filters_2, col_view_toggle = st.columns([0.45, 0.45, 0.1])
    with col_main_filters_1:
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
            key="main_followup_status_multiselect",
            on_change=_on_status_multiselect_change
        )

    with col_main_filters_2:
        st.text_input(
            "Pesquisar Processo:", 
            value=st.session_state.get('followup_main_process_search_term', ''),
            key="main_followup_search_processo_novo",
            on_change=_on_process_search_change 
        )
    with col_view_toggle:
        st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
        if st.button("🔁", help="Clique para alterar a visualização", key="toggle_view_mode"):
            _toggle_view_mode()
            
    # Popover de "Mais Opções" condicional
    # Ele será visível apenas se o usuário tiver permissão para a nova tela "Mais Opções (Popover)"
    user_allowed_screens = st.session_state.get('user_info', {}).get('allowed_screens', [])
    is_admin = st.session_state.get('user_info', {}).get('is_admin', False)

    if is_admin or "Mais Opções (Popover)" in user_allowed_screens:
        with st.popover("Mais Opções"):
            if is_admin or "Formulário Processo" in user_allowed_screens:
                if st.button("Adicionar Novo Processo +", key="add_new_process_button"):
                    _open_edit_process_popup(None)
            
            # O botão "Mais Filtros" é sempre visível, pois a consulta é básica
            if st.button("Mais Filtros ⌨", key="open_filter_search_popup_button"):
                _open_filter_search_popup()
            
            # NOVO BOTÃO: Alterar Visualização para Pagamentos
            payment_view_button_label = "Alterar Visualização: Dados Gerais 📊" if st.session_state.get('show_payment_view', False) else "Alterar Visualização: Pagamentos 💵"
            if st.button(payment_view_button_label, key="toggle_payment_view_button"):
                # Define uma nova flag no session_state para controlar o modo de visualização de pagamentos
                st.session_state.show_payment_view = not st.session_state.get('show_payment_view', False)
                st.rerun()

            # --- Configurações de Performance (visíveis apenas para administradores ou usuários com permissão específica, se desejar) ---
            if is_admin: # Apenas admins podem ajustar configs de performance
                st.markdown("**⚙️ Configurações de Performance:**")
                
                # Controle para ajustar quantos cards carregar por vez
                new_cards_per_chunk = st.selectbox(
                    "Cards por carregamento:",
                    options=[10, 15, 20, 30, 50, 100],
                    index=[10, 15, 20, 30, 50, 100].index(st.session_state.get('cards_per_chunk', 20)),
                    help="Quantidade de cards carregados por vez. Valores menores melhoram a velocidade inicial.",
                    key="cards_per_chunk_selector"
                )
                
                # Se mudou a configuração, atualiza e reseta o estado de carregamento
                if new_cards_per_chunk != st.session_state.get('cards_per_chunk', 20):
                    st.session_state.cards_per_chunk = new_cards_per_chunk
                    _reset_cards_loading_state()
                    # Removido st.rerun() - não necessário
                
                # Botão para carregar todos os cards de uma vez
                if st.button("🚀 Carregar Todos os Cards", help="Carrega todos os cards de todos os status de uma vez"):
                    # Define um número muito alto para todos os status
                    for status in st.session_state.loaded_cards_per_status.keys():
                        st.session_state.loaded_cards_per_status[status] = 9999
                    # Removido st.rerun() - não necessário
            
            # Botões de exportação (visíveis apenas para usuários com permissão ou admins)
            if is_admin or "Exportar Excel" in user_allowed_screens: # Exemplo: uma permissão "Exportar Excel"
                if st.session_state.followup_processes_data_non_consolidated:
                    df_to_export_non_consolidated = pd.DataFrame(st.session_state.followup_processes_data_non_consolidated)
                    excel_data_non_consolidated = _export_processes_to_excel(df_to_export_non_consolidated)
                    st.download_button(
                        label="Exportar Excel (Não Consolidados) 📊",
                        data=excel_data_non_consolidated,
                        file_name="processos_importacao_nao_consolidados.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        key="export_excel_button_non_consolidado"
                    )
                
                all_consolidated_members_for_export = []
                for group in st.session_state.consolidated_groups_data:
                    all_consolidated_members_for_export.extend(group['members_data'])
                if all_consolidated_members_for_export:
                    df_to_export_consolidated = pd.DataFrame(all_consolidated_members_for_export)
                    excel_data_consolidated = _export_processes_to_excel(df_to_export_consolidated)
                    st.download_button(
                        label="Exportar Excel (Consolidados) 📊",
                        data=excel_data_consolidated,
                        file_name="processos_importacao_consolidados.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        key="export_excel_button_consolidado"
                    )

    st.markdown("---")
    st.markdown("#### Processos de Importação")

    # Estilos CSS para os cards e botões com otimizações de performance avançadas.
    st.markdown("""
        <style>
        /* CSS OTIMIZADO PARA PERFORMANCE - Baseado em OTIMIZACOES_PERFORMANCE.md */
        .process-card-container {
            background-color: #333;
            border-radius: 10px;
            padding: 0;
            margin-bottom: 10px;
            box-shadow: 2px 2px 8px rgba(0, 0, 0, 0.3);
            border: 1px solid #444;
            /* OTIMIZAÇÕES DE GPU E PERFORMANCE */
            contain: layout style paint;      /* Isolamento de layout para melhor performance */
            will-change: transform;           /* Otimização de compositing */
            transform: translateZ(0);         /* Força layer de GPU */
            backface-visibility: hidden;      /* Evita renderização traseira */
            transition: transform 0.2s ease;  /* Transições GPU-aceleradas */
        }
        .process-card-container:hover {
            transform: translateY(-5px) translateZ(0);  /* Mantém a GPU layer */
            box-shadow: 3px 3px 12px rgba(0, 0, 0, 0.5);
        }
        .process-card-container-inner { 
            padding: 5px; 
            margin-bottom: 2px;
            contain: layout;  /* Isolamento adicional para cards internos */
        } 
        .process-card-row { 
            display: flex; 
            justify-content: space-between; 
            align-items: center; 
            margin-bottom: 10px; 
        }
        .process-card-col { 
            flex: 1; 
            padding: 0 5px; 
            color: #E0E0E0; 
        }
        .process-card-col strong { 
            color: #F8F8F8; 
        }
        .process-card-status-text { 
            font-weight: bold; 
            padding: 2px 8px; 
            border-radius: 5px; 
            display: inline-block; 
        }
        .process-card-doc-status { 
            font-size: 1.1em; 
        }
        
        /* Estilos para os botões "Carregar Mais" com animações GPU-aceleradas */
        .load-more-button {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            border-radius: 25px;
            padding: 12px 24px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            box-shadow: 0 4px 15px rgba(102, 126, 234, 0.3);
            text-align: center;
            width: 100%;
            /* OTIMIZAÇÕES DE PERFORMANCE */
            will-change: transform, box-shadow;
            transform: translateZ(0);
            transition: all 0.3s ease;
        }
        .load-more-button:hover {
            transform: translateY(-2px) translateZ(0);
            box-shadow: 0 6px 20px rgba(102, 126, 234, 0.4);
            background: linear-gradient(135deg, #764ba2 0%, #667eea 100%);
        }
        .load-more-button:active {
            transform: translateY(0px) translateZ(0);
        }
        
        /* Indicador de loading otimizado */
        .loading-indicator {
            display: inline-block;
            width: 20px;
            height: 20px;
            border: 3px solid #f3f3f3;
            border-top: 3px solid #667eea;
            border-radius: 50%;
            animation: spin 1s linear infinite;
            margin-right: 10px;
            will-change: transform;  /* Otimização para animação */
        }
        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }
        
        /* Otimizações para botões do popover */
        div[data-testid^="stVerticalBlock"] > div > div > div > div > .stButton > button {
            font-size: 1.5em; 
            padding: 0.2em 0.5em; 
            border-radius: 50%; 
            width: 40px; 
            height: 40px;
            display: flex; 
            justify-content: center; 
            align-items: center; 
            background-color: #555;
            border: 1px solid #777; 
            color: #F8F8F8;
            /* OTIMIZAÇÕES DE PERFORMANCE */
            will-change: transform, background-color;
            transform: translateZ(0);
            transition: all 0.2s ease;
        }
        div[data-testid^="stVerticalBlock"] > div > div > div > div > .stButton > button:hover {
            background-color: #777; 
            transform: scale(1.1) translateZ(0);
        }
        
        /* Evita layout shifts nos cards */
        .stExpander {
            contain: layout;
        }
        </style>
    """, unsafe_allow_html=True)

    # Renderização dos expanders com virtualização de cards
    if not st.session_state.sorted_all_expander_keys:
        st.info("Nenhum processo encontrado com os filtros aplicados.")
        return

    # --- Renderização dos expanders com sistema de lazy loading ---
    for item in st.session_state.sorted_all_expander_keys:
        status = item['status']
        processes_and_groups_in_status = item['processes_and_groups']

        if not processes_and_groups_in_status:
            continue

        status_display_name = "Arquivados" if status == 'Arquivados' else status

        with st.expander(f"**{status_display_name} ({len(processes_and_groups_in_status)})**", expanded=True):
            sorted_items_in_status = processes_and_groups_in_status

            if st.session_state.view_mode == 'cards':
                cards_loaded_for_status = st.session_state.loaded_cards_per_status.get(status, INITIAL_CARDS_PER_CHUNK)
                total_cards_in_status = len(sorted_items_in_status)
                cards_to_show = sorted_items_in_status[:cards_loaded_for_status]

                # --- Busca batch de pagamentos para os cards deste status ---
                referencias = [proc.get('Processo_Novo', 'N/A') for proc in cards_to_show if not proc.get('_is_consolidated_group')]
                di_dict = db_utils.get_declaracoes_by_referencias(referencias) if referencias else {}
                frete_int_dict = db_utils.get_fretes_internacionais_by_referencias(referencias) if referencias else {}

                for item in cards_to_show:
                    if item.get('_is_consolidated_group'):
                        group_data = item['group_data']
                        unique_group_id = f"consolidated_group_card_{group_data.get('principal_id', uuid.uuid4())}"
                        _render_consolidated_group_card(group_data, unique_group_id)
                    else:
                        row_dict = item
                        unique_id_for_key = f"non_consolidated_card_{row_dict.get('id', uuid.uuid4())}"
                        if st.session_state.get('show_payment_view', False):
                            process_novo = row_dict.get('Processo_Novo', 'N/A')
                            di_data = di_dict.get(process_novo)
                            frete_internacional_data = frete_int_dict.get(process_novo)
                            _render_payment_card(row_dict, unique_id_for_key, di_data=di_data, frete_internacional_data=frete_internacional_data)
                        else:
                            _render_process_card(row_dict, unique_id_for_key)
                    st.markdown("---") # Separador entre cards

                if cards_loaded_for_status < total_cards_in_status:
                    remaining_cards = total_cards_in_status - cards_loaded_for_status
                    cards_to_load_next = min(st.session_state.cards_per_chunk, remaining_cards)
                    col_center_button = st.columns([1, 2, 1])[1]
                    with col_center_button:
                        if st.button(
                            f"📋 Carregar mais {cards_to_load_next} processos ({remaining_cards} restantes)",
                            key=f"load_more_cards_{status}",
                            use_container_width=True
                        ):
                            _load_more_cards_for_status(status)

                if total_cards_in_status > 0:
                    st.caption(f"Exibindo {len(cards_to_show)} de {total_cards_in_status} processos")

            else: # Modo de visualização em tabela
                # A lógica para a tabela foi movida para uma função separada para melhor organização
                # e para garantir que a `table_data` seja preenchida corretamente antes de ser exibida.
                # A `table_data` não será mais preenchida no loop principal, mas sim dentro da função
                # `_render_table_view`.
                _render_table_view(sorted_items_in_status, status)


    # --- Botão flutuante de voltar ao topo (visual clássico, canto inferior direito) + função global para simulação ---
    st.markdown("""
        <style>
        .float-voltar-topo-btn {
            position: fixed;
            bottom: 32px;
            right: 32px;
            z-index: 9999;
            background: #0787FF;
            color: #fff;
            border: none;
            border-radius: 50%;
            width: 56px;
            height: 56px;
            box-shadow: 0 4px 16px rgba(7,135,255,0.25), 0 1.5px 4px rgba(0,0,0,0.10);
            font-size: 2em;
            font-weight: bold;
            display: flex;
            align-items: center;
            justify-content: center;
            cursor: pointer;
            transition: background 0.2s, color 0.2s, box-shadow 0.2s, transform 0.2s;
            outline: none;
            opacity: 0.92;
        }
        .float-voltar-topo-btn:hover {
            background: #005fa3;
            color: #fff;
            box-shadow: 0 6px 24px rgba(7,135,255,0.35), 0 2px 8px rgba(0,0,0,0.15);
            transform: translateY(-2px) scale(1.08);
            opacity: 1.0;
        }
        </style>
        <button id="float-voltar-topo-btn" class="float-voltar-topo-btn" title="Voltar ao topo">⬆️</button>
        <script>
        // Função para encontrar o elemento rolável principal do Streamlit
        function findScrollableContainer() {
            let element = document.querySelector('.main [data-testid="stVerticalBlock"]');
            if (element) return element;
            element = document.querySelector('.stApp');
            if (element) return element;
            let bodyChildren = document.body.children;
            for (let i = 0; i < bodyChildren.length; i++) {
                let computedStyle = window.getComputedStyle(bodyChildren[i]);
                if (computedStyle.overflowY === 'auto' || computedStyle.overflowY === 'scroll') {
                    return bodyChildren[i];
                }
            }
            return window;
        }
        function scrollToTopRobust() {
            try {
                let scrollableElement = findScrollableContainer();
                if (scrollableElement) {
                    if (scrollableElement.scrollTo) {
                        scrollableElement.scrollTo({top: 0, behavior: 'smooth'});
                    } else {
                        window.scrollTo({top: 0, behavior: 'smooth'});
                    }
                }
            } catch(e) {console.error("Erro ao tentar rolar para o topo:", e);}
        }
        // Função global para simular clique no botão flutuante
        window.simulateScrollToTopClick = function() {
            var btn = document.getElementById('float-voltar-topo-btn');
            if (btn) { btn.click(); }
            else { scrollToTopRobust(); }
        }
        function setupVoltarTopoBtn() {
            var btn = document.getElementById('float-voltar-topo-btn');
            if (btn) {
                btn.onclick = scrollToTopRobust;
                let scrollableElement = findScrollableContainer();
                if (scrollableElement) {
                    scrollableElement.addEventListener('scroll', function() {
                        if (scrollableElement.scrollTop > 200) {
                            btn.style.display = 'flex';
                        } else {
                            btn.style.display = 'none';
                        }
                    });
                    if (scrollableElement.scrollTop > 200) {
                        btn.style.display = 'flex';
                    } else {
                        btn.style.display = 'none';
                    }
                } else {
                    window.addEventListener('scroll', function() {
                        if (window.scrollY > 200) {
                            btn.style.display = 'flex';
                        } else {
                            btn.style.display = 'none';
                        }
                    });
                    if (window.scrollY > 200) {
                        btn.style.display = 'flex';
                    } else {
                        btn.style.display = 'none';
                    }
                }
            }
        }
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', setupVoltarTopoBtn);
        } else {
            setupVoltarTopoBtn();
        }
        </script>
    """, unsafe_allow_html=True)

    # Exemplo de botão Streamlit que dispara o scroll para o topo via JS
    if st.button("Ir para o Topo", key="btn_ir_para_topo"):
        st.components.v1.html("<script>window.simulateScrollToTopClick && window.simulateScrollToTopClick();</script>", height=0, width=0)

def _render_table_view(sorted_items_in_status: List[Dict[str, Any]], status: str):
    """
    Renderiza a visualização de processos em formato de tabela.
    Inclui lógica para exibir grupos consolidados e seus membros.
    """
    table_data = []
    table_columns = ["Processo", "Status", "Modal", "Fornecedor", "Nº Invoice", "Qtd", "Valor (US$)", "Data Compra", "Data Embarque", "Prev. Pichau", "Observação", "Ações"]

    # Atualiza o total de linhas disponíveis para o lazy loading da tabela
    st.session_state.total_rows_available = len(sorted_items_in_status)
    
    # Prepara os dados limitados ao número atual de linhas carregadas para a tabela
    limited_items_for_table = sorted_items_in_status[:st.session_state.table_rows_loaded]

    for item in limited_items_for_table: # Itera sobre os itens limitados para a tabela
        if item.get('_is_consolidated_group'):
            group_data = item['group_data']
            principal_id = group_data.get('principal_id', 'N/A')
            principal_process_data = next((m for m in group_data.get('members_data', []) if str(m.get('id')) == str(principal_id)), None)
            
            # Linha para o grupo consolidado
            table_data.append({
                "Processo": f"📦 Grupo: {principal_id}",
                "Status": principal_process_data.get('Status_Geral', 'Consolidado') if principal_process_data else 'Consolidado',
                "Modal": principal_process_data.get('Modal', 'Consolidado') if principal_process_data else 'Consolidado',
                "Fornecedor": "",
                "Nº Invoice": "",
                "Qtd": "",
                "Valor (US$)": "",
                "Data Compra": "",
                "Data Embarque": "",
                "Prev. Pichau": _format_date_display(principal_process_data.get('Previsao_Pichau')) if principal_process_data else '',
                "Observação": f"Membros: {len(group_data.get('members_data', []))}",
                "Ações": "" # Ações para o grupo consolidado podem ser adicionadas aqui, se necessário
            })
            # Linhas para os membros do grupo consolidado
            for member_row_dict in group_data.get('members_data', []):
                table_data.append({
                    "Processo": f"  - {member_row_dict.get('Processo_Novo', 'N/A')}", # Indentação para membros
                    "Status": member_row_dict.get('Status_Geral', 'Sem Status'),
                    "Modal": member_row_dict.get('Modal', 'Sem Modal'),
                    "Fornecedor": member_row_dict.get('Fornecedor', 'N/A'),
                    "Nº Invoice": member_row_dict.get('N_Invoice', 'N/A'),
                    "Qtd": _format_int_display(member_row_dict.get('Quantidade', 0)),
                    "Valor (US$)": _format_usd_display(member_row_dict.get('Valor_USD', 0.0)),
                    "Data Compra": _format_date_display(member_row_dict.get('Data_Compra')),
                    "Data Embarque": _format_date_display(member_row_dict.get('Data_Embarque')),
                    "Prev. Pichau": _format_date_display(member_row_dict.get('Previsao_Pichau')),
                    "Observação": member_row_dict.get('Observacao', ''),
                    "Ações": "Opções..."
                })
        else:
            # Linha para processo não consolidado
            row_dict = item
            table_data.append({
                "Processo": row_dict.get('Processo_Novo', 'N/A'),
                "Status": row_dict.get('Status_Geral', 'Sem Status'),
                "Modal": row_dict.get('Modal', 'Sem Modal'),
                "Fornecedor": row_dict.get('Fornecedor', 'N/A'),
                "Nº Invoice": row_dict.get('N_Invoice', 'N/A'),
                "Qtd": _format_int_display(row_dict.get('Quantidade', 0)),
                "Valor (US$)": _format_usd_display(row_dict.get('Valor_USD', 0.0)),
                "Data Compra": _format_date_display(row_dict.get('Data_Compra')),
                "Data Embarque": _format_date_display(row_dict.get('Data_Embarque')),
                "Prev. Pichau": _format_date_display(row_dict.get('Previsao_Pichau')),
                "Observação": row_dict.get('Observacao', ''),
                "Ações": "Opções..."
            })
    
    if table_data:
        df_display = pd.DataFrame(table_data, columns=table_columns)
        st.dataframe(df_display, use_container_width=True, hide_index=True)
        
        # Implementação de lazy loading para a tabela
        if st.session_state.table_rows_loaded < st.session_state.total_rows_available:
            remaining_rows = st.session_state.total_rows_available - st.session_state.table_rows_loaded
            rows_to_load_next = min(TABLE_ROWS_INCREMENT, remaining_rows)
            col_center_button = st.columns([1, 2, 1])[1]
            with col_center_button:
                if st.button(f"📋 Carregar mais {rows_to_load_next} linhas ({remaining_rows} restantes)", key=f"load_more_table_{status}", use_container_width=True):
                    _load_more_table_rows()
                    st.rerun() # Força o rerun para exibir as novas linhas
        
        if st.session_state.total_rows_available > 0:
            st.caption(f"Exibindo {len(table_data)} de {st.session_state.total_rows_available} processos")
    else:
        st.info(f"Nenhum processo encontrado para o status {status} na visualização de tabela.")
