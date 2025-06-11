import streamlit as st
import pandas as pd
from datetime import datetime
import logging
import os
import sys
import re
import tempfile
from typing import Optional, Any, Dict, List, Union

import followup_db_manager as db_manager

# Ajuste no caminho para garantir que db_utils.py e ncm_list_page.py sejam encontrados
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

try:
    import db_utils
    # Verificar se as funções essenciais existem no db_utils real, se não, usar o mock
    if not hasattr(db_utils, 'get_declaracao_by_id') or \
       not hasattr(db_utils, 'get_declaracao_by_referencia') or \
       not hasattr(db_utils, 'get_ncm_item_by_ncm_code') or \
       not hasattr(db_utils, 'selecionar_todos_ncm_itens'):
        raise ImportError("db_utils real não contém todas as funções esperadas.")
except ImportError:
    class MockDbUtils:
        def get_db_path(self, db_name: str) -> str:
            _base_path = os.path.dirname(os.path.abspath(__file__))
            _app_root_path = os.path.dirname(_base_path) if os.path.basename(_base_path) == 'app_logic' else _base_path
            _DEFAULT_DB_FOLDER = "data"
            return os.path.join(_app_root_path, _DEFAULT_DB_FOLDER, f"{db_name}.db")
        
        def get_declaracao_by_id(self, di_id: int) -> Optional[dict]:
            if di_id == 999: return {'numero_di': '9988776654', 'id': 999}
            return None 
        
        def get_declaracao_by_referencia(self, referencia: str) -> Optional[dict]:
            if referencia == "MOCK-DI-123": return {'numero_di': '9988776654', 'id': 999}
            return None

        def get_ncm_item_by_ncm_code(self, ncm_code: str) -> Optional[dict]:
            # Mock para NCMs conhecidos
            if ncm_code == "85171231":
                return {
                    'ncm_code': '85171231', 'descricao_item': 'Telefones celulares',
                    'ii_aliquota': 16.0, 'ipi_aliquota': 5.0, 'pis_aliquota': 1.65,
                    'cofins_aliquota': 7.6, 'icms_aliquota': 18.0
                }
            return None

        def selecionar_todos_ncm_itens(self) -> List[Dict[str, Any]]:
            return [
                {'ID': 1, 'ncm_code': '85171231', 'descricao_item': 'Telefones celulares', 'ii_aliquota': 16.0, 'ipi_aliquota': 5.0, 'pis_aliquota': 1.65, 'cofins_aliquota': 7.6, 'icms_aliquota': 18.0},
                {'ID': 2, 'ncm_code': '84713012', 'descricao_item': 'Notebooks', 'ii_aliquota': 10.0, 'ipi_aliquota': 0.0, 'pis_aliquota': 1.65, 'cofins_aliquota': 7.6, 'icms_aliquota': 18.0},
            ]

    # Ensure MockDbUtils is defined before assigning to db_utils
    db_utils = MockDbUtils()
    logging.warning("Módulo 'db_utils' não encontrado ou incompleto. Usando MockDbUtils.")
except Exception as e:
    # Fallback to MockDbUtils if any error occurs during real db_utils import
    db_utils = MockDbUtils() 
    logging.error(f"Erro ao importar ou inicializar 'db_utils': {e}. Usando MockDbUtils.")

# Importar pdf_analyzer_page.py e ncm_list_page para reuso de funções
try:
    from app_logic import pdf_analyzer_page
    import pdfplumber # Import pdfplumber here as it's used in this module directly
except ImportError:
    logging.warning("Módulo 'pdf_analyzer_page' ou 'pdfplumber' não encontrado. Funções de análise de PDF não estarão disponíveis.")
    pdf_analyzer_page = None # Define como None se não puder ser importado

try:
    from app_logic import ncm_list_page
except ImportError:
    logging.warning("Módulo 'ncm_list_page' não encontrado. Funções NCM não estarão disponíveis.")
    ncm_list_page = None # Define como None se não puder ser importado


# Configura o logger
logger = logging.getLogger(__name__)

# --- Funções Auxiliares para Formatação ---
def _format_di_number(di_number: Optional[str]) -> str:
    """Formata o número da DI para o padrão **/*******-*."""
    if di_number and isinstance(di_number, str) and len(di_number) == 10:
        return f"{di_number[0:2]}/{di_number[2:9]}-{di_number[9]}"
    return di_number if di_number is not None else ""

def _get_di_number_from_id(di_id: Optional[int]) -> str:
    """Obtém o número da DI a partir do seu ID no banco de dados de XML DI."""
    if di_id is None:
        return "N/A"
    try:
        di_data = db_utils.get_declaracao_by_id(di_id)
        if di_data:
            return _format_di_number(str(di_data.get('numero_di')))
    except Exception as e:
        logger.error(f"Erro ao buscar DI por ID {di_id}: {e}")
    return "DI Não Encontrada"

def _display_message_box(message: str, type: str = "info"):
    """Exibe uma caixa de mensagem customizada (substitui alert())."""
    if type == "info":
        st.info(message)
    elif type == "success":
        st.success(message)
    elif type == "warning":
        st.warning(message)
    elif type == "error":
        st.error(message)

# --- Funções de Cálculo ---
def get_ncm_taxes(ncm_code: str) -> Dict[str, float]:
    """Busca as alíquotas de impostos para um dado NCM."""
    ncm_data_raw = db_utils.get_ncm_item_by_ncm_code(ncm_code)
    # Convert sqlite3.Row object to dictionary if it's not None
    ncm_data = dict(ncm_data_raw) if ncm_data_raw else None

    if ncm_data:
        return {
            'ii_aliquota': ncm_data.get('ii_aliquota', 0.0),
            'ipi_aliquota': ncm_data.get('ipi_aliquota', 0.0),
            'pis_aliquota': ncm_data.get('pis_aliquota', 0.0),
            'cofins_aliquota': ncm_data.get('cofins_aliquota', 0.0),
            'icms_aliquota': ncm_data.get('icms_aliquota', 0.0) # ICMS pode ser digitável ou buscado
        }
    return {'ii_aliquota': 0.0, 'ipi_aliquota': 0.0, 'pis_aliquota': 0.0, 'cofins_aliquota': 0.0, 'icms_aliquota': 0.0}

def calculate_item_taxes_and_values(item: Dict[str, Any], dolar_brl: float, total_invoice_value_usd: float, total_invoice_weight_kg: float, estimativa_frete_usd: float, estimativa_seguro_brl: float) -> Dict[str, Any]:
    """
    Calcula o VLMD, impostos e rateios para um item individual.
    Retorna o item com os campos de impostos atualizados e valores rateados.
    """
    item_qty = float(item.get('Quantidade', 0))
    item_unit_value_usd = float(item.get('Valor Unitário', 0))
    item_unit_weight_kg = float(item.get('Peso Unitário', 0))
    item_value_usd = item_qty * item_unit_value_usd
    item_weight_kg = item_qty * item_unit_weight_kg

    # Para evitar divisão por zero
    # Use max(1, ...) para garantir que o divisor nunca seja zero e evitar erros
    value_ratio = item_value_usd / max(1, total_invoice_value_usd)
    weight_ratio = item_weight_kg / max(1, total_invoice_weight_kg)

    # Rateio de frete e seguro
    frete_rateado_usd = estimativa_frete_usd * value_ratio
    seguro_rateado_brl = estimativa_seguro_brl * weight_ratio

    # NCM e impostos
    ncm_code = str(item.get('NCM', ''))
    ncm_taxes = get_ncm_taxes(ncm_code)

    # VLMD_Item (Valor da Mercadoria no Local de Desembaraço)
    # Considera o valor em USD, frete e seguro rateados convertidos para BRL
    vlmd_item = (item_unit_value_usd * item_qty * dolar_brl) + (frete_rateado_usd * dolar_brl) + seguro_rateado_brl
    
    # Cálculos de impostos
    item['Estimativa_II_BR'] = vlmd_item * (ncm_taxes['ii_aliquota'] / 100)
    item['Estimativa_IPI_BR'] = (vlmd_item + item['Estimativa_II_BR']) * (ncm_taxes['ipi_aliquota'] / 100)
    item['Estimativa_PIS_BR'] = vlmd_item * (ncm_taxes['pis_aliquota'] / 100)
    item['Estimativa_COFINS_BR'] = vlmd_item * (ncm_taxes['cofins_aliquota'] / 100)
    
    # ICMS é digitável, então, se já existir no item, mantém. Caso contrário, usa a alíquota do NCM.
    # Pode ser sobrescrito pelo usuário.
    # IMPORTANT: The ICMS percentage from NCM is used for per-item calculation.
    # The global ICMS field on "Valores e Estimativas" is a manual override for the total, not a percentage override for items.
    item['Estimativa_ICMS_BR'] = (vlmd_item * (ncm_taxes['icms_aliquota'] / 100))

    item['VLMD_Item'] = vlmd_item # Adicionar para referência
    item['Frete_Rateado_USD'] = frete_rateado_usd
    item['Seguro_Rateado_BRL'] = seguro_rateado_brl

    return item

# --- Lógica para Salvar Processo ---
def _save_process_action(process_id: Optional[int], edited_data: dict, is_new_process: bool):
    """Lógica para salvar ou atualizar um processo."""
    db_col_names_full = db_manager.obter_nomes_colunas_db()
    
    data_to_save_dict = {col: None for col in db_col_names_full if col != 'id'}

    for col_name, value in edited_data.items():
        if col_name in data_to_save_dict:
            if isinstance(value, datetime):
                data_to_save_dict[col_name] = value.strftime("%Y-%m-%d")
            elif isinstance(value, str) and value.strip() == '':
                data_to_save_dict[col_name] = None
            elif isinstance(value, (float, int)) and pd.isna(value):
                data_to_save_dict[col_name] = None
            else:
                data_to_save_dict[col_name] = value
        else:
            logger.warning(f"Campo '{col_name}' do formulário não corresponde a uma coluna no DB. Ignorado.")

    if 'Status_Arquivado' in db_col_names_full:
        if is_new_process:
            data_to_save_dict['Status_Arquivado'] = 'Não Arquivado'
        else:
            original_process_data = db_manager.obter_processo_por_id(process_id if process_id is not None else -1)
            if original_process_data:
                original_status_arquivado = dict(original_process_data).get('Status_Arquivado')
                data_to_save_dict['Status_Arquivado'] = original_status_arquivado
            else:
                logger.warning(f"Processo ID {process_id} não encontrado ao tentar obter Status_Arquivado original para salvar.")
                data_to_save_dict['Status_Arquivado'] = 'Não Arquivado'
    
    # Tratamento para campo 'Caminho_da_pasta'
    if 'Caminho_da_pasta' in db_col_names_full:
        data_to_save_dict['Caminho_da_pasta'] = edited_data.get('Caminho_da_pasta')

    if 'DI_ID_Vinculada' in db_col_names_full:
        if 'DI_ID_Vinculada' in edited_data and edited_data['DI_ID_Vinculada'] is not None:
            data_to_save_dict['DI_ID_Vinculada'] = edited_data['DI_ID_Vinculada']
        elif not is_new_process:
            original_process_data = db_manager.obter_processo_por_id(process_id if process_id is not None else -1)
            if original_process_data:
                data_to_save_dict['DI_ID_Vinculada'] = dict(original_process_data).get('DI_ID_Vinculada')
            else:
                data_to_save_dict['DI_ID_Vinculada'] = None
        else:
            data_to_save_dict['DI_ID_Vinculada'] = None

    user_info = st.session_state.get('user_info', {'username': 'Desconhecido'})
    data_to_save_dict['Ultima_Alteracao_Por'] = user_info.get('username')
    data_to_save_dict['Ultima_Alteracao_Em'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Adicionar Estimativa_Impostos_Total ao data_to_save_dict
    if 'Estimativa_Impostos_Total' in edited_data and 'Estimativa_Impostos_Total' in db_col_names_full:
        data_to_save_dict['Estimativa_Impostos_Total'] = edited_data['Estimativa_Impostos_Total']

    final_data_tuple = tuple(data_to_save_dict[col] for col in db_col_names_full if col != 'id')

    changes = []
    if not is_new_process and process_id is not None:
        original_process_data_dict = dict(db_manager.obter_processo_por_id(process_id))
        username = user_info.get('username')

        for col_name in db_col_names_full:
            if col_name == 'id': continue
            
            old_value = original_process_data_dict.get(col_name)
            new_value = data_to_save_dict.get(col_name)

            old_val_comp = "" if old_value is None else str(old_value).strip()
            new_val_comp = "" if new_value is None else str(new_value).strip()

            if old_val_comp != new_val_comp:
                changes.append({
                    'field_name': col_name,
                    'old_value': old_value,
                    'new_value': new_value
                })

    success = False
    if is_new_process:
        success = db_manager.inserir_processo(final_data_tuple)
        # Se for um novo processo, obter o ID recém-criado para inserir itens
        if success:
            new_process_id = db_manager.obter_ultimo_processo_id()
            if new_process_id:
                process_id = new_process_id # Atribui o ID para uso na inserção de itens
    elif process_id is not None:
        success = db_manager.atualizar_processo(process_id, final_data_tuple)

    if success:
        # Salvar os itens do processo na tabela dedicada
        if process_id is not None and 'process_items_data' in st.session_state:
            db_manager.deletar_itens_processo(process_id) # Limpa os itens existentes para evitar duplicidade
            for item in st.session_state.process_items_data:
                db_manager.inserir_item_processo(
                    process_id,
                    item.get('Código Interno'),
                    item.get('NCM'),
                    item.get('Cobertura'),
                    item.get('SKU'),
                    item.get('Quantidade'),
                    item.get('Peso Unitário'),
                    item.get('Valor Unitário'),
                    item.get('Valor total do item'), # O valor total do item que já foi calculado
                    item.get('Estimativa_II_BR'),
                    item.get('Estimativa_IPI_BR'),
                    item.get('Estimativa_PIS_BR'),
                    item.get('Estimativa_COFINS_BR'),
                    item.get('Estimativa_ICMS_BR'),
                    item.get('Frete_Rateado_USD'),
                    item.get('Seguro_Rateado_BRL'),
                    item.get('VLMD_Item'),
                    item.get('Denominação do produto'),
                    item.get('Detalhamento complementar do produto')
                )
        
        _display_message_box(f"Processo {'adicionado' if is_new_process else 'atualizado'} com sucesso!", "success")
        st.session_state.current_page = "Follow-up Importação"
        if 'form_reload_processes_callback' in st.session_state and st.session_state.form_reload_processes_callback:
            st.session_state.form_reload_processes_callback()
        st.rerun()
    else:
        _display_message_box(f"Falha ao {'adicionar' if is_new_process else 'atualizar'} processo.", "error")

# Define a standard schema for items
DEFAULT_ITEM_SCHEMA = {
    "Código Interno": None,
    "NCM": None,
    "Cobertura": "NÃO",
    "SKU": None,
    "Quantidade": 0,
    "Peso Unitário": 0.0,
    "Valor Unitário": 0.0,
    "Valor total do item": 0.0,
    "Estimativa_II_BR": 0.0,
    "Estimativa_IPI_BR": 0.0,
    "Estimativa_PIS_BR": 0.0,
    "Estimativa_COFINS_BR": 0.0,
    "Estimativa_ICMS_BR": 0.0,
    "Frete_Rateado_USD": 0.0,
    "Seguro_Rateado_BRL": 0.0,
    "VLMD_Item": 0.0,
    "Denominação do produto": None,
    "Detalhamento complementar do produto": None,
    "Fornecedor": None,
    "Invoice N#": None
}

def _standardize_item_data(item_dict: Dict[str, Any], fornecedor: Optional[str] = None, invoice_n: Optional[str] = None) -> Dict[str, Any]:
    """Ensures an item dictionary conforms to the default schema."""
    standardized_item = DEFAULT_ITEM_SCHEMA.copy()
    for key, default_value in DEFAULT_ITEM_SCHEMA.items():
        if key in item_dict:
            # If the key exists in item_dict, use its value.
            # This allows empty strings to be preserved if they came from the source.
            standardized_item[key] = item_dict[key]
        elif key == 'Fornecedor' and fornecedor is not None:
            standardized_item[key] = fornecedor
        elif key == 'Invoice N#' and invoice_n is not None:
            standardized_item[key] = invoice_n
        else:
            # If the key does not exist in item_dict, use the default value from schema.
            standardized_item[key] = default_value
    return standardized_item

def show_process_form_page(process_identifier: Optional[Any] = None, reload_processes_callback: Optional[callable] = None):
    """
    Exibe o formulário de edição/criação de processo em uma página dedicada.
    process_identifier: ID (int) ou Processo_Novo (str) do processo a ser editado. None para novo processo.
    reload_processes_callback: Função para chamar na página principal para recarregar os dados.
    """
    if reload_processes_callback:
        st.session_state.form_reload_processes_callback = reload_processes_callback

    is_new_process = process_identifier is None

    # Initialize process_data and process_id
    process_data: Dict[str, Any] = {}
    process_id: Optional[int] = None

    # Initialize st.session_state for process_items_data and process_items_loaded_for_id
    if 'process_items_data' not in st.session_state:
        st.session_state.process_items_data = []
    if 'process_items_loaded_for_id' not in st.session_state:
        st.session_state.process_items_loaded_for_id = None
    if 'current_form_process_id' not in st.session_state: # Track the ID the form is currently rendering
        st.session_state.current_form_process_id = None
    
    if not is_new_process: # Editing an existing process
        # Only load from DB if the process_identifier has changed since last render
        if process_identifier != st.session_state.process_items_loaded_for_id:
            raw_data = None
            if isinstance(process_identifier, int):
                raw_data = db_manager.obter_processo_por_id(process_identifier)
            elif isinstance(process_identifier, str):
                raw_data = db_manager.obter_processo_by_processo_novo(process_identifier)
            else:
                logger.error(f"Tipo inesperado para process_identifier: {type(process_identifier)} - {process_identifier}")
            
            if raw_data:
                process_data = dict(raw_data) # Ensure it's a dictionary
                process_id = process_data.get('id')
                if process_id:
                    # Standardize items loaded from DB
                    st.session_state.process_items_data = [_standardize_item_data(dict(row), process_data.get("Fornecedor"), process_data.get("N_Invoice")) for row in db_manager.obter_itens_processo(process_id)]
                    st.session_state.process_items_loaded_for_id = process_id
                    st.session_state.current_form_process_id = process_id # Update current form ID
            else:
                _display_message_box(f"Processo '{process_identifier}' não encontrado para edição.", "error")
                st.session_state.current_page = "Follow-up Importação"
                st.rerun()
                return
        else:
            # Process_items_data already loaded for this ID, just use existing state
            # Ensure process_data and process_id are set for the current render cycle
            if isinstance(process_identifier, int):
                raw_data = db_manager.obter_processo_por_id(process_identifier)
            elif isinstance(process_identifier, str):
                raw_data = db_manager.obter_processo_by_processo_novo(process_identifier)
            if raw_data:
                process_data = dict(raw_data)
                process_id = process_data.get('id')

    else: # is_new_process is True
        # Only clear items if we are truly starting a new, blank form
        if st.session_state.current_form_process_id != 'new_process_form_instance' or \
           st.session_state.process_items_loaded_for_id is not None: 
            st.session_state.process_items_data = []
            st.session_state.process_items_loaded_for_id = None
            st.session_state.current_form_process_id = 'new_process_form_instance' # Mark this as a new form instance
        
        process_id = None # Ensure process_id is None for a new process
    
    linked_di_id = process_data.get('DI_ID_Vinculada')
    linked_di_number = None
    if linked_di_id:
        linked_di_data = db_utils.get_declaracao_by_id(linked_di_id)
        if linked_di_data:
            linked_di_number = _format_di_number(str(linked_di_data.get('numero_di')))

    st.markdown(f"### {'Novo Processo' if is_new_process else f'Editar Processo: {process_data.get('Processo_Novo', '')}'}")

    # Define campos_config_tabs for state initialization and widget creation
    campos_config_tabs = {
        "Dados Gerais": {
            "col1": {
                "Processo_Novo": {"label": "Processo:", "type": "text"},
                "Fornecedor": {"label": "Fornecedor:", "type": "text"},
                "Tipos_de_item": {"label": "Tipos de item:", "type": "text"},
                "N_Invoice": {"label": "Nº Invoice:", "type": "text"},
                "Quantidade": {"label": "Quantidade:", "type": "number"},
                "N_Ordem_Compra": {"label": "Nº da Ordem de Compra:", "type": "text"},
                "Agente_de_Carga_Novo": {"label": "Agente de Carga:", "type": "text"},
            },
            "col2": {
                "Modal": {"label": "Modal:", "type": "dropdown", "values": ["", "Aéreo", "Maritimo"]},
                "Navio": {"label": "Navio:", "type": "text", "conditional_field": "Modal", "conditional_value": "Maritimo"}, 
                "Origem": {"label": "Origem:", "type": "text"},
                "Destino": {"label": "Destino:", "type": "text"},
                "INCOTERM": {"label": "INCOTERM:", "type": "dropdown", "values": ["","EXW","FCA","FAS","FOB","CFR","CIF","CPT","CIP","DPU","DAP","DDP"]},
                "Comprador": {"label": "Comprador:", "type": "text"},
            }
        },
        "Itens": {}, # This tab will now only display the data_editor and totals
        "Valores e Estimativas": {
            "Estimativa_Dolar_BRL": {"label": "Cambio Estimado (R$):", "type": "currency_br"},
            "Valor_USD": {"label": "Valor (USD):", "type": "currency_usd"},
            "Pago": {"label": "Pago?:", "type": "dropdown", "values": ["Não", "Sim"]},
            "Estimativa_Frete_USD": {"label": "Estimativa de Frete (USD):", "type": "currency_usd"},
            "Estimativa_Seguro_BRL": {"label": "Estimativa Seguro (R$):", "type": "currency_br"},
            "Estimativa_II_BR": {"label": "Estimativa de II (R$):", "type": "currency_br", "disabled": True},
            "Estimativa_IPI_BR": {"label": "Estimativa de IPI (R$):", "type": "currency_br", "disabled": True},
            "Estimativa_PIS_BR": {"label": "Estimativa de PIS (R$):", "type": "currency_br", "disabled": True},
            "Estimativa_COFINS_BR": {"label": "Estimativa de COFINS (R$):", "type": "currency_br", "disabled": True},
            "Estimativa_ICMS_BR": {"label": "Estimativa de ICMS (R$):", "type": "currency_br"}, # Digitável
            "Estimativa_Impostos_Total": {"label": "Estimativa Impostos (R$):", "type": "currency_br", "disabled": True}, # Novo campo
        },
        "Status Operacional": {
            "Status_Geral": {"label": "Status Geral:", "type": "dropdown", "values": db_manager.STATUS_OPTIONS},
            "Data_Compra": {"label": "Data de Compra:", "type": "date"},
            "Data_Embarque": {"label": "Data de Embarque:", "type": "date"},
            "ETA_Recinto": {"label": "ETA no Recinto:", "type": "date"},
            "Data_Registro": {"label": "Data de Registro:", "type": "date"},
            "Previsao_Pichau": {"label": "Previsão na Pichau:", "type": "date"},
            "Documentos_Revisados": {"label": "Documentos Revisados:", "type": "dropdown", "values": ["Não", "Sim"]},
            "Conhecimento_Embarque": {"label": "Conhecimento de embarque:", "type": "dropdown", "values": ["Não", "Sim"]},
            "Descricao_Feita": {"label": "Descrição Feita:", "type": "dropdown", "values": ["Não", "Sim"]},
            "Descricao_Enviada": {"label": "Descrição Enviada:", "type": "dropdown", "values": ["Não", "Sim"]},
            "Nota_feita": {"label": "Nota feita?:", "type": "dropdown", "values": ["Não", "Sim"]},
            "Conferido": {"label": "Conferido?:", "type": "dropdown", "values": ["Não", "Sim"]},
        },
        "Documentação": {
            "Caminho_da_pasta": {"label": "Caminho da pasta:", "type": "folder_path", "placeholder": "Caminho ou URL para documentos"},
            "DI_ID_Vinculada": {"label": "DI Vinculada (ID):", "type": "text", "disabled": True, "help": "ID da Declaração de Importação vinculada a este processo."},
        }
    }

    # Initialize session state for all form fields
    form_state_key = f"form_fields_process_{process_id if process_id is not None else 'new'}"
    if form_state_key not in st.session_state or st.session_state.current_form_process_id != (process_id if process_id is not None else 'new_process_form_instance'):
        st.session_state[form_state_key] = {}
        st.session_state.current_form_process_id = (process_id if process_id is not None else 'new_process_form_instance')

        # Populate initial values from process_data
        for tab_config in campos_config_tabs.values():
            if "col1" in tab_config:
                for field_name, config in tab_config["col1"].items():
                    initial_value = process_data.get(field_name, None)
                    if config["type"] == "number" and initial_value is None:
                        st.session_state[form_state_key][field_name] = 0
                    else:
                        st.session_state[form_state_key][field_name] = initial_value
            if "col2" in tab_config:
                for field_name, config in tab_config["col2"].items():
                    initial_value = process_data.get(field_name, None)
                    if "currency" in config["type"] and initial_value is None:
                        st.session_state[form_state_key][field_name] = 0.0
                    elif config["type"] == "number" and initial_value is None:
                        st.session_state[form_state_key][field_name] = 0
                    else:
                        st.session_state[form_state_key][field_name] = initial_value
            # Iterate directly on their field definitions for other tabs
            else: 
                for field_name, config in tab_config.items():
                    initial_value = process_data.get(field_name, None)
                    if "currency" in config["type"] and initial_value is None:
                        st.session_state[form_state_key][field_name] = 0.0
                    elif config["type"] == "number" and initial_value is None:
                        st.session_state[form_state_key][field_name] = 0
                    else:
                        st.session_state[form_state_key][field_name] = initial_value

        # Handle 'Observacao' separately as it's outside the tab config dict
        st.session_state[form_state_key]["Observacao"] = process_data.get("Observacao", "")

        # Set default values for new processes if process_data is empty (i.e., new form)
        if not process_data:
            st.session_state[form_state_key]["Modal"] = ""
            st.session_state[form_state_key]["INCOTERM"] = ""
            st.session_state[form_state_key]["Pago"] = "Não"
            st.session_state[form_state_key]["Status_Geral"] = ""
            st.session_state[form_state_key]["Documentos_Revisados"] = "Não"
            st.session_state[form_state_key]["Conhecimento_Embarque"] = "Não"
            st.session_state[form_state_key]["Descricao_Feita"] = "Não"
            st.session_state[form_state_key]["Descricao_Enviada"] = "Não"
            st.session_state[form_state_key]["Nota_feita"] = "Não"
            st.session_state[form_state_key]["Conferido"] = "Não"
            
    # Always ensure show_add_item_popup is in session_state
    if 'show_add_item_popup' not in st.session_state:
        st.session_state.show_add_item_popup = False
    
    # Initialize for item selection and editing
    if 'selected_item_indices' not in st.session_state:
        st.session_state.selected_item_indices = []
    if 'show_edit_item_popup' not in st.session_state:
        st.session_state.show_edit_item_popup = False
    if 'item_to_edit_index' not in st.session_state:
        st.session_state.item_to_edit_index = None


    # Tabs are now OUTSIDE the main Streamlit form
    tabs_names = list(campos_config_tabs.keys())
    tabs = st.tabs(tabs_names)

    for i, tab_name in enumerate(tabs_names):
        with tabs[i]:
            if tab_name == "Dados Gerais":
                col_left, col_right = st.columns(2)
                
                with col_left:
                    for field_name, config in campos_config_tabs[tab_name]["col1"].items():
                        label = config["label"]
                        current_value = st.session_state[form_state_key].get(field_name) # Read from session state
                        
                        if config["type"] == "number":
                            default_value = float(current_value) if (current_value is not None and pd.isna(current_value) == False) else 0.0
                            widget_value = st.number_input(label, value=default_value, format="%d", key=f"{form_state_key}_{field_name}", disabled=config.get("disabled", False))
                            st.session_state[form_state_key][field_name] = int(widget_value) if widget_value is not None else None # Update session state
                        else:
                            widget_value = st.text_input(label, value=current_value if current_value is not None else "", key=f"{form_state_key}_{field_name}", disabled=config.get("disabled", False))
                            st.session_state[form_state_key][field_name] = widget_value if widget_value else None # Update session state

                with col_right:
                    for field_name, config in campos_config_tabs[tab_name]["col2"].items():
                        label = config["label"]
                        current_value = st.session_state[form_state_key].get(field_name) # Read from session state

                        if field_name == "Modal":
                            options = config["values"]
                            default_index = 0
                            if current_value in options:
                                default_index = options.index(current_value)
                            elif current_value is not None and str(current_value).strip() != "" and current_value not in options:
                                options = [current_value] + options
                                default_index = 0
                            widget_value = st.selectbox(
                                label, 
                                options=options, 
                                index=default_index, 
                                key=f"{form_state_key}_{field_name}"
                            )
                            st.session_state[form_state_key][field_name] = widget_value if widget_value else None # Update session state
                        
                        elif "conditional_field" in config:
                            conditional_field_name = config["conditional_field"]
                            conditional_value_required = config["conditional_value"]
                            
                            current_modal_selection = st.session_state[form_state_key].get(conditional_field_name, "") # Read from session state

                            if current_modal_selection == conditional_value_required:
                                widget_value = st.text_input(label, value=current_value if current_value is not None else "", key=f"{form_state_key}_{field_name}", disabled=config.get("disabled", False))
                                st.session_state[form_state_key][field_name] = widget_value if widget_value else None # Update session state
                            else:
                                st.text_input(label, value="", key=f"{form_state_key}_{field_name}", disabled=True, help="Selecione 'Maritimo' no campo Modal para habilitar.")
                                st.session_state[form_state_key][field_name] = None # Ensure it's not saved if condition not met
                        
                        else:
                            widget_value = st.text_input(label, value=current_value if current_value is not None else "", key=f"{form_state_key}_{field_name}", disabled=config.get("disabled", False))
                            st.session_state[form_state_key][field_name] = widget_value if widget_value else None # Update session state


            elif tab_name == "Itens":
                st.subheader("Itens do Processo")
                
                current_fornecedor_context = st.session_state[form_state_key].get("Fornecedor", "N/A") # Read from session state
                current_invoice_n_context = st.session_state[form_state_key].get("N_Invoice", "N/A") # Read from session state
                st.info(f"Fornecedor: {current_fornecedor_context} | Nº Invoice: {current_invoice_n_context}") # Atualizado para mostrar o Nº Invoice

                col_add_item, col_edit_item, col_delete_item = st.columns([0.15, 0.15, 0.15])

                with col_add_item:
                    if st.button("Adicionar Item", key="add_item_button_in_items_tab"):
                        st.session_state.show_add_item_popup = True
                        st.session_state.show_edit_item_popup = False # Ensure edit popup is closed

                if st.session_state.get('show_add_item_popup', False):
                    with st.popover("Adicionar Novo Item"):
                        with st.form("add_item_form_fixed", clear_on_submit=True):
                            new_item_codigo_interno = st.text_input("Código Interno", key="new_item_codigo_interno_popup")
                            
                            all_ncm_items = db_utils.selecionar_todos_ncm_itens()
                            ncm_options = [""] + sorted([ncm_list_page.format_ncm_code(item['ncm_code']) for item in all_ncm_items]) if ncm_list_page else [""]
                            new_item_ncm_display = st.selectbox("NCM", options=ncm_options, key="new_item_ncm_popup")
                            
                            new_item_cobertura = st.selectbox("Cobertura", options=["SIM", "NÃO"], key="new_item_cobertura_popup")
                            new_item_sku = st.text_input("SKU", key="new_item_sku_popup")
                            new_item_quantidade = st.number_input("Quantidade", min_value=0, value=0, step=1, key="new_item_quantidade_popup")
                            new_item_valor_unitario = st.number_input("Valor Unitário (USD)", min_value=0.0, format="%.2f", key="new_item_valor_unitario_popup")
                            # Adicionado campos faltantes ao popover de adicionar
                            new_item_peso_unitario = st.number_input("Peso Unitário (KG)", min_value=0.0, format="%.4f", key="new_item_peso_unitario_popup")
                            new_item_denominacao = st.text_input("Denominação do produto", key="new_item_denominacao_popup")
                            new_item_detalhamento = st.text_input("Detalhamento complementar do produto", key="new_item_detalhamento_popup")

                            
                            if st.form_submit_button("Adicionar Item"):
                                raw_new_item_data = {
                                    "Código Interno": new_item_codigo_interno,
                                    "NCM": re.sub(r'\D', '', new_item_ncm_display) if new_item_ncm_display else None,
                                    "Cobertura": new_item_cobertura,
                                    "SKU": new_item_sku,
                                    "Quantidade": new_item_quantidade, 
                                    "Valor Unitário": new_item_valor_unitario,
                                    "Peso Unitário": new_item_peso_unitario, # Adicionado
                                    "Denominação do produto": new_item_denominacao, # Adicionado
                                    "Detalhamento complementar do produto": new_item_detalhamento, # Adicionado
                                    "Fornecedor": current_fornecedor_context,
                                    "Invoice N#": current_invoice_n_context
                                }
                                standardized_new_item_data = _standardize_item_data(raw_new_item_data, current_fornecedor_context, current_invoice_n_context)
                                standardized_new_item_data["Valor total do item"] = standardized_new_item_data["Quantidade"] * standardized_new_item_data["Valor Unitário"]
                                
                                st.session_state.process_items_data.append(standardized_new_item_data)
                                _display_message_box("Item adicionado com sucesso!", "success")
                                st.session_state.show_add_item_popup = False
                                st.rerun()

                st.markdown("---") 

                # Ensure df_items is created with all expected columns from the schema
                df_items = pd.DataFrame(st.session_state.process_items_data)
                
                # Garanta que todas as colunas de DEFAULT_ITEM_SCHEMA estão presentes no DataFrame
                for col in DEFAULT_ITEM_SCHEMA.keys():
                    if col not in df_items.columns:
                        df_items[col] = None

                # Recalculate totals needed for tax calculation before displaying anything
                total_invoice_value_usd_for_calc = df_items["Valor total do item"].sum() if "Valor total do item" in df_items.columns else 0
                total_invoice_weight_kg_for_calc = 0
                if "Peso Unitário" in df_items.columns and "Quantidade" in df_items.columns:
                    df_items['Peso Total do Item Calculado'] = pd.to_numeric(df_items['Peso Unitário'], errors='coerce').fillna(0) * \
                                                            pd.to_numeric(df_items['Quantidade'], errors='coerce').fillna(0)
                    total_invoice_weight_kg_for_calc = df_items['Peso Total do Item Calculado'].sum()

                # Re-calculate taxes for all items in session state
                dolar_brl = st.session_state[form_state_key].get("Estimativa_Dolar_BRL", 0.0)
                updated_process_items_data = []
                for item in st.session_state.process_items_data:
                    updated_item = calculate_item_taxes_and_values(
                        item.copy(), # Pass a copy to ensure original is not modified during calculation
                        dolar_brl,
                        total_invoice_value_usd_for_calc,
                        total_invoice_weight_kg_for_calc,
                        st.session_state[form_state_key].get('Estimativa_Frete_USD', 0.0),
                        st.session_state[form_state_key].get('Estimativa_Seguro_BRL', 0.0)
                    )
                    updated_process_items_data.append(updated_item)
                st.session_state.process_items_data = updated_process_items_data
                
                # Re-create DataFrame from the updated session state for display
                df_items = pd.DataFrame(st.session_state.process_items_data)


                if not df_items.empty: # Only proceed if there are actual items to display or edit
                    st.markdown("#### Itens do Processo:")

                    # Adicionar coluna de seleção para edição/exclusão
                    df_items['Selecionar'] = False 

                    df_items['NCM Formatado'] = df_items['NCM'].apply(lambda x: ncm_list_page.format_ncm_code(str(x)) if ncm_list_page and x is not None else str(x) if x is not None else '')

                    display_cols = [
                        "Selecionar", # Adicionado para seleção
                        "Código Interno", "NCM Formatado", "Denominação do produto", 
                        "Quantidade", "Valor Unitário", "Valor total do item", 
                        "Peso Unitário", "Cobertura", "SKU"
                    ]

                    column_config_items = {
                        "Selecionar": st.column_config.CheckboxColumn("Selecionar", default=False),
                        "Código Interno": st.column_config.TextColumn("Cód. Interno", width="small", disabled=True), # Desabilitado para edição direta
                        "NCM Formatado": st.column_config.TextColumn("NCM", width="small", disabled=True), # Desabilitado para edição direta
                        "Denominação do produto": st.column_config.TextColumn("Denominação", width="medium", disabled=True), # Desabilitado
                        "Quantidade": st.column_config.NumberColumn("Qtd.", format="%d", width="small", disabled=True), # Desabilitado
                        "Valor Unitário": st.column_config.NumberColumn("Valor Unit. (USD)", format="%.2f", width="small", disabled=True), # Desabilitado
                        "Valor total do item": st.column_config.NumberColumn("Valor Total Item (USD)", format="%.2f", disabled=True, width="small"),
                        "Peso Unitário": st.column_config.NumberColumn("Peso Unit. (KG)", format="%.4f", width="small", disabled=True), # Desabilitado
                        "Cobertura": st.column_config.SelectboxColumn("Cobertura", options=["SIM", "NÃO"], width="small", disabled=True), # Desabilitado
                        "SKU": st.column_config.TextColumn("SKU", width="small", disabled=True), # Desabilitado
                    }

                    displayed_items_df = st.data_editor(
                        df_items[display_cols],
                        column_config=column_config_items,
                        num_rows="fixed", # Impede adição/exclusão direta pela tabela
                        hide_index=True,
                        use_container_width=True,
                        key="process_items_editor"
                    )
                    
                    # Store selected indices based on the 'Selecionar' column from the displayed DataFrame
                    st.session_state.selected_item_indices = [
                        idx for idx, selected in enumerate(displayed_items_df['Selecionar']) if selected
                    ]

                    # Botões de Editar e Excluir Item
                    if st.session_state.selected_item_indices:
                        with col_edit_item:
                            if st.button("Editar Item", key="edit_selected_item_button"):
                                if len(st.session_state.selected_item_indices) == 1:
                                    st.session_state.item_to_edit_index = st.session_state.selected_item_indices[0]
                                    st.session_state.show_edit_item_popup = True
                                    st.session_state.show_add_item_popup = False # Ensure add popup is closed
                                else:
                                    _display_message_box("Selecione exatamente um item para editar.", "warning")
                        with col_delete_item:
                            if st.button("Excluir Item", key="delete_selected_item_button"):
                                # Excluir do maior índice para o menor para evitar problemas de índice
                                for idx in sorted(st.session_state.selected_item_indices, reverse=True):
                                    del st.session_state.process_items_data[idx]
                                st.session_state.selected_item_indices = [] # Limpar seleção
                                _display_message_box("Itens selecionados excluídos com sucesso!", "success")
                                st.rerun()

                    # Popover para Edição de Item
                    if st.session_state.get('show_edit_item_popup', False) and st.session_state.item_to_edit_index is not None:
                        item_index = st.session_state.item_to_edit_index
                        item_data = st.session_state.process_items_data[item_index]

                        with st.popover(f"Editar Item: {item_data.get('Código Interno', 'N/A')}"):
                            with st.form("edit_item_form_fixed", clear_on_submit=False):
                                edited_codigo_interno = st.text_input("Código Interno", value=item_data.get("Código Interno", ""), key="edit_item_codigo_interno_popup")
                                
                                all_ncm_items = db_utils.selecionar_todos_ncm_itens()
                                ncm_options = [""] + sorted([ncm_list_page.format_ncm_code(item['ncm_code']) for item in all_ncm_items]) if ncm_list_page else [""]
                                current_ncm_display = ncm_list_page.format_ncm_code(str(item_data.get("NCM", ""))) if ncm_list_page else str(item_data.get("NCM", ""))
                                edited_ncm_display = st.selectbox("NCM", options=ncm_options, index=ncm_options.index(current_ncm_display) if current_ncm_display in ncm_options else 0, key="edit_item_ncm_popup")
                                
                                edited_cobertura = st.selectbox("Cobertura", options=["SIM", "NÃO"], index=0 if item_data.get("Cobertura", "NÃO") == "SIM" else 1, key="edit_item_cobertura_popup")
                                edited_sku = st.text_input("SKU", value=item_data.get("SKU", ""), key="edit_item_sku_popup")
                                edited_quantidade = st.number_input("Quantidade", min_value=0, value=int(item_data.get("Quantidade", 0)), step=1, key="edit_item_quantidade_popup")
                                edited_valor_unitario = st.number_input("Valor Unitário (USD)", min_value=0.0, value=float(item_data.get("Valor Unitário", 0.0)), format="%.2f", key="edit_item_valor_unitario_popup")
                                edited_peso_unitario = st.number_input("Peso Unitário (KG)", min_value=0.0, value=float(item_data.get("Peso Unitário", 0.0)), format="%.4f", key="edit_item_peso_unitario_popup")
                                edited_denominacao = st.text_input("Denominação do produto", value=item_data.get("Denominação do produto", ""), key="edit_item_denominacao_popup")
                                edited_detalhamento = st.text_input("Detalhamento complementar do produto", value=item_data.get("Detalhamento complementar do produto", ""), key="edit_item_detalhamento_popup")

                                if st.form_submit_button("Salvar Edição"):
                                    # Update item data in session state
                                    st.session_state.process_items_data[item_index]["Código Interno"] = edited_codigo_interno
                                    st.session_state.process_items_data[item_index]["NCM"] = re.sub(r'\D', '', edited_ncm_display) if edited_ncm_display else None
                                    st.session_state.process_items_data[item_index]["Cobertura"] = edited_cobertura
                                    st.session_state.process_items_data[item_index]["SKU"] = edited_sku
                                    st.session_state.process_items_data[item_index]["Quantidade"] = edited_quantidade
                                    st.session_state.process_items_data[item_index]["Valor Unitário"] = edited_valor_unitario
                                    st.session_state.process_items_data[item_index]["Peso Unitário"] = edited_peso_unitario
                                    st.session_state.process_items_data[item_index]["Denominação do produto"] = edited_denominacao
                                    st.session_state.process_items_data[item_index]["Detalhamento complementar do produto"] = edited_detalhamento
                                    st.session_state.process_items_data[item_index]["Valor total do item"] = edited_quantidade * edited_valor_unitario
                                    
                                    # Recalculate taxes for this item immediately after editing
                                    dolar_brl_form_state = st.session_state[form_state_key].get("Estimativa_Dolar_BRL", 0.0)
                                    
                                    # Recalculate total invoice value and weight from the current session state items
                                    temp_df_for_recalc = pd.DataFrame(st.session_state.process_items_data)
                                    total_invoice_value_usd_recalc = temp_df_for_recalc["Valor total do item"].sum() if "Valor total do item" in temp_df_for_recalc.columns else 0
                                    total_invoice_weight_kg_recalc = 0
                                    if "Peso Unitário" in temp_df_for_recalc.columns and "Quantidade" in temp_df_for_recalc.columns:
                                        total_invoice_weight_kg_recalc = (pd.to_numeric(temp_df_for_recalc['Peso Unitário'], errors='coerce').fillna(0) * \
                                                                            pd.to_numeric(temp_df_for_recalc['Quantidade'], errors='coerce').fillna(0)).sum()

                                    updated_item_after_recalc = calculate_item_taxes_and_values(
                                        st.session_state.process_items_data[item_index], # Pass reference to modify directly
                                        dolar_brl_form_state, 
                                        total_invoice_value_usd_recalc, 
                                        total_invoice_weight_kg_recalc, 
                                        st.session_state[form_state_key].get('Estimativa_Frete_USD', 0.0), 
                                        st.session_state[form_state_key].get('Estimativa_Seguro_BRL', 0.0)
                                    )
                                    # The item in session_state.process_items_data is already updated by passing reference

                                    _display_message_box("Item editado com sucesso!", "success")
                                    st.session_state.show_edit_item_popup = False
                                    st.session_state.item_to_edit_index = None
                                    st.session_state.selected_item_indices = [] # Limpar seleção
                                    st.rerun()
                                if st.form_submit_button("Cancelar"):
                                    st.session_state.show_edit_item_popup = False
                                    st.session_state.item_to_edit_index = None
                                    st.session_state.selected_item_indices = [] # Limpar seleção
                                    st.rerun()

                    # Recalcular total_invoice_value_usd e total_invoice_weight_kg com base nos dados ATUALIZADOS
                    # Estes totais são para exibição no resumo e para o cálculo de impostos globais.
                    df_items_for_summary_calc = pd.DataFrame(st.session_state.process_items_data)
                    
                    total_invoice_value_usd = df_items_for_summary_calc["Valor total do item"].sum() if "Valor total do item" in df_items_for_summary_calc.columns else 0
                    
                    total_invoice_weight_kg = 0
                    if "Peso Unitário" in df_items_for_summary_calc.columns and "Quantidade" in df_items_for_summary_calc.columns:
                        total_invoice_weight_kg = (pd.to_numeric(df_items_for_summary_calc['Peso Unitário'], errors='coerce').fillna(0) * \
                                                   pd.to_numeric(df_items_for_summary_calc['Quantidade'], errors='coerce').fillna(0)).sum()


                    st.markdown("---")
                    st.subheader("Resumo de Itens para Cálculos")
                    st.write(f"Valor Total dos Itens (USD): **{total_invoice_value_usd:,.2f}**".replace('.', '#').replace(',', '.').replace('#', ','))
                    st.write(f"Peso Total dos Itens (KG): **{total_invoice_weight_kg:,.4f}**".replace('.', '#').replace(',', '.').replace('#', ','))

                    st.session_state.total_invoice_value_usd = total_invoice_value_usd
                    st.session_state.total_invoice_weight_kg = total_invoice_weight_kg

                else:
                    st.info("Nenhum item adicionado a este processo ainda. Use as opções acima para adicionar.")

            elif tab_name == "Valores e Estimativas":
                st.subheader("Valores e Estimativas")
                
                # Use o total_invoice_value_usd de st.session_state como valor padrão para Valor_USD
                total_itens_usd_from_session = st.session_state.get('total_invoice_value_usd', 0.0)
                
                dolar_brl_current = st.session_state[form_state_key].get("Estimativa_Dolar_BRL", 0.0)
                # Valor_USD agora começa preenchido com o total dos itens
                valor_usd_current = st.session_state[form_state_key].get("Valor_USD") 
                # Se o valor atual for 0 e o total de itens for maior, atualize o valor do campo
                if valor_usd_current == 0.0 and total_itens_usd_from_session > 0.0:
                    valor_usd_current = total_itens_usd_from_session

                pago_current = st.session_state[form_state_key].get("Pago", "Não")
                frete_usd_current = st.session_state[form_state_key].get("Estimativa_Frete_USD", 0.0)
                seguro_brl_current = st.session_state[form_state_key].get("Estimativa_Seguro_BRL", 0.0)
                icms_br_manual_estimate_current = st.session_state[form_state_key].get("Estimativa_ICMS_BR", 0.0) 

                st.session_state[form_state_key]["Estimativa_Dolar_BRL"] = st.number_input(
                    "Cambio Estimado (R$):", 
                    value=float(dolar_brl_current), 
                    format="%.2f", 
                    key=f"{form_state_key}_Estimativa_Dolar_BRL"
                )
                st.session_state[form_state_key]["Valor_USD"] = st.number_input(
                    "Valor (USD):", 
                    value=float(valor_usd_current), 
                    format="%.2f", 
                    key=f"{form_state_key}_Valor_USD"
                )
                st.session_state[form_state_key]["Pago"] = st.selectbox(
                    "Pago?:", 
                    options=["Não", "Sim"], 
                    index=0 if pago_current == "Não" else 1, 
                    key=f"{form_state_key}_Pago"
                )
                st.session_state[form_state_key]["Estimativa_Frete_USD"] = st.number_input(
                    "Estimativa de Frete (USD):", 
                    value=float(frete_usd_current), 
                    format="%.2f", 
                    key=f"{form_state_key}_Estimativa_Frete_USD"
                )
                st.session_state[form_state_key]["Estimativa_Seguro_BRL"] = st.number_input(
                    "Estimativa Seguro (R$):", 
                    value=float(seguro_brl_current), 
                    format="%.2f", 
                    key=f"{form_state_key}_Estimativa_Seguro_BRL"
                )
                
                st.session_state[form_state_key]["Estimativa_ICMS_BR"] = st.number_input(
                    "Estimativa de ICMS (R$ - Manual):", 
                    value=float(icms_br_manual_estimate_current), 
                    format="%.2f",
                    key=f"{form_state_key}_Estimativa_ICMS_BR"
                )
                
                dolar_brl = st.session_state[form_state_key].get("Estimativa_Dolar_BRL", 0.0)
                total_invoice_value_usd = st.session_state.get('total_invoice_value_usd', 0.0)
                total_invoice_weight_kg = st.session_state.get('total_invoice_weight_kg', 0.0)
                estimativa_frete_usd = st.session_state[form_state_key].get('Estimativa_Frete_USD', 0.0)
                estimativa_seguro_brl = st.session_state[form_state_key].get('Estimativa_Seguro_BRL', 0.0)

                total_ii = total_ipi = total_pis = total_cofins = total_icms_calculated_sum = 0.0
                if st.session_state.process_items_data:
                    # Nao precisa recalcular itens inteiros aqui, eles ja foram atualizados na aba Itens
                    # Apenas somar os totais dos itens existentes
                    for item in st.session_state.process_items_data:
                        total_ii += item.get('Estimativa_II_BR', 0.0)
                        total_ipi += item.get('Estimativa_IPI_BR', 0.0)
                        total_pis += item.get('Estimativa_PIS_BR', 0.0)
                        total_cofins += item.get('Estimativa_COFINS_BR', 0.0)
                        total_icms_calculated_sum += item.get('Estimativa_ICMS_BR', 0.0)

                st.session_state[form_state_key]['Estimativa_II_BR'] = total_ii
                st.session_state[form_state_key]['Estimativa_IPI_BR'] = total_ipi
                st.session_state[form_state_key]['Estimativa_PIS_BR'] = total_pis
                st.session_state[form_state_key]['Estimativa_COFINS_BR'] = total_cofins
                
                # Calcular Estimativa Impostos (R$) - Soma de todos os impostos calculados
                total_impostos_reais = total_ii + total_ipi + total_pis + total_cofins + total_icms_calculated_sum
                st.session_state[form_state_key]['Estimativa_Impostos_Total'] = total_impostos_reais


                st.markdown("---")
                st.subheader("Totais de Impostos Calculados (Soma dos itens)")
                st.number_input("Estimativa de II (R$ - Calculado):", value=total_ii, format="%.2f", disabled=True, key=f"display_{form_state_key}_II_BR_calc")
                st.number_input("Estimativa de IPI (R$ - Calculado):", value=total_ipi, format="%.2f", disabled=True, key=f"display_{form_state_key}_IPI_BR_calc")
                st.number_input("Estimativa de PIS (R$ - Calculado):", value=total_pis, format="%.2f", disabled=True, key=f"display_{form_state_key}_PIS_BR_calc")
                st.number_input("Estimativa de COFINS (R$ - Calculado):", value=total_cofins, format="%.2f", disabled=True, key=f"display_{form_state_key}_COFINS_BR_calc")
                st.number_input("Estimativa de ICMS (R$ - Calculado):", value=total_icms_calculated_sum, format="%.2f", disabled=True, key=f"display_{form_state_key}_ICMS_BR_calc")
                st.number_input("Estimativa Impostos (R$):", value=total_impostos_reais, format="%.2f", disabled=True, key=f"display_{form_state_key}_Impostos_Total_calc") # Campo adicionado
                st.caption("Os valores acima são a soma dos impostos calculados para cada item com base no NCM.")
                
            elif tab_name == "Status Operacional":
                st.subheader("Status Operacional")
                for field_name, config in campos_config_tabs[tab_name].items():
                    label = config["label"]
                    current_value = st.session_state[form_state_key].get(field_name)

                    if config["type"] == "date":
                        current_value_dt = None
                        if current_value:
                            try:
                                current_value_dt = datetime.strptime(str(current_value), "%Y-%m-%d")
                            except ValueError:
                                current_value_dt = None
                        widget_value = st.date_input(label, value=current_value_dt, key=f"{form_state_key}_{field_name}", format="DD/MM/YYYY")
                        st.session_state[form_state_key][field_name] = widget_value.strftime("%Y-%m-%d") if widget_value else None
                    elif config["type"] == "dropdown":
                        options = config["values"]
                        default_index = 0
                        if current_value in options:
                            default_index = options.index(current_value)
                        elif current_value is not None and str(current_value).strip() != "" and current_value not in options:
                            options = [current_value] + options
                            default_index = 0
                        widget_value = st.selectbox(label, options=options, index=default_index, key=f"{form_state_key}_{field_name}")
                        st.session_state[form_state_key][field_name] = widget_value if widget_value else None
                    else:
                        widget_value = st.text_input(label, value=current_value if current_value is not None else "", key=f"{form_state_key}_{field_name}")
                        st.session_state[form_state_key][field_name] = widget_value if widget_value else None

            elif tab_name == "Documentação":
                st.subheader("Documentação")
                for field_name, config in campos_config_tabs[tab_name].items():
                    label = config["label"]
                    current_value = st.session_state[form_state_key].get(field_name)

                    if config["type"] == "folder_path":
                        widget_value = st.text_input(label, value=current_value if current_value is not None else "", placeholder=config.get("placeholder", ""), key=f"{form_state_key}_{field_name}")
                        st.session_state[form_state_key][field_name] = widget_value if widget_value else None
                        st.info("Este campo é apenas para registro do caminho ou URL. Não faz upload de arquivos diretamente.")
                    elif config["type"] == "text" and config.get("disabled"):
                        di_vinculada_value = None
                        processo_novo_val = st.session_state[form_state_key].get("Processo_Novo") 
                        if processo_novo_val:
                            linked_di_data_by_process_number = db_utils.get_declaracao_by_referencia(str(processo_novo_val)) 
                            if linked_di_data_by_process_number:
                                di_vinculada_value = linked_di_data_by_process_number.get('id')
                                if di_vinculada_value:
                                    st.info(f"DI vinculada automaticamente: ID {di_vinculada_value} (Nº DI: {_format_di_number(str(linked_di_data_by_process_number.get('numero_di')))})")
                            else:
                                st.info(f"Nenhuma DI encontrada para o processo '{processo_novo_val}'.")

                        display_value = str(di_vinculada_value) if di_vinculada_value is not None else ""
                        st.text_input(label, value=display_value, key=f"{form_state_key}_{field_name}", disabled=True, help=config.get("help"))
                        st.session_state[form_state_key][field_name] = di_vinculada_value
                    else:
                        widget_value = st.text_input(label, value=current_value if current_value is not None else "", key=f"{form_state_key}_{field_name}")
                        st.session_state[form_state_key][field_name] = widget_value if widget_value else None
            
    st.markdown("---")
    st.markdown("##### Observação (Campo Dedicado)")
    st.session_state[form_state_key]["Observacao"] = st.text_area("Observação", value=st.session_state[form_state_key].get("Observacao", "") or "", height=150, key=f"{form_state_key}_Observacao_dedicated")
    st.session_state[form_state_key]["Observacao"] = st.session_state[form_state_key]["Observacao"] if st.session_state[form_state_key]["Observacao"] else None

    st.markdown("---")
    st.markdown("##### Histórico do Processo")
    if not is_new_process:
        history_data_raw = db_manager.obter_historico_processo(process_id if process_id is not None else -1) 
        if history_data_raw:
            history_df = pd.DataFrame(history_data_raw, columns=["Campo", "Valor Antigo", "Valor Novo", "Timestamp", "Usuário"])
            history_df["Timestamp"] = history_df["Timestamp"].apply(lambda x: datetime.strptime(str(x), "%Y-%m-%d %H:%M:%S").strftime("%d/%m/%Y %H:%M:%S") if x else "")
            st.dataframe(history_df, use_container_width=True, hide_index=True)
        else:
            st.info("Nenhum histórico de alterações para este processo.")
    else:
        st.info("Histórico disponível apenas para processos existentes após a primeira gravação.")

    # Main form only for saving and canceling
    with st.form(key=f"followup_process_form_submit_buttons_{process_id}", clear_on_submit=False):
        col_save, col_cancel  = st.columns([0.03, 0.1])

        with col_save:
            if st.form_submit_button("Salvar Processo"):
                # Construct edited_data from session state before saving
                edited_data_to_save = {}
                for tab_config in campos_config_tabs.values():
                    if "col1" in tab_config:
                        for field_name, config in tab_config["col1"].items():
                            edited_data_to_save[field_name] = st.session_state[form_state_key].get(field_name)
                    if "col2" in tab_config:
                        for field_name, config in tab_config["col2"].items():
                            edited_data_to_save[field_name] = st.session_state[form_state_key].get(field_name)
                    # For other tabs that have fields directly
                    if tab_config not in [campos_config_tabs["Dados Gerais"]]:
                        for field_name, config in tab_config.items():
                            edited_data_to_save[field_name] = st.session_state[form_state_key].get(field_name)
                # Ensure 'Observacao' is also included
                edited_data_to_save["Observacao"] = st.session_state[form_state_key].get("Observacao")
                
                _save_process_action(process_id, edited_data_to_save, is_new_process)
        with col_cancel:
            if st.form_submit_button("Cancelar"):
                # Clear form state and go back to main page
                st.session_state.current_page = "Follow-up Importação"
                # Clear the specific form state key to re-initialize on next load
                if form_state_key in st.session_state:
                    del st.session_state[form_state_key]
                st.session_state.show_add_item_popup = False # Also reset popover state
                st.rerun()

        col_delete = st.columns([0.0000003, 0.01])[1]

        with col_delete:
            if not is_new_process:
                confirm_delete = st.checkbox("Confirmar exclusão", key=f"confirm_delete_process_{process_id}")
                if st.form_submit_button("Excluir Processo"):
                    if confirm_delete:
                        _display_message_box("A funcionalidade de exclusão direta por este formulário está temporariamente desabilitada. Por favor, use o botão de exclusão na tela principal de Follow-up.", "warning")
                    else:
                        st.warning("Marque a caixa de confirmação para excluir o processo.")
            else:
                st.info("Excluir disponível após salvar o processo.")
        
    if linked_di_id is not None and linked_di_number:
        st.markdown("---")
        st.markdown(f"**DI Vinculada:** {linked_di_number}")
        if st.button(f"Ver Detalhes da DI {linked_di_number}", key=f"view_linked_di_outside_form_{process_id}"):
            st.session_state.current_page = "Importar XML DI"
            st.session_state.selected_di_id = linked_di_id
            st.rerun()

    elif linked_di_id is not None and not linked_di_number: 
        st.markdown("---")
        st.warning(f"DI vinculada (ID: {linked_di_id}) não encontrada no banco de dados de Declarações de Importação.")
