import streamlit as st
import pandas as pd
from datetime import datetime, date
import logging
import os
import subprocess
import sys
import io
import xlsxwriter
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from typing import Optional, Any, Dict, List, Union
import numpy as np
import base64
import re
import uuid
# Removido: import pdfplumber # Importar pdfplumber

# Importar db_manager explicitamente no início
import followup_db_manager as db_manager

# Importar função para buscar cotação do dólar
try:
    from app_logic.utils import get_dolar_cotacao
    from app_logic import db_utils
except ImportError:
    get_dolar_cotacao = None
    db_utils = None

# Configuração do logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG) # Manter DEBUG para logs detalhados durante o desenvolvimento

# --- Função para obter cotação atual do dólar PTAX Venda ---
def get_current_dolar_ptax_venda():
    """
    Obtém a cotação atual do dólar PTAX Venda.
    Primeiro tenta da API, depois do banco de dados, finalmente usa valor padrão.
    """
    try:
        # Valor padrão caso não consiga obter de nenhuma fonte
        default_value = 5.50
        
        # Primeiro tenta da API
        if get_dolar_cotacao:
            try:
                dolar_data_api = get_dolar_cotacao()
                if dolar_data_api and isinstance(dolar_data_api, dict) and 'ptax_venda' in dolar_data_api:
                    ptax_venda_str = dolar_data_api['ptax_venda']
                    if ptax_venda_str and str(ptax_venda_str).strip() != 'N/A':
                        # Converte string com vírgula para float
                        ptax_value = float(str(ptax_venda_str).replace(',', '.'))
                        if ptax_value > 0:  # Verifica se é um valor válido
                            logger.info(f"[get_current_dolar_ptax_venda] Obtido da API: {ptax_value}")
                            return ptax_value
            except Exception as api_error:
                logger.warning(f"[get_current_dolar_ptax_venda] Erro na API: {api_error}")
        
        # Se não conseguiu da API, tenta do banco de dados
        if db_utils and hasattr(db_utils, 'get_latest_dolar_cotacao_from_db'):
            try:
                latest_cotacoes = db_utils.get_latest_dolar_cotacao_from_db()
                if latest_cotacoes and isinstance(latest_cotacoes, dict) and 'ptax_venda' in latest_cotacoes:
                    db_entry = latest_cotacoes['ptax_venda']
                    if isinstance(db_entry, dict) and 'valor' in db_entry:
                        ptax_value = float(db_entry['valor'])
                        if ptax_value > 0:  # Verifica se é um valor válido
                            logger.info(f"[get_current_dolar_ptax_venda] Obtido do banco: {ptax_value}")
                            return ptax_value
            except Exception as db_error:
                logger.warning(f"[get_current_dolar_ptax_venda] Erro no banco: {db_error}")
        
        # Valor padrão se não conseguir obter de nenhuma fonte
        logger.warning(f"[get_current_dolar_ptax_venda] Usando valor padrão: {default_value}")
        return default_value
        
    except Exception as e:
        logger.error(f"[get_current_dolar_ptax_venda] Erro geral: {e}")
        return 5.50  # Valor padrão em caso de erro

# Configuração do logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG) # Manter DEBUG para logs detalhados durante o desenvolvimento

# --- Funções Auxiliares de UI e Estilo ---

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
                opacity: 0.50;
                z-index: -1;
            }}
            </style>
            """,
            unsafe_allow_html=True
        )
    except FileNotFoundError:
        logger.warning(f"A imagem de fundo não foi encontrada no caminho: {image_path}")
        st.warning(f"A imagem de fundo não foi encontrada no caminho: {image_path}")
    except Exception as e:
        logger.error(f"Erro ao carregar a imagem de fundo: {e}")
        st.error(f"Erro ao carregar a imagem de fundo: {e}")

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

# --- Classes Mock para Dependências (se necessário) ---

# Define a classe MockDbUtils globalmente, para evitar redeclarações
class MockDbUtils:
    """Classe Mock para simular funcionalidades do db_utils quando o módulo real não está disponível."""
    def get_db_path(self, db_name: str) -> str:
        _base_path = os.path.dirname(os.path.abspath(__file__))
        _app_root_path = os.path.dirname(_base_path) if os.path.basename(_base_path) == 'app_logic' else _base_path
        _DEFAULT_DB_FOLDER = "data"
        return os.path.join(_app_root_path, _DEFAULT_DB_FOLDER, f"{db_name}.db")
    
    def get_declaracao_by_id(self, di_id: int) -> Optional[dict]:
        """Função mock para simulação de obtenção de DI por ID."""
        if di_id == 999: # Exemplo de DI mock
            return {'numero_di': '9988776654', 'id': 999}
        return None 
    
    def get_declaracao_by_referencia(self, process_number: str) -> Optional[dict]:
        """Função mock para simulação de obtenção de DI por número de processo."""
        if process_number == "MOCK-DI-123": # Exemplo de DI mock
            return {'numero_di': '9988776654', 'id': 999}
        return None

    def get_ncm_item_by_ncm_code(self, ncm_code: str) -> Optional[dict]:
        """Função mock para simulação de obtenção de dados NCM por código."""
        # Adicionando alguns NCMs de exemplo para teste
        ncm_data = {
            "85171231": {'ncm_code': '85171231', 'descricao_item': 'Telefones celulares', 'ii_aliquota': 16.0, 'ipi_aliquota': 5.0, 'pis_aliquota': 1.65, 'cofins_aliquota': 7.6, 'icms_aliquota': 18.0},
            "84713012": {'ncm_code': '84713012', 'descricao_item': 'Notebooks', 'ii_aliquota': 10.0, 'ipi_aliquota': 0.0, 'pis_aliquota': 1.65, 'cofins_aliquota': 7.6, 'icms_aliquota': 18.0},
            "9403890": {'ncm_code': '9403890', 'descricao_item': 'Móveis de metal, uso doméstico', 'ii_aliquota': 10.0, 'ipi_aliquota': 0.0, 'pis_aliquota': 1.65, 'cofins_aliquota': 7.6, 'icms_aliquota': 18.0},
            # Adicione mais NCMs conforme necessário para seus testes
        }
        return ncm_data.get(ncm_code)

    def selecionar_todos_ncm_itens(self) -> List[Dict[str, Any]]:
        """Função mock para simulação de obtenção de todos os itens NCM."""
        return [
            {'ID': 1, 'ncm_code': '85171231', 'descricao_item': 'Telefones celulares', 'ii_aliquota': 16.0, 'ipi_aliquota': 5.0, 'pis_aliquota': 1.65, 'cofins_aliquota': 7.6, 'icms_aliquota': 18.0},
            {'ID': 2, 'ncm_code': '84713012', 'descricao_item': 'Notebooks', 'ii_aliquota': 10.0, 'ipi_aliquota': 0.0, 'pis_aliquota': 1.65, 'cofins_aliquota': 7.6, 'icms_aliquota': 18.0},
            {'ID': 3, 'ncm_code': '9403890', 'descricao_item': 'Móveis de metal, uso doméstico', 'ii_aliquota': 10.0, 'ipi_aliquota': 0.0, 'pis_aliquota': 1.65, 'cofins_aliquota': 7.6, 'icms_aliquota': 18.0},
        ]
    
    def search_ncm_by_description(self, description: str) -> Optional[Dict[str, Any]]:
        """Função mock para simulação de busca de NCM por descrição."""
        description_lower = description.lower()
        if "mesa" in description_lower:
            return {'ncm_code': '9403890', 'descricao_item': 'Móveis de metal, uso doméstico'}
        elif "celular" in description_lower:
            return {'ncm_code': '85171231', 'descricao_item': 'Telefones celulares'}
        return None


# Importa db_utils real, ou usa o mock se houver erro
db_utils: Union[Any, MockDbUtils] = MockDbUtils() # Inicializa com o mock por padrão
try:
    import db_utils as real_db_utils # Importa com um alias para evitar sombreamento
    # Verifica se o db_utils real tem as funções esperadas
    if all(hasattr(real_db_utils, func) for func in [
        'get_declaracao_by_id', 'get_declaracao_by_referencia', 
        'get_ncm_item_by_ncm_code', 'selecionar_todos_ncm_itens',
        'search_ncm_by_description'
    ]):
        db_utils = real_db_utils # Usa o real se for válido
        logger.info("db_utils.py: Real db_utils importado e validado.")
    else:
        logger.warning("db_utils.py: Real db_utils encontrado mas incompleto. Usando MockDbUtils.")
except ImportError:
    logger.warning("Módulo 'db_utils' não encontrado. Usando MockDbUtils.")
except Exception as e:
    logger.error(f"db_utils.py: Erro ao importar ou inicializar 'db_utils': {e}. Usando MockDbUtils.")

# Importar pdf_analyzer_page.py e ncm_list_page para reuso de funções
pdf_analyzer_page = None
try:
    from app_logic import pdf_analyzer_page
    # pdfplumber já importado no topo
except ImportError:
    logger.warning("Módulo 'pdf_analyzer_page' não encontrado. Funções de análise de PDF não estarão disponíveis.")

ncm_list_page = None
try:
    from app_logic import ncm_list_page
except ImportError:
    logger.warning("Módulo 'ncm_list_page' não encontrado. Funções NCM não estarão disponíveis.")


# --- Funções Auxiliares para Formatação de Dados ---
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
            # Garante que di_data é um dicionário ou se comporta como um
            return _format_di_number(str(di_data.get('numero_di') if isinstance(di_data, dict) else di_data['numero_di']))
    except Exception as e:
        logger.error(f"Erro ao buscar DI por ID {di_id}: {e}")
    return "DI Não Encontrada"

# --- Funções de Cálculo de Impostos ---
@st.cache_data(ttl=3600) # Cache de 1 hora para dados NCM
def get_ncm_taxes(ncm_code: str) -> Dict[str, float]:
    """
    Busca as alíquotas de impostos para um dado NCM diretamente do Firestore.
    Sempre retorna as alíquotas mais atualizadas da coleção 'ncm_impostos_items'.
    """
    if not ncm_code:
        logger.warning(f"[get_ncm_taxes] NCM code vazio ou None fornecido")
        return {'ii_aliquota': 0.0, 'ipi_aliquota': 0.0, 'pis_aliquota': 0.0, 'cofins_aliquota': 0.0, 'icms_aliquota': 0.0}
    
    # Garante que o NCM está limpo (apenas dígitos)
    ncm_code_clean = re.sub(r'\D', '', str(ncm_code))
    if not ncm_code_clean:
        logger.warning(f"[get_ncm_taxes] NCM code após limpeza resultou vazio: {ncm_code}")
        return {'ii_aliquota': 0.0, 'ipi_aliquota': 0.0, 'pis_aliquota': 0.0, 'cofins_aliquota': 0.0, 'icms_aliquota': 0.0}
    
    logger.info(f"[get_ncm_taxes] Buscando alíquotas para NCM: {ncm_code_clean}")
    
    # Busca diretamente no Firestore
    ncm_data_raw = db_utils.get_ncm_item_by_ncm_code(ncm_code_clean)
    ncm_data = dict(ncm_data_raw) if ncm_data_raw else None

    if ncm_data:
        taxes = {
            'ii_aliquota': float(ncm_data.get('ii_aliquota', 0.0)),
            'ipi_aliquota': float(ncm_data.get('ipi_aliquota', 0.0)),
            'pis_aliquota': float(ncm_data.get('pis_aliquota', 0.0)),
            'cofins_aliquota': float(ncm_data.get('cofins_aliquota', 0.0)),
            'icms_aliquota': float(ncm_data.get('icms_aliquota', 0.0))
        }
        logger.info(f"[get_ncm_taxes] Alíquotas encontradas para NCM {ncm_code_clean}: II={taxes['ii_aliquota']}%, IPI={taxes['ipi_aliquota']}%, PIS={taxes['pis_aliquota']}%, COFINS={taxes['cofins_aliquota']}%, ICMS={taxes['icms_aliquota']}%")
        return taxes
    else:
        logger.warning(f"[get_ncm_taxes] NCM {ncm_code_clean} não encontrado no Firestore. Usando alíquotas zeradas.")
        return {'ii_aliquota': 0.0, 'ipi_aliquota': 0.0, 'pis_aliquota': 0.0, 'cofins_aliquota': 0.0, 'icms_aliquota': 0.0}

def calculate_item_taxes_and_values(item: Dict[str, Any], dolar_brl: float, total_invoice_value_usd: float, total_invoice_weight_kg: float, estimativa_frete_usd: float, estimativa_seguro_brl: float) -> Dict[str, Any]:
    """
    Calcula o VLMD, impostos e rateios para um item individual.
    Sempre busca as alíquotas mais atualizadas do Firestore.
    Retorna o item com os campos de impostos atualizados e valores rateados.
    """
    item_qty = float(item.get('Quantidade', 0))
    item_unit_value_usd = float(item.get('Valor Unitário', 0))
    item_value_usd = item_qty * item_unit_value_usd

    # Para evitar divisão por zero, use max(1, ...)
    value_ratio = item_value_usd / max(1, total_invoice_value_usd)
    # Como removemos Peso Unitário, usamos apenas o rateio por valor
    weight_ratio = value_ratio

    # Rateio de frete e seguro
    frete_rateado_usd = estimativa_frete_usd * value_ratio
    seguro_rateado_brl = estimativa_seguro_brl * weight_ratio

    # NCM e impostos - SEMPRE busca as alíquotas atualizadas do Firestore
    ncm_code = str(item.get('NCM', ''))
    ncm_taxes = get_ncm_taxes(ncm_code)  # Busca sempre as alíquotas atualizadas
    
    logger.info(f"[calculate_item_taxes_and_values] Calculando impostos para item NCM {ncm_code}, alíquotas: II={ncm_taxes['ii_aliquota']}%, IPI={ncm_taxes['ipi_aliquota']}%, PIS={ncm_taxes['pis_aliquota']}%, COFINS={ncm_taxes['cofins_aliquota']}%, ICMS={ncm_taxes['icms_aliquota']}%")

    # VLMD_Item (Valor da Mercadoria no Local de Desembaraço)
    vlmd_item = (item_unit_value_usd * item_qty * dolar_brl) + (frete_rateado_usd * dolar_brl) + seguro_rateado_brl
    
    # Cálculos de impostos usando as alíquotas atualizadas
    item['Estimativa_II_BR'] = vlmd_item * (ncm_taxes['ii_aliquota'] / 100)
    item['Estimativa_IPI_BR'] = (vlmd_item + item['Estimativa_II_BR']) * (ncm_taxes['ipi_aliquota'] / 100)
    item['Estimativa_PIS_BR'] = vlmd_item * (ncm_taxes['pis_aliquota'] / 100)
    item['Estimativa_COFINS_BR'] = vlmd_item * (ncm_taxes['cofins_aliquota'] / 100)
    item['Estimativa_ICMS_BR'] = (vlmd_item * (ncm_taxes['icms_aliquota'] / 100))

    item['VLMD_Item'] = vlmd_item
    item['Frete_Rateado_USD'] = frete_rateado_usd
    item['Seguro_Rateado_BRL'] = seguro_rateado_brl

    logger.info(f"[calculate_item_taxes_and_values] Impostos calculados: II=R${item['Estimativa_II_BR']:.2f}, IPI=R${item['Estimativa_IPI_BR']:.2f}, PIS=R${item['Estimativa_PIS_BR']:.2f}, COFINS=R${item['Estimativa_COFINS_BR']:.2f}, ICMS=R${item['Estimativa_ICMS_BR']:.2f}")

    return item

# --- Lógica para Salvar Processo ---
def _save_process_action(process_id_from_form_load: Optional[Any], edited_data: dict, is_new_process_flag: bool, form_state_key: str) -> Optional[Any]:
    """
    Lógica para salvar ou atualizar um processo.
    Retorna o ID do processo salvo/atualizado (int para SQLite, str para Firestore).
    """
    db_col_names_full = db_manager.obter_nomes_colunas_db()
    data_to_save_dict = {col: None for col in db_col_names_full if col != 'id'}

    for col_name, value in edited_data.items():
        if col_name in data_to_save_dict:
            if isinstance(value, (datetime, date)):
                data_to_save_dict[col_name] = value.strftime("%Y-%m-%d")
            elif isinstance(value, str) and value.strip() == '':
                data_to_save_dict[col_name] = None
            elif pd.isna(value) if isinstance(value, (float, int, np.number)) else False: # Tratamento robusto para NaN
                data_to_save_dict[col_name] = None
            else:
                data_to_save_dict[col_name] = value
        else:
            logger.warning(f"Campo '{col_name}' do formulário não corresponde a uma coluna no DB. Ignorado.")

    # Trata campos específicos como 'Status_Arquivado', 'Caminho_da_pasta', 'DI_ID_Vinculada'
    # Esta lógica foi mantida para garantir a compatibilidade com o comportamento existente.
    if 'Status_Arquivado' in db_col_names_full:
        if is_new_process_flag:
            data_to_save_dict['Status_Arquivado'] = 'Não Arquivado'
        else:
            original_process_data_raw = db_manager.obter_processo_por_id(process_id_from_form_load if process_id_from_form_load is not None else -1)
            original_process_data = dict(original_process_data_raw) if original_process_data_raw else {}
            data_to_save_dict['Status_Arquivado'] = original_process_data.get('Status_Arquivado', 'Não Arquivado') # Fallback robusto
    
    if 'Caminho_da_pasta' in db_col_names_full:
        data_to_save_dict['Caminho_da_pasta'] = edited_data.get('Caminho_da_pasta')

    if 'DI_ID_Vinculada' in db_col_names_full:
        if 'DI_ID_Vinculada' in edited_data and edited_data['DI_ID_Vinculada'] is not None:
            data_to_save_dict['DI_ID_Vinculada'] = edited_data['DI_ID_Vinculada']
        elif not is_new_process_flag:
            original_process_data_raw = db_manager.obter_processo_por_id(process_id_from_form_load if process_id_from_form_load is not None else -1)
            original_process_data = dict(original_process_data_raw) if original_process_data_raw else {}
            data_to_save_dict['DI_ID_Vinculada'] = original_process_data.get('DI_ID_Vinculada')
        else:
            data_to_save_dict['DI_ID_Vinculada'] = None

    # NOVO: Adiciona campos "Consolidado" e "LCL_Processos_Quantidade" ao dicionário para salvar
    if 'Consolidado' in db_col_names_full:
        data_to_save_dict['Consolidado'] = edited_data.get('Consolidado')
    if 'LCL_Processos_Quantidade' in db_col_names_full:
        data_to_save_dict['LCL_Processos_Quantidade'] = edited_data.get('LCL_Processos_Quantidade')

    # Atualiza informações de auditoria
    user_info = st.session_state.get('user_info', {'username': 'Desconhecido'})
    current_username = user_info.get('username', 'Desconhecido')
    data_to_save_dict['Ultima_Alteracao_Por'] = current_username
    data_to_save_dict['Ultima_Alteracao_Em'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Incluir campos de estimativa de impostos no dicionário a ser salvo
    for field in ['Estimativa_Impostos_Total', 'Quantidade_Containers', 'Estimativa_Impostos_BR',
                   'Valor_USD', 'Estimativa_II_BR', 'Estimativa_IPI_BR', 'Estimativa_PIS_BR',
                   'Estimativa_COFINS_BR', 'Estimativa_ICMS_BR',
                   'Nome_do_arquivo', 'Tipo_do_arquivo', 'Conteudo_do_arquivo']: # Adicionado campos de arquivo
        if field in edited_data and field in db_col_names_full:
            # Garante que números sejam salvos como float ou None se NaN
            val = edited_data[field]
            if isinstance(val, (float, int, np.number)):
                data_to_save_dict[field] = float(val) if not pd.isna(val) else None
            else:
                data_to_save_dict[field] = val # Mantém o tipo original se não for numérico

    if 'Processo_Novo' in edited_data and 'Processo_Novo' in db_col_names_full:
        data_to_save_dict['Processo_Novo'] = edited_data['Processo_Novo']
    else:
        logger.warning("Processo_Novo não encontrado nos dados editados.")
        _display_message_box("Erro: O nome do processo não foi fornecido. Não é possível salvar.", "error")
        return None


    success = False
    actual_process_id_after_save: Optional[Any] = None
    original_process_data_for_history = {} # Para coletar dados originais para histórico de forma mais robusta

    # Se for processo existente, carregar dados originais para histórico
    if not is_new_process_flag and process_id_from_form_load is not None:
        original_process_raw = db_manager.obter_processo_por_id(process_id_from_form_load if isinstance(process_id_from_form_load, int) else -1) if not db_manager._USE_FIRESTORE_AS_PRIMARY else db_manager.obter_processo_by_processo_novo(process_id_from_form_load)
        if original_process_raw:
            original_process_data_for_history = dict(original_process_raw)

    try:
        if is_new_process_flag:
            existing_process = db_manager.obter_processo_by_processo_novo(data_to_save_dict['Processo_Novo'])
            if existing_process:
                _display_message_box(f"Falha ao adicionar processo: Já existe um processo com a referência '{data_to_save_dict['Processo_Novo']}'. Por favor, altere a referência do processo clonado.", "error")
                return None
            
            success = db_manager.inserir_processo(data_to_save_dict)
            if success:
                # No Firestore, Processo_Novo é o ID. No SQLite, obtemos o último ID numérico.
                actual_process_id_after_save = data_to_save_dict['Processo_Novo'] if db_manager._USE_FIRESTORE_AS_PRIMARY else db_manager.obter_ultimo_processo_id()
                
                if not actual_process_id_after_save:
                    logger.error("Falha ao obter o ID do novo processo após a inserção (FireStore/SQLite).")
                    success = False
                
                if success:
                    db_type_for_history = "Firestore" if db_manager._USE_FIRESTORE_AS_PRIMARY else "SQLite"
                    db_manager.inserir_historico_processo(
                        actual_process_id_after_save, "Processo Criado", "N/A",
                        data_to_save_dict.get('Processo_Novo', 'Processo Criado'),
                        current_username, db_type=db_type_for_history
                    )
            
        else: # Atualizando processo existente
            success = db_manager.atualizar_processo(process_id_from_form_load, data_to_save_dict)
            actual_process_id_after_save = process_id_from_form_load

            if success and original_process_data_for_history:
                db_type_for_history = "Firestore" if db_manager._USE_FIRESTORE_AS_PRIMARY else "SQLite"
                for field_name, new_value in data_to_save_dict.items():
                    if field_name in ["Ultima_Alteracao_Por", "Ultima_Alteracao_Em"]:
                        continue

                    original_value = original_process_data_for_history.get(field_name)

                    # Normaliza valores para comparação, tratando None e NaN de forma consistente
                    normalized_original = None
                    if original_value is not None and not (isinstance(original_value, (float, np.number)) and pd.isna(original_value)):
                        normalized_original = str(original_value).strip() if isinstance(original_value, str) else original_value
                        # Para datas que podem ser strings
                        if isinstance(normalized_original, str) and field_name.startswith("Data_"):
                            try:
                                normalized_original = datetime.strptime(normalized_original, "%Y-%m-%d").date()
                            except ValueError:
                                pass # Não é uma data válido, mantém como string
                    
                    normalized_new = None
                    if new_value is not None and not (isinstance(new_value, (float, np.number)) and pd.isna(new_value)):
                        normalized_new = str(new_value).strip() if isinstance(new_value, str) else new_value
                        # Para datas que podem ser strings
                        if isinstance(normalized_new, str) and field_name.startswith("Data_"):
                            try:
                                normalized_new = datetime.strptime(normalized_new, "%Y-%m-%d").date()
                            except ValueError:
                                pass # Não é uma data válida, mantém como string


                    if normalized_original != normalized_new:
                        db_manager.inserir_historico_processo(
                            actual_process_id_after_save, field_name,
                            str(original_value) if original_value is not None and not (isinstance(original_value, (float, np.number)) and pd.isna(original_value)) else "Vazio",
                            str(new_value) if new_value is not None and not (isinstance(new_value, (float, np.number)) and pd.isna(new_value)) else "Vazio",
                            current_username, db_type=db_type_for_history
                        )

    except Exception as e:
        logger.exception(f"Erro de banco de dados durante a operação de salvar/atualizar processo.")
        _display_message_box(f"Erro no banco de dados ao salvar processo: {e}", "error")
        success = False

    if success:
        item_process_id_for_db_ops = None
        # Para salvar/deletar itens, usamos o ID do processo recém-salvo/atualizado
        # Que é o Processo_Novo no Firestore, ou o ID numérico no SQLite
        if db_manager._USE_FIRESTORE_AS_PRIMARY:
            item_process_id_for_db_ops = data_to_save_dict.get('Processo_Novo')
            if not item_process_id_for_db_ops: # Fallback se Processo_Novo não foi o ID de retorno
                item_process_id_for_db_ops = actual_process_id_after_save
        else:
            item_process_id_for_db_ops = actual_process_id_after_save

        logger.info(f"[_save_process_action] Processo salvo/atualizado com sucesso. ID do processo para itens: {item_process_id_for_db_ops}")
        
        if item_process_id_for_db_ops is not None:
            # Deleta todos os itens existentes e reinserir, estratégia mais simples por agora.
            # Em uma aplicação de grande escala, considerar delta updates ou UPSERT de itens.
            logger.info(f"[_save_process_action] Tentando deletar itens existentes para o processo ID {item_process_id_for_db_ops}.")
            try:
                db_manager.deletar_itens_processo(processo_id=item_process_id_for_db_ops)
                logger.info(f"[_save_process_action] Itens antigos deletados com sucesso para o processo ID {item_process_id_for_db_ops}.")
            except Exception as e:
                logger.error(f"[_save_process_action] ERRO ao deletar itens antigos para o processo ID {item_process_id_for_db_ops}: {e}")
                _display_message_box(f"Erro ao limpar itens antigos: {e}", "error")
            
            if 'process_items_data' in st.session_state and st.session_state.process_items_data:
                logger.info(f"[_save_process_action] Tentando inserir {len(st.session_state.process_items_data)} novos itens para o processo ID {item_process_id_for_db_ops}.")
                for i, item in enumerate(st.session_state.process_items_data):
                    try:
                        # Garante que os campos numéricos sejam convertidos corretamente para o DB
                        item_to_insert = item.copy()
                        for k_num in ['Quantidade', 'Valor Unitário', 'Valor total do item',
                                      'Estimativa_II_BR', 'Estimativa_IPI_BR', 'Estimativa_PIS_BR',
                                      'Estimativa_COFINS_BR', 'Estimativa_ICMS_BR', 'Frete_Rateado_USD',
                                      'Seguro_Rateado_BRL', 'VLMD_Item']:
                            if k_num in item_to_insert and item_to_insert[k_num] is not None:
                                try:
                                    item_to_insert[k_num] = float(item_to_insert[k_num])
                                except (ValueError, TypeError):
                                    item_to_insert[k_num] = 0.0 # Define um valor padrão se a conversão falhar
                            else:
                                item_to_insert[k_num] = 0.0 # Garante que None ou ausente virem 0.0
                        
                        logger.debug(f"[_save_process_action] Inserindo item {i} para processo ID {item_process_id_for_db_ops}: {item_to_insert}")
                        db_manager.inserir_item_processo(
                            processo_id=item_process_id_for_db_ops,
                            codigo_interno=item_to_insert.get('Código Interno'),
                            ncm=item_to_insert.get('NCM'),
                            cobertura=item_to_insert.get('Cobertura'),
                            sku=item_to_insert.get('SKU'),
                            quantidade=item_to_insert.get('Quantidade'),
                            peso_unitario=0.0,  # Valor padrão já que removemos o campo
                            valor_unitario=item_to_insert.get('Valor Unitário'),
                            valor_total_item=item_to_insert.get('Valor total do item'),
                            estimativa_ii_br=item_to_insert.get('Estimativa_II_BR'),
                            estimativa_ipi_br=item_to_insert.get('Estimativa_IPI_BR'),
                            estimativa_pis_br=item_to_insert.get('Estimativa_PIS_BR'),
                            estimativa_cofins_br=item_to_insert.get('Estimativa_COFINS_BR'),
                            estimativa_icms_br=item_to_insert.get('Estimativa_ICMS_BR'),
                            frete_rateado_usd=item_to_insert.get('Frete_Rateado_USD'),
                            seguro_rateado_brl=item_to_insert.get('Seguro_Rateado_BRL'),
                            vlmd_item=item_to_insert.get('VLMD_Item'),
                            denominacao_produto=item_to_insert.get('Denominação do produto'),
                            detalhamento_complementar_produto=item_to_insert.get('Detalhamento complementar do produto')
                        )
                        logger.debug(f"[_save_process_action] Item {i} inserido com sucesso para processo ID {item_process_id_for_db_ops}.")
                    except Exception as e:
                        logger.error(f"[_save_process_action] ERRO ao inserir item {i} para o processo ID {item_process_id_for_db_ops}: {e}")
                        _display_message_box(f"Erro ao inserir item {item.get('Código Interno', 'N/A')}: {e}", "error")
                logger.info(f"[_save_process_action] Tentativa de inserção de todos os itens concluída.")
            else:
                logger.info(f"[_save_process_action] Nenhum item para salvar em st.session_state.process_items_data para o processo ID {item_process_id_for_db_ops}.")

        # Limpar caches relacionados a itens do processo e aos próprios processos
        db_manager.obter_itens_processo.clear()
        db_manager.obter_historico_processo.clear()
        db_manager.obter_processo_por_id.clear()
        db_manager.obter_processo_by_processo_novo.clear()
        db_manager.obter_processos_filtrados.clear()
        db_manager.obter_todos_processos.clear()
        db_manager.obter_status_gerais_distintos.clear()
        logger.info(f"[_save_process_action] Caches de histórico, processos e itens limpos após salvamento/atualização.")

        _display_message_box(f"Processo {'adicionado' if is_new_process_flag else 'atualizado'} com sucesso!", "success")
        
        # Limpar estados relacionados a itens/upload para uma nova interação do formulário
        st.session_state.show_add_item_popup = False
        st.session_state.last_processed_upload_key = None
        st.session_state.process_items_loaded_for_id = None
        st.session_state.total_invoice_value_usd = 0.0
        st.session_state.total_invoice_weight_kg = 0.0

        # Limpar todos os campos do formulário e estados de sessão relacionados
        if form_state_key in st.session_state:
            del st.session_state[form_state_key] # Remove o estado do formulário
        st.session_state.process_items_data = [] # Limpa a lista de itens
        st.session_state.show_edit_item_popup = False
        st.session_state.item_to_edit_index = None
        st.session_state.selected_item_indices = []
        st.session_state.last_processed_process_upload_key = None # Limpa o upload de dados gerais do processo
        st.session_state.form_is_cloning = False
        st.session_state.last_cloned_from_id = None
        st.session_state.current_loaded_form_key = None # Indica que nenhum formulário está carregado

        return actual_process_id_after_save
    else:
        st.session_state.form_is_cloning = False
        st.session_state.last_cloned_from_id = None
        return None

# --- Esquema Padrão para Itens ---
DEFAULT_ITEM_SCHEMA = {
    "Código Interno": None, "NCM": None, "Cobertura": "SIM", "SKU": None,
    "Quantidade": 0, "Valor Unitário": 0.0,
    "Valor total do item": 0.0, "Estimativa_II_BR": 0.0, "Estimativa_IPI_BR": 0.0,
    "Estimativa_PIS_BR": 0.0, "Estimativa_COFINS_BR": 0.0, "Estimativa_ICMS_BR": 0.0,
    "Frete_Rateado_USD": 0.0, "Seguro_Rateado_BRL": 0.0, "VLMD_Item": 0.0,
    "Denominação do produto": None, "Detalhamento complementar do produto": None,
    "Fornecedor": None, "Invoice N#": None
}

def _standardize_item_data(item_dict: Any, fornecedor: Optional[str] = None, invoice_n: Optional[str] = None) -> Dict[str, Any]:
    """
    Garante que um dicionário de item esteja em conformidade com o esquema padrão.
    Lida com chaves no formato snake_case (do DB) e "Capitalized With Spaces" (do formulário/Excel).
    """
    standardized_item = DEFAULT_ITEM_SCHEMA.copy()
    
    if not isinstance(item_dict, dict):
        logger.warning(f"[_standardize_item_data] Input item_dict não é um dicionário: {type(item_dict)}. Retornando esquema padrão.")
        standardized_item['Fornecedor'] = fornecedor
        standardized_item['Invoice N#'] = invoice_n
        return standardized_item

    # Mapeamento de chaves snake_case do DB para chaves 'Capitalized With Spaces' do schema/display
    db_to_schema_map = {
        "codigo_interno": "Código Interno", "ncm": "NCM", "cobertura": "Cobertura", "sku": "SKU",
        "quantidade": "Quantidade", "valor_unitario": "Valor Unitário",
        "valor_total_item": "Valor total do item", "estimativa_ii_br": "Estimativa_II_BR",
        "estimativa_ipi_br": "Estimativa_IPI_BR", "estimativa_pis_br": "Estimativa_PIS_BR",
        "estimativa_cofins_br": "Estimativa_COFINS_BR", "estimativa_icms_br": "Estimativa_ICMS_BR",
        "frete_rateado_usd": "Frete_Rateado_USD", "seguro_rateado_brl": "Seguro_Rateado_BRL",
        "vlmd_item": "VLMD_Item", "denominacao_produto": "Denominação do produto",
        "detalhamento_complementar_produto": "Detalhamento complementar do produto",
    }

    # Primeiro, preencher com valores do item_dict usando o mapeamento para campos do DB
    for db_key, schema_key in db_to_schema_map.items():
        if db_key in item_dict:
            standardized_item[schema_key] = item_dict[db_key]
        elif schema_key in item_dict:
             standardized_item[schema_key] = item_dict[schema_key]

    # Campos que podem vir diretamente sem mapeamento
    for key in DEFAULT_ITEM_SCHEMA.keys():
        if key not in standardized_item and key in item_dict:
            standardized_item[key] = item_dict[key]

    # Converte tipos para garantir compatibilidade
    for k, v in standardized_item.items():
        if k in ["Quantidade"]:
            # Converte para numérico, se for NaN, vira 0, então para int
            numeric_val = pd.to_numeric(v, errors='coerce')
            standardized_item[k] = int(numeric_val if not pd.isna(numeric_val) else 0)
        elif k in ["Valor Unitário", "Valor total do item",
                   "Estimativa_II_BR", "Estimativa_IPI_BR", "Estimativa_PIS_BR",
                   "Estimativa_COFINS_BR", "Estimativa_ICMS_BR", "Frete_Rateado_USD",
                   "Seguro_Rateado_BRL", "VLMD_Item"]:
            # Converte para numérico, se for NaN, vira 0.0, então para float
            numeric_val = pd.to_numeric(v, errors='coerce')
            standardized_item[k] = float(numeric_val if not pd.isna(numeric_val) else 0.0)
        elif isinstance(v, str) and v.strip() == '':
            standardized_item[k] = None # Converte strings vazias para None
    
    return standardized_item

def _extract_items_from_excel_or_csv(uploaded_file: Any) -> List[Dict[str, Any]]:
    """
    Extrai dados de itens de uma tabela em um arquivo Excel (.xlsx) ou CSV.
    Adapta a leitura com base na extensão do arquivo.
    """
    items_from_file = []
    if uploaded_file is None:
        return items_from_file

    try:
        file_extension = os.path.splitext(uploaded_file.name)[1].lower()
        df = None

        if file_extension == '.csv':
            # Para CSV, assume que o cabeçalho está na primeira linha (index 0)
            df = pd.read_csv(uploaded_file, sep=',', quotechar='"', dtype=str)
        elif file_extension == '.xlsx':
            # Para XLSX, tenta ler o cabeçalho a partir da 7ª linha (index 6)
            df = pd.read_excel(uploaded_file, header=6, dtype=str) 
        else:
            _display_message_box("Formato de arquivo não suportado. Por favor, faça upload de um arquivo CSV ou XLSX.", "error")
            return items_from_file

        # Limpar nomes das colunas: remover quebras de linha e espaços extras
        # Garante que 'col' é uma string antes de chamar replace()
        df.columns = [str(col).replace('\n', ' ').strip() if col is not None else '' for col in df.columns]

        # Mapeamento dos cabeçalhos do arquivo para as chaves internas
        col_mapping_keywords = {
            "Código Interno": ["Código"],
            "SKU": ["Cód.Fabricante"],
            "Quantidade": ["Quant. Und", "Quant."], 
            "Denominação do produto": ["Descrição"],
            "NCM": ["NCM"],
            "Valor Unitário": ["Valor Unit."],
        }

        # Encontra os nomes reais das colunas no DataFrame
        col_names_in_df = {}
        for internal_key, keywords in col_mapping_keywords.items():
            found_col = None
            for keyword in keywords:
                # Procura por correspondência exata ou parcial (contém)
                matching_cols = [col for col in df.columns if keyword.lower() in col.lower()]
                if matching_cols:
                    found_col = matching_cols[0] 
                    break
            col_names_in_df[internal_key] = found_col
        
        # Verifica se todas as colunas essenciais foram encontradas
        essential_cols = ["Código Interno", "SKU", "Quantidade", "Denominação do produto", "NCM", "Valor Unitário"]
        if any(col_names_in_df[key] is None for key in essential_cols):
            logger.warning(f"Cabeçalhos essenciais não encontrados no arquivo. Ignorando. Colunas encontradas: {df.columns.tolist()}")
            _display_message_box("Não foi possível encontrar todas as colunas essenciais no arquivo. Verifique o formato do cabeçalho.", "error")
            return items_from_file

        # Iterar sobre as linhas do DataFrame
        for index, row in df.iterrows():
            item_data = {}
            
            # Extrai os dados usando os nomes das colunas mapeados, tratando None
            # Garante que os valores da linha são strings antes de processar
            item_data["Código Interno"] = str(row[col_names_in_df["Código Interno"]]) if col_names_in_df["Código Interno"] and pd.notna(row[col_names_in_df["Código Interno"]]) else None
            item_data["SKU"] = str(row[col_names_in_df["SKU"]]) if col_names_in_df["SKU"] and pd.notna(row[col_names_in_df["SKU"]]) else None
            item_data["Quantidade"] = str(row[col_names_in_df["Quantidade"]]) if col_names_in_df["Quantidade"] and pd.notna(row[col_names_in_df["Quantidade"]]) else None
            item_data["Denominação do produto"] = str(row[col_names_in_df["Denominação do produto"]]) if col_names_in_df["Denominação do produto"] and pd.notna(row[col_names_in_df["Denominação do produto"]]) else None
            item_data["NCM"] = str(row[col_names_in_df["NCM"]]) if col_names_in_df["NCM"] and pd.notna(row[col_names_in_df["NCM"]]) else None
            
            # Para "Valor Unitário", extrair o primeiro número float da string
            raw_valor_unitario = str(row[col_names_in_df["Valor Unitário"]]) if col_names_in_df["Valor Unitário"] and pd.notna(row[col_names_in_df["Valor Unitário"]]) else None
            if raw_valor_unitario:
                # Usa regex para encontrar o primeiro número que pode ter vírgula como separador decimal
                match = re.search(r'(\d[\d,.]*)', raw_valor_unitario)
                if match:
                    # Substitui vírgula por ponto e converte para float
                    item_data["Valor Unitário"] = float(match.group(1).replace(',', '.'))
                else:
                    item_data["Valor Unitário"] = 0.0
            else:
                item_data["Valor Unitário"] = 0.0

            # Limpeza e conversão de tipos para os demais campos
            # Quantidade: remover não-dígitos e converter para int
            item_data["Quantidade"] = int(re.sub(r'\D', '', str(item_data["Quantidade"]))) if item_data["Quantidade"] else 0
            # NCM: remover não-dígitos
            item_data["NCM"] = re.sub(r'\D', '', str(item_data["NCM"])) if item_data["NCM"] else None
            
            # --- Automação da busca de NCM/Descrição ---
            if item_data.get('NCM'):
                ncm_info = db_utils.get_ncm_item_by_ncm_code(item_data['NCM'])
                if ncm_info:
                    item_data['Denominação do produto'] = ncm_info.get('descricao_item', item_data.get('Denominação do produto'))
            elif item_data.get('Denominação do produto'):
                ncm_info_by_desc = db_utils.search_ncm_by_description(item_data['Denominação do produto'])
                if ncm_info_by_desc:
                    item_data['NCM'] = ncm_info_by_desc.get('ncm_code', item_data.get('NCM'))
                    item_data['Denominação do produto'] = ncm_info_by_desc.get('descricao_item', item_data.get('Denominação do produto'))

            # Padroniza o item com o esquema padrão
            standardized_item = _standardize_item_data(item_data)
            standardized_item["Valor total do item"] = standardized_item["Quantidade"] * standardized_item["Valor Unitário"]
            
            # NOVO: Filtrar itens que não são produtos reais
            # Critérios de filtragem:
            # 1. Código Interno não pode ser "Pedido de Compra" (case-insensitive)
            # 2. Quantidade deve ser maior que 0
            if standardized_item["Código Interno"] and \
               "pedido de compra" not in standardized_item["Código Interno"].lower() and \
               standardized_item["Quantidade"] > 0:
                items_from_file.append(standardized_item)
            else:
                logger.warning(f"Item filtrado (não é um produto válido): {standardized_item}")

        _display_message_box(f"Total de {len(items_from_file)} itens extraídos do arquivo.", "success")
    except Exception as e:
        _display_message_box(f"Erro ao extrair itens do arquivo: {e}", "error")
        logger.exception("Erro durante a extração de itens do arquivo.")
    
    return items_from_file


# Mover a definição de campos_config_tabs para fora da função show_process_form_page
# para garantir que ela esteja sempre definida e acessível.
campos_config_tabs = {
    "Dados Gerais": {
        "col1": {
            "Processo_Novo": {"label": "Processo:", "type": "text", "icon": "📦"}, # Ícone adicionado
            "Fornecedor": {"label": "Fornecedor:", "type": "text", "icon": "🏢"}, # Ícone adicionado
            "Tipos_de_item": {"label": "Tipos de item:", "type": "text", "icon": "📝"}, # Ícone adicionado
            "N_Invoice": {"label": "Nº Invoice:", "type": "text", "icon": "📄"}, # Ícone adicionado
            "Quantidade": {"label": "Quantidade:", "type": "number", "icon": "🔢"}, # Ícone adicionado
            "N_Ordem_Compra": {"label": "Nº da Ordem de Compra:", "type": "text", "icon": "🛒"}, # Ícone adicionado
            "Agente_de_Carga_Novo": {"label": "Agente de Carga:", "type": "text", "icon": "�‍✈️"}, # Ícone adicionado
            "Origem": {"label": "Origem:", "type": "text", "icon": "🌍"}, # Ícone adicionado
            "Destino": {"label": "Destino:", "type": "text", "icon": "📍"}, # Ícone adicionado
            "Comprador": {"label": "Comprador:", "type": "text", "icon": "👤"}, # Ícone adicionado
        },
        "col2": {
            "Modal": {"label": "Modal:", "type": "dropdown", "values": ["", "Aéreo", "Maritimo", "Consolidado"], "on_change": True, "icon": "✈️🚢"}, # Ícone adicionado
            "Navio": {"label": "Navio:", "type": "text", "conditional_field": "Modal", "conditional_value": "Maritimo", "icon": "🚢"}, # Ícone adicionado
            "Quantidade_Containers": {"label": "Quantidade de Containers:", "type": "number", "conditional_field": "Modal", "conditional_value": "Maritimo", "icon": "📦"}, # Ícone adicionado
            "Consolidado": {"label": "Consolidado?:", "type": "dropdown", "values": ["", "Sim", "Não"], "conditional_field": "Modal", "conditional_value": "Consolidado", "on_change": True, "icon": "🔗"}, # Ícone adicionado
            "LCL_Processos_Quantidade": {"label": "Quantos processos - LCL:", "type": "number", "conditional_field": "Consolidado", "conditional_value": "Sim", "min_value": 0, "max_value": 30, "format": "%d", "icon": "🔢"}, # Ícone adicionado
            "INCOTERM": {"label": "INCOTERM:", "type": "dropdown", "values": ["","EXW","FCA","FAS","FOB","CFR","CIF","CPT","CIP","DPU","DAP","DDP"], "icon": "🤝"}, # Ícone adicionado
            "Pago": {"label": "Pago?:", "type": "dropdown", "values": ["Não", "Sim"], "icon": "💸"}, # Ícone adicionado
            "Data_Compra": {"label": "Data de Compra:", "type": "date", "icon": "📅"}, # Ícone adicionado
            "Data_Embarque": {"label": "Data de Embarque:", "type": "date", "icon": "🗓️"}, # Ícone adicionado
            "ETA_Recinto": {"label": "ETA no Recinto:", "type": "date", "icon": "🗓️"}, # Ícone adicionado
            "Previsao_Pichau": {"label": "Previsão na Pichau:", "type": "date", "icon": "🗓️"}, # Ícone adicionado
            "Status_Geral": {"label": "Status Geral (para e-mail):", "type": "dropdown", "values": db_manager.STATUS_OPTIONS, "icon": "🚦"}, # Ícone adicionado
        }
    },
    "Itens": {},
    "Valores e Estimativas": {
        "Estimativa_Dolar_BRL": {"label": "Cambio Estimado (R$):", "type": "currency_br", "icon": "💵"}, # Ícone adicionado
        "Valor_USD": {"label": "Valor (USD):", "type": "currency_usd", "disabled": True, "icon": "💲"}, # Ícone adicionado
        "Estimativa_Frete_USD": {"label": "Estimativa de Frete (USD):", "type": "currency_usd", "icon": "🚚"}, # Ícone adicionado
        "Estimativa_Seguro_BRL": {"label": "Estimativa Seguro (R$):", "type": "currency_br", "icon": "🛡️"}, # Ícone adicionado
        "Estimativa_II_BR": {"label": "Estimativa de II (R$):", "type": "currency_br", "disabled": True, "icon": "💰"}, # Ícone adicionado
        "Estimativa_IPI_BR": {"label": "Estimativa de IPI (R$):", "type": "currency_br", "disabled": True, "icon": "💰"}, # Ícone adicionado
        "Estimativa_PIS_BR": {"label": "Estimativa de PIS (R$):", "type": "currency_br", "disabled": True, "icon": "💰"}, # Ícone adicionado
        "Estimativa_COFINS_BR": {"label": "Estimativa de COFINS (R$):", "type": "currency_br", "disabled": True, "icon": "💰"}, # Ícone adicionado
        "Estimativa_ICMS_BR": {"label": "Estimativa de ICMS (R$):", "type": "currency_br", "icon": "💰"}, # Ícone adicionado
        "Estimativa_Impostos_Total": {"label": "Estimativa Impostos (R$):", "type": "currency_br", "disabled": True, "icon": "📊"}, # Ícone adicionado
        "Estimativa_Impostos_BR": {"label": "Estimativa Impostos (Antigo):", "type": "currency_br", "disabled": True, "icon": "👴"}, # Ícone adicionado
    },
    "Status Operacional": {
        # Campos de status operacional movidos para "Dados Gerais" ou mantidos aqui se forem muito específicos.
        # "Data_Registro": {"label": "Data de Registro:", "type": "date"}, # Movido para Dados Gerais
        "Documentos_Revisados": {"label": "Documentos Revisados:", "type": "dropdown", "values": ["Não", "Sim"], "icon": "✅"}, # Ícone adicionado
        "Conhecimento_Embarque": {"label": "Conhecimento de embarque:", "type": "dropdown", "values": ["Não", "Sim"], "icon": "📄"}, # Ícone adicionado
        "Descricao_Feita": {"label": "Descrição Feita:", "type": "dropdown", "values": ["Não", "Sim"], "icon": "✍️"}, # Ícone adicionado
        "Descricao_Enviada": {"label": "Descrição Enviada:", "type": "dropdown", "values": ["Não", "Sim"], "icon": "✉️"}, # Ícone adicionado
        "Nota_feita": {"label": "Nota feita?:", "type": "dropdown", "values": ["Não", "Sim"], "icon": "📝"}, # Ícone adicionado
        "Conferido": {"label": "Conferido?:", "type": "dropdown", "values": ["Não", "Sim"], "icon": "✔️"}, # Ícone adicionado
    }
}

# Callback para forçar o rerun quando o Modal muda e afetar campos condicionais
def _on_modal_change_rerun():
    # Removido st.rerun() para evitar "no-op" warning. Streamlit re-executa ao mudar session_state.
    pass 

def _on_consolidado_change_rerun():
    # Removido st.rerun() para evitar "no-op" warning. Streamlit re-executa ao mudar session_state.
    pass


def _initialize_form_state(form_state_key: str, process_identifier: Optional[Any], is_cloning: bool):
    """Inicializa ou reinicializa o estado do formulário na session_state."""
    # Define a chave de carregamento para saber se os itens já foram carregados para este processo
    st.session_state.current_loaded_form_key = form_state_key
    st.session_state[f'{form_state_key}_is_new_process_flag'] = process_identifier is None or is_cloning
    
    process_data = {}
    items_loaded_successfully = False

    # Carregar dados do processo
    if not (process_identifier is None or is_cloning): # Editando um processo existente
        raw_data = db_manager.obter_processo_por_id(process_identifier) if isinstance(process_identifier, int) else db_manager.obter_processo_by_processo_novo(process_identifier)
        if raw_data:
            process_data = dict(raw_data)
        else:
            _display_message_box(f"Processo '{process_identifier}' não encontrado para edição.", "error")
            st.session_state.current_page = "Follow-up Importação"
            st.rerun()
            return {} # Retorna dicionário vazio em caso de erro

    # Lógica de clonagem
    if is_cloning and process_identifier is not None:
        raw_data = db_manager.obter_processo_por_id(process_identifier) if isinstance(process_identifier, int) else db_manager.obter_processo_by_processo_novo(process_identifier)
        if raw_data:
            process_data = dict(raw_data)
            cloned_process_novo = f"{process_data.get('Processo_Novo', 'NovoProcesso')}_Clone_{datetime.now().strftime('%H%M%S')}"
            process_data['Processo_Novo'] = cloned_process_novo # Altera para o nome clonado
            process_data['id'] = None # Garante que é um novo registro no DB
            # Limpa campos de auditoria para o clone
            process_data['Ultima_Alteracao_Por'] = None
            process_data['Ultima_Alteracao_Em'] = None
            # Os dados do arquivo não devem ser clonados, já que o arquivo é único por processo.
            process_data['Nome_do_arquivo'] = None
            process_data['Tipo_do_arquivo'] = None
            process_data['Conteudo_do_arquivo'] = None
            _display_message_box(f"Processo clonado de '{process_data.get('Processo_Novo', 'N/A')}' com sucesso. Por favor, edite a referência do novo processo.", "success")
        else:
            _display_message_box(f"Processo '{process_identifier}' não encontrado para clonagem.", "error")
            st.session_state.current_page = "Follow-up Importação"
            st.rerun()
            return {} # Retorna dicionário vazio em caso de erro
    
    # Preenche st.session_state[form_state_key] com os dados carregados ou padrões
    st.session_state[form_state_key] = {}
    
    # Itera sobre todas as configurações de campos e inicializa os valores
    for tab_name, tab_config in campos_config_tabs.items():
        if "col1" in tab_config:
            for field_name, config in tab_config["col1"].items():
                st.session_state[form_state_key][field_name] = process_data.get(field_name)
        if "col2" in tab_config:
            for field_name, config in tab_config["col2"].items():
                st.session_state[form_state_key][field_name] = process_data.get(field_name)
        # Para tabs que não têm colunas internas (como Valores e Estimativas, Status Operacional, Documentação)
        if tab_name not in ["Dados Gerais", "Itens"]: # Exclui "Dados Gerais" e "Itens" para evitar double-initialization
            for field_name, config in tab_config.items():
                # Define um valor padrão para campos numéricos se o valor carregado for None ou pd.isna
                if config["type"] == "number":
                    st.session_state[form_state_key][field_name] = process_data.get(field_name, 0) if (process_data.get(field_name) is not None and not pd.isna(process_data.get(field_name))) else 0
                elif config["type"] == "currency_br" or config["type"] == "currency_usd":
                    # Tratamento especial para Estimativa_Dolar_BRL - usar PTAX Venda como padrão
                    if field_name == "Estimativa_Dolar_BRL":
                        db_value = process_data.get(field_name)
                        if db_value is not None and not pd.isna(db_value) and db_value != 0.0:
                            st.session_state[form_state_key][field_name] = db_value
                            logger.info(f"[_initialize_form_state] Usando valor do banco para {field_name}: {db_value}")
                        else:
                            ptax_value = get_current_dolar_ptax_venda()
                            st.session_state[form_state_key][field_name] = ptax_value
                            logger.info(f"[_initialize_form_state] Usando PTAX Venda para {field_name}: {ptax_value}")
                    else:
                        st.session_state[form_state_key][field_name] = process_data.get(field_name, 0.0) if (process_data.get(field_name) is not None and not pd.isna(process_data.get(field_name))) else 0.0
                else:
                    st.session_state[form_state_key][field_name] = process_data.get(field_name)

    st.session_state[form_state_key]["Observacao"] = process_data.get("Observacao", "")

    # Define valores padrão para campos específicos se for clonagem ou novo processo
    if is_cloning or (process_identifier is None):
        # Campos que devem ter um valor inicial padrão para novos/clones,
        # se ainda não foram preenchidos acima pela lógica de process_data.get()
        st.session_state[form_state_key].update({
            "Quantidade": st.session_state[form_state_key].get("Quantidade", 0), 
            "Quantidade_Containers": st.session_state[form_state_key].get("Quantidade_Containers", 0),
            "Consolidado": st.session_state[form_state_key].get("Consolidado", ""),            
            "LCL_Processos_Quantidade": st.session_state[form_state_key].get("LCL_Processos_Quantidade", 0),            
            "Modal": st.session_state[form_state_key].get("Modal", ""),
            "INCOTERM": st.session_state[form_state_key].get("INCOTERM", ""), 
            "Pago": st.session_state[form_state_key].get("Pago", "Não"), 
            "Data_Compra": st.session_state[form_state_key].get("Data_Compra", None), 
            "Data_Embarque": st.session_state[form_state_key].get("Data_Embarque", None), 
            "ETA_Recinto": st.session_state[form_state_key].get("ETA_Recinto", None), 
            "Previsao_Pichau": st.session_state[form_state_key].get("Previsao_Pichau", None),
            "Status_Geral": st.session_state[form_state_key].get("Status_Geral", ""), 
            "DI_ID_Vinculada": st.session_state[form_state_key].get("DI_ID_Vinculada", None), 
            "Estimativa_Impostos_Total": st.session_state[form_state_key].get("Estimativa_Impostos_Total", 0.0), 
            "Estimativa_Impostos_BR": st.session_state[form_state_key].get("Estimativa_Impostos_BR", 0.0),
            "Estimativa_Dolar_BRL": st.session_state[form_state_key].get("Estimativa_Dolar_BRL", get_current_dolar_ptax_venda()), 
            "Valor_USD": st.session_state[form_state_key].get("Valor_USD", 0.0), 
            "Estimativa_Frete_USD": st.session_state[form_state_key].get("Estimativa_Frete_USD", 0.0), 
            "Estimativa_Seguro_BRL": st.session_state[form_state_key].get("Estimativa_Seguro_BRL", 0.0), 
            "Estimativa_II_BR": st.session_state[form_state_key].get("Estimativa_II_BR", 0.0), 
            "Estimativa_IPI_BR": st.session_state[form_state_key].get("Estimativa_IPI_BR", 0.0), 
            "Estimativa_PIS_BR": st.session_state[form_state_key].get("Estimativa_PIS_BR", 0.0), 
            "Estimativa_COFINS_BR": st.session_state[form_state_key].get("Estimativa_COFINS_BR", 0.0), 
            "Estimativa_ICMS_BR": st.session_state[form_state_key].get("Estimativa_ICMS_BR", 0.0)
        })

    # Carregamento de itens do processo
    process_id_for_items_load = process_data.get('id') # ID numérico para SQLite
    if db_manager._USE_FIRESTORE_AS_PRIMARY:
        process_id_for_items_load = process_data.get('Processo_Novo') # Processo_Novo para Firestore

    # Carrega itens apenas se o ID for válido e os itens ainda não foram carregados para este processo
    if process_id_for_items_load is not None and (st.session_state.get('process_items_loaded_for_id') != process_id_for_items_load or not st.session_state.get('process_items_data')):
        logger.info(f"[_initialize_form_state] Recarregando itens para processo ID: {process_id_for_items_load} (type: {type(process_id_for_items_load)})")
        retrieved_items = db_manager.obter_itens_processo(process_id_for_items_load)
        st.session_state.process_items_data = [
            _standardize_item_data(dict(row), process_data.get("Fornecedor"), process_data.get("N_Invoice")) 
            for row in retrieved_items
        ]
        logger.info(f"[_initialize_form_state] Obtidos {len(st.session_state.process_items_data)} itens após recarregar para ID: {process_id_for_items_load}.")
        st.session_state.process_items_loaded_for_id = process_id_for_items_load
        items_loaded_successfully = True
    elif process_identifier is None and not is_cloning: # Novo processo, sem itens
        st.session_state.process_items_data = []
        st.session_state.process_items_loaded_for_id = None
        items_loaded_successfully = True
    else: # Itens já carregados para este ID ou ID é None (clonagem inicial)
        if is_cloning and not st.session_state.get('process_items_data'): # Se é clone, e itens não foram preenchidos
             # Isso é tratado na clonagem, onde process_items_data é preenchido manualmente.
             pass
        elif not st.session_state.get('process_items_data'): # Caso não seja clone nem edição, e os dados estejam vazios
             st.session_state.process_items_data = []
        items_loaded_successfully = True # Considera que o estado atual dos itens está ok.

    # Garante que total_invoice_value_usd e total_invoice_weight_kg são calculados ao inicializar
    if items_loaded_successfully and st.session_state.get('process_items_data'):
        df_items_calc = pd.DataFrame(st.session_state.process_items_data)
        st.session_state.total_invoice_value_usd = df_items_calc["Valor total do item"].sum() if "Valor total do item" in df_items_calc.columns else 0.0
        
        # Como removemos Peso Unitário, definimos um peso padrão baseado no valor
        # ou simplesmente 1.0 por item para manter a funcionalidade
        total_invoice_weight_kg_calc = len(st.session_state.process_items_data) * 1.0 if st.session_state.process_items_data else 0.0
        st.session_state.total_invoice_weight_kg = total_invoice_weight_kg_calc
        
        # NOVO: Recalcula impostos de todos os itens com alíquotas atualizadas do Firestore
        # Isso garante que mesmo itens carregados do banco tenham impostos atualizados
        logger.info(f"[_initialize_form_state] Recalculando impostos para {len(st.session_state.process_items_data)} itens carregados")
        
        dolar_brl = st.session_state[form_state_key].get("Estimativa_Dolar_BRL", get_current_dolar_ptax_venda())
        frete_usd = st.session_state[form_state_key].get("Estimativa_Frete_USD", 0.0)
        seguro_brl = st.session_state[form_state_key].get("Estimativa_Seguro_BRL", 0.0)
        
        # Recalcula impostos para todos os itens carregados
        total_ii = total_ipi = total_pis = total_cofins = total_icms = 0.0
        for item in st.session_state.process_items_data:
            calculate_item_taxes_and_values(
                item, dolar_brl, st.session_state.total_invoice_value_usd, 
                st.session_state.total_invoice_weight_kg, frete_usd, seguro_brl
            )
            # Soma os impostos recalculados
            total_ii += item.get('Estimativa_II_BR', 0.0)
            total_ipi += item.get('Estimativa_IPI_BR', 0.0)
            total_pis += item.get('Estimativa_PIS_BR', 0.0)
            total_cofins += item.get('Estimativa_COFINS_BR', 0.0)
            total_icms += item.get('Estimativa_ICMS_BR', 0.0)
        
        # Atualiza os totais no formulário com os valores recalculados
        st.session_state[form_state_key]['Estimativa_II_BR'] = total_ii
        st.session_state[form_state_key]['Estimativa_IPI_BR'] = total_ipi
        st.session_state[form_state_key]['Estimativa_PIS_BR'] = total_pis
        st.session_state[form_state_key]['Estimativa_COFINS_BR'] = total_cofins
        st.session_state[form_state_key]['Estimativa_ICMS_BR'] = total_icms
        st.session_state[form_state_key]['Estimativa_Impostos_Total'] = total_ii + total_ipi + total_pis + total_cofins + total_icms
        
        logger.info(f"[_initialize_form_state] Impostos recalculados: II=R${total_ii:.2f}, IPI=R${total_ipi:.2f}, PIS=R${total_pis:.2f}, COFINS=R${total_cofins:.2f}, ICMS=R${total_icms:.2f}")
    else:
        st.session_state.total_invoice_value_usd = 0.0
        st.session_state.total_invoice_weight_kg = 0.0

    return process_data # Retorna process_data para uso no display (importante para process_novo, etc.)

def show_process_form_page(process_identifier: Optional[Any] = None, reload_processes_callback: Optional[callable] = None, is_cloning: bool = False):
    """
    Exibe o formulário de edição/criação de processo em uma página dedicada.
    process_identifier: ID (int) ou Processo_Novo (str) do processo a ser editado. None para novo processo.
    reload_processes_callback: Função para chamar na página principal para recarregar os dados.
    is_cloning: Se True, indica que a operação é de clonagem.
    """
    background_image_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'assets', 'logo_navio_atracado.png')
    set_background_image(background_image_path)

    # Adiciona um pouco de espaço e estilo para a interface principal
    st.markdown("""
    <style>
        .main-header {
            margin-top: 0;
            padding-top: 0;
            text-align: center;
        }
        .tab-content {
            padding: 1rem;
            margin-top: 0.5rem;
        }
        .streamlit-expanderHeader {
            font-size: 1.1rem;
            font-weight: 600;
        }
        div[data-testid="stForm"] {
            border: 1px solid #f0f2f6;
            border-radius: 0.5rem;
            padding: 1rem;
            margin-top: 1rem;
        }
        div.stButton > button {
            width: 100%;
            border-radius: 0.5rem; /* Adicionado para botões */
            padding: 0.75rem; /* Adicionado padding para botões */
            font-size: 1rem; /* Adicionado tamanho da fonte para botões */
            font-weight: 600; /* Adicionado peso da fonte para botões */
        }
        /* Estilos para as caixas de mensagem (info, warning, error, success) */
        div[data-testid="stAlert"] {
            border-radius: 0.5rem;
            padding: 1rem;
            margin-bottom: 1rem;
        }
        div[data-testid="stAlert"].stAlert-info {
            background-color: rgba(33, 150, 243, 0.1); /* Azul claro */
            border-left: 5px solid #2196F3;
        }
        div[data-testid="stAlert"].stAlert-warning {
            background-color: rgba(255, 193, 7, 0.1); /* Amarelo claro */
            border-left: 5px solid #FFC107;
        }
        div[data-testid="stAlert"].stAlert-error {
            background-color: rgba(244, 67, 54, 0.1); /* Vermelho claro */
            border-left: 5px solid #F44336;
        }
        div[data-testid="stAlert"].stAlert-success {
            background-color: rgba(76, 175, 80, 0.1); /* Verde claro */
            border-left: 5px solid #4CAF50;
        }
        .observation-container {
            background-color: #f8f9fa; /* Fundo claro para o container de observação */
            border-radius: 0.5rem;
            padding: 1rem;
            margin-bottom: 1rem;
            border: 1px solid #e0e0e0; /* Borda sutil */
        }
        .observation-title {
            font-size: 1.1rem;
            font-weight: 600;
            margin-bottom: 0.75rem;
            color: #333; /* Cor mais escura para o título */
        }
        /* Estilo para inputs de texto e números */
        div[data-testid="stTextInput"] > div > input,
        div[data-testid="stNumberInput"] > div > input,
        div[data-testid="stDateInput"] > div > input,
        div[data-testid="stSelectbox"] > div > button {
            border-radius: 0.5rem;
            border: 1px solid #ced4da;
            padding: 0.5rem 0.75rem;
        }
        /* Estilo para text area */
        div[data-testid="stTextArea"] > div > textarea {
            border-radius: 0.5rem;
            border: 1px solid #ced4da;
            padding: 0.5rem 0.75rem;
        }
        /* Estilos para o cabeçalho dinâmico */
        .header-new-process {
            background-color: #d4edda; /* Verde claro */
            color: #155724; /* Verde escuro */
            padding: 10px;
            border-radius: 8px;
            text-align: center;
            margin-bottom: 20px;
            font-size: 1.5rem;
            font-weight: bold;
            border: 1px solid #c3e6cb;
        }
        .header-edit-process {
            background-color: #ffeeba; /* Amarelo claro */
            color: #856404; /* Amarelo escuro */
            padding: 10px;
            border-radius: 8px;
            text-align: center;
            margin-bottom: 20px;
            font-size: 1.5rem;
            font-weight: bold;
            border: 1px solid #ffdf7e;
        }
        /* Estilo para os cards de itens */
        .item-card {
            background-color: #f0f2f6; /* Cor de fundo suave */
            border-radius: 0.5rem;
            padding: 1rem;
            margin-bottom: 1rem;
            border: 1px solid #e0e0e0;
        }
        .item-card-header {
            font-size: 1.2rem;
            font-weight: bold;
            margin-bottom: 0.5rem;
            color: #333;
        }
        /* Estilos para tornar a interface de itens mais compacta */
        div[data-testid="stAppViewContainer"] .item-section {
            margin-bottom:  1rem;
        }
        div[data-testid="stAppViewContainer"] .item-section h4 {
            margin-bottom: 0.5rem;
            font-size: 1.1rem;
        }
        div[data-testid="stAppViewContainer"] .item-section h5 {
            margin-bottom: 0.3rem;
            font-size: 1rem;
        }
        /* Compactar campos de formulário na seção de itens */
        div[data-testid="stAppViewContainer"] .item-detail-form .stTextInput > div,
        div[data-testid="stAppViewContainer"] .item-detail-form .stNumberInput > div,
        div[data-testid="stAppViewContainer"] .item-detail-form .stSelectbox > div,
        div[data-testid="stAppViewContainer"] .item-detail-form .stTextArea > div {
            margin-bottom: 0.5rem;
        }
        /* Compactar labels dos campos */
        div[data-testid="stAppViewContainer"] .item-detail-form label {
            font-size: 0.9rem;
            font-weight: 500;
            margin-bottom: 0.2rem;
        }
        /* Compactar radio buttons na lista de itens */
        div[data-testid="stAppViewContainer"] .item-list-radio .stRadio > div {
            gap: 0.3rem;
        }
        div[data-testid="stAppViewContainer"] .item-list-radio .stRadio label {
            font-size: 0.85rem;
            line-height: 1.2;
        }
        /* Compactar informações de impostos */
        div[data-testid="stAppViewContainer"] .tax-info {
            font-size: 0.85rem;
            line-height: 1.3;
            margin-bottom: 0.2rem;
        }
        /* Compactar botões na seção de itens */
        div[data-testid="stAppViewContainer"] .item-buttons .stButton > button {
            padding: 0.4rem 0.8rem;
            font-size: 0.9rem;
            margin-bottom: 0.3rem;
        }
    </style>
    """, unsafe_allow_html=True)

    if reload_processes_callback:
        st.session_state.form_reload_processes_callback = reload_processes_callback

    # Sempre inicialize process_items_data e process_items_loaded_for_id no início da função
    st.session_state.setdefault('process_items_data', [])
    st.session_state.setdefault('process_items_loaded_for_id', None)
    # NOVO: Inicializa o item selecionado para edição detalhada
    st.session_state.setdefault('selected_item_for_detail_edit', None)

    # Flag para saber se estamos em um "novo" processo (inclui clones)
    is_new_process = process_identifier is None or is_cloning

    # Gerenciamento de estado do formulário para evitar recargas desnecessárias e manter dados
    form_state_id_key_base = process_identifier if not is_cloning else f"new_clone_from_{process_identifier}"
    if process_identifier is None and not is_cloning:
        form_state_id_key_base = 'new_empty_process_form_instance'
    form_state_key = f"form_fields_process_{form_state_id_key_base}"

    # Inicializa o estado do formulário SOMENTE se estivermos carregando um processo diferente
    # ou se for um novo processo/clone que ainda não foi inicializado/processado.
    if (form_state_key not in st.session_state or 
        st.session_state.get('current_loaded_form_key') != form_state_key or
        (is_cloning and st.session_state.get(f'{form_state_key}_is_new_process_flag', False) and not st.session_state.get('process_items_data'))
        ): # Adiciona verificação de itens para clones
        
        logger.info(f"[show_process_form_page] Inicializando estado do formulário para key: {form_state_key}, process_id: {process_identifier}, is_cloning: {is_cloning}")
        process_data_from_init = _initialize_form_state(form_state_key, process_identifier, is_cloning)
        if is_cloning and not process_data_from_init and process_identifier is not None: 
            return # Sai da função, já exibe mensagem e reruns dentro de _initialize_form_state

    # Se estamos editando, garantir que process_id seja o ID real do processo
    process_id: Optional[Any] = None
    if not is_new_process and process_identifier is not None:
        if db_manager._USE_FIRESTORE_AS_PRIMARY:
            # No Firestore, o process_identifier já pode ser o Processo_Novo (string)
            process_id = process_identifier 
        else: # SQLite
            if isinstance(process_identifier, int):
                process_id = process_identifier
            else: # Se for string Processo_Novo, tenta buscar o ID numérico
                existing_process_data = db_manager.obter_processo_by_processo_novo(process_identifier)
                if existing_process_data:
                    process_id = existing_process_data['id']
                else:
                    process_id = None # Processo_Novo não encontrado no SQLite

    linked_di_id = st.session_state[form_state_key].get('DI_ID_Vinculada')
    linked_di_number = None
    if linked_di_id:
        linked_di_data = db_utils.get_declaracao_by_id(linked_di_id)
        if linked_di_data:
            linked_di_number = _format_di_number(str(linked_di_data.get('numero_di') if isinstance(linked_di_data, dict) else linked_di_data['numero_di']))

    # Cabeçalho com título centralizado e estilo dinâmico
    if st.session_state[f'{form_state_key}_is_new_process_flag']:
        st.markdown("<h2 class='header-new-process'>➕ Novo Processo</h2>", unsafe_allow_html=True)
    else:
        st.markdown(f"<h2 class='header-edit-process'>✏️ Editar Processo: {st.session_state[form_state_key].get('Processo_Novo', '')}</h2>", unsafe_allow_html=True)
    
    # Informações de DI vinculada, se existir
    if linked_di_id is not None and linked_di_number:
        st.info(f"**🔗 DI Vinculada:** {linked_di_number} - Clique no botão ao final do formulário para ver detalhes.")
    elif linked_di_id is not None and not linked_di_number: 
        st.warning(f"DI vinculada (ID: {linked_di_id}) não encontrada no banco de dados.")

    # Sempre inicialize as flags de popup se não existirem
    st.session_state.setdefault('show_add_item_popup', False)
    st.session_state.setdefault('selected_item_indices', [])
    st.session_state.setdefault('show_edit_item_popup', False)
    st.session_state.setdefault('item_to_edit_index', None)
    st.session_state.setdefault('last_processed_upload_key', None)
    st.session_state.setdefault('uploaded_file_key', None) # Alterado para uploaded_file_key

    tabs_names = list(campos_config_tabs.keys())
    tabs = st.tabs(tabs_names)

    for i, tab_name in enumerate(tabs_names):
        with tabs[i]:
            if tab_name == "Dados Gerais":
                col_left, col_right = st.columns(2) 

                with col_left:
                    for field_name, config in campos_config_tabs[tab_name]["col1"].items():
                        current_value = st.session_state[form_state_key].get(field_name)
                        label_with_icon = f"{config.get('icon', '')} {config['label']}" # Adiciona ícone ao label
                        if config["type"] == "number":
                            default_value_for_number_input = int(current_value) if (current_value is not None and not pd.isna(current_value)) else 0
                            widget_value = st.number_input(label_with_icon, value=default_value_for_number_input, format="%d", key=f"{form_state_key}_{field_name}", disabled=config.get("disabled", False))
                            st.session_state[form_state_key][field_name] = int(widget_value) if widget_value is not None else None
                        else:
                            widget_value = st.text_input(label_with_icon, value=current_value if current_value is not None else "", key=f"{form_state_key}_{field_name}", disabled=config.get("disabled", False))
                            st.session_state[form_state_key][field_name] = widget_value if widget_value else None

                with col_right:
                    # Captura o valor do Modal e Consolidado para lógica condicional
                    current_modal_selection = st.session_state[form_state_key].get("Modal", "")
                    current_consolidado_selection = st.session_state[form_state_key].get("Consolidado", "")

                    for field_name, config in campos_config_tabs[tab_name]["col2"].items():
                        current_value = st.session_state[form_state_key].get(field_name)
                        is_conditional_field = "conditional_field" in config
                        is_field_enabled = True # Assume que o campo está habilitado

                        # Lógica para campos condicionais
                        if is_conditional_field:
                            parent_field_value = None
                            if config["conditional_field"] == "Modal":
                                parent_field_value = current_modal_selection
                            elif config["conditional_field"] == "Consolidado":
                                parent_field_value = current_consolidado_selection
                            
                            # Condição para habilitar/desabilitar o campo
                            if parent_field_value != config["conditional_value"]:
                                is_field_enabled = False
                                # Limpa o valor do campo se ele não estiver habilitado
                                if st.session_state[form_state_key].get(field_name) is not None:
                                    # Se for um dropdown, limpa para o primeiro valor (geralmente vazio)
                                    if config["type"] == "dropdown":
                                        st.session_state[form_state_key][field_name] = config["values"][0] if config["values"] else None
                                    else:
                                        st.session_state[form_state_key][field_name] = None
                        
                        is_disabled_overall = config.get("disabled", False) or not is_field_enabled
                        label_with_icon = f"{config.get('icon', '')} {config['label']}" # Adiciona ícone ao label

                        if config["type"] == "dropdown":
                            options = config["values"]
                            default_index = 0
                            if current_value in options:
                                default_index = options.index(current_value)
                            elif current_value is not None and str(current_value).strip() != "" and current_value not in options:
                                options = [current_value] + options
                                default_index = 0
                            
                            # Adicionar on_change para Modal e Consolidado para forçar re-renderização
                            on_change_callback = None
                            if field_name == "Modal":
                                on_change_callback = _on_modal_change_rerun
                            elif field_name == "Consolidado":
                                on_change_callback = _on_consolidado_change_rerun

                            widget_value = st.selectbox(
                                label_with_icon, 
                                options=options, 
                                index=default_index, 
                                key=f"{form_state_key}_{field_name}", 
                                disabled=is_disabled_overall,
                                on_change=on_change_callback if on_change_callback else None # Definir callback
                            )
                            st.session_state[form_state_key][field_name] = widget_value if widget_value else None
                        elif config["type"] == "number":
                            default_value_for_number_input = int(current_value) if (current_value is not None and not pd.isna(current_value)) else 0
                            
                            # NOVO: Min/Max values para LCL_Processos_Quantidade
                            min_val = config.get("min_value", None)
                            max_val = config.get("max_value", None)
                            num_format = config.get("format", "%d")

                            widget_value = st.number_input(
                                label_with_icon, 
                                value=default_value_for_number_input, 
                                format=num_format, 
                                key=f"{form_state_key}_{field_name}", 
                                disabled=is_disabled_overall,
                                min_value=min_val,
                                max_value=max_val
                            )
                            st.session_state[form_state_key][field_name] = int(widget_value) if widget_value is not None else None
                        elif config["type"] == "date":
                            current_value_dt = None
                            if current_value:
                                try:
                                    if isinstance(current_value, str):
                                        current_value_dt = datetime.strptime(current_value, "%Y-%m-%d").date()
                                    elif isinstance(current_value, (datetime, date)):
                                        current_value_dt = current_value.date()
                                except ValueError:
                                    current_value_dt = None
                            widget_value = st.date_input(label_with_icon, value=current_value_dt, key=f"{form_state_key}_{field_name}", format="DD/MM/YYYY", disabled=is_disabled_overall)
                            st.session_state[form_state_key][field_name] = widget_value.strftime("%Y-%m-%d") if widget_value else None
                        else: # text input
                            widget_value = st.text_input(
                                label_with_icon, 
                                value=current_value if current_value is not None else "", 
                                key=f"{form_state_key}_{field_name}", 
                                disabled=is_disabled_overall, 
                                help=config.get("help", None)
                            )
                            st.session_state[form_state_key][field_name] = widget_value if widget_value else None

                st.markdown("---")
                st.subheader("Importar/Exportar Dados do Processo")
                # REMOVIDO: Baixar Template Processo
                # REMOVIDO: Upload Excel/CSV de Dados do Processo
                st.info("Funcionalidade de importação/exportação de dados gerais do processo via Excel/CSV removida.")
                
                # Recalcular automaticamente todos os itens se os campos relevantes mudarem
                _recalculate_all_items_if_needed(form_state_key)


            elif tab_name == "Itens":
                st.subheader("Itens do Processo")
                
                current_fornecedor_context = st.session_state[form_state_key].get("Fornecedor", "N/A")
                current_invoice_n_context = st.session_state[form_state_key].get("N_Invoice", "N/A")
                
                col_add_item, col_edit_item, col_delete_item = st.columns([0.15, 0.15, 0.15])

                with col_add_item:
                    if st.button("Adicionar Item Manualmente", key="add_item_button_in_items_tab"):
                        st.session_state.show_add_item_popup = True
                        st.session_state.show_edit_item_popup = False
                
                if st.session_state.get('show_add_item_popup', False):
                    # Removido 'key' do st.popover para corrigir TypeError
                    with st.popover("Adicionar Novo Item"): 
                        with st.form("add_item_form_fixed", clear_on_submit=True):
                            new_item_codigo_interno = st.text_input("Código Interno", value="", key="new_item_codigo_interno_popup")
                            all_ncm_items = db_utils.selecionar_todos_ncm_itens()
                            # Garantir que ncm_options sempre tenha uma opção vazia no início
                            ncm_options = [""] + sorted([ncm_list_page.format_ncm_code(item['ncm_code']) for item in all_ncm_items]) if ncm_list_page else [""]
                            new_item_ncm_display = st.selectbox("NCM", options=ncm_options, key="new_item_ncm_popup")
                            new_item_cobertura = st.selectbox("Cobertura", options=["SIM", "NÃO"], key="new_item_cobertura_popup")
                            new_item_sku = st.text_input("SKU", value="", key="new_item_sku_popup")
                            new_item_quantidade = st.number_input("Quantidade", min_value=0, value=0, step=1, key="new_item_quantidade_popup")
                            new_item_valor_unitario = st.number_input("Valor Unitário (USD)", min_value=0.0, format="%.2f", key="new_item_valor_unitario_popup")
                            new_item_denominacao = st.text_input("Denominação do produto", value="", key="new_item_denominacao_popup")
                            new_item_detalhamento = st.text_input("Detalhamento complementar do produto", value="", key="new_item_detalhamento_popup")

                            if st.form_submit_button("Adicionar Item"):
                                raw_new_item_data = {
                                    "Código Interno": new_item_codigo_interno, "NCM": re.sub(r'\D', '', new_item_ncm_display) if new_item_ncm_display else None,
                                    "Cobertura": new_item_cobertura, "SKU": new_item_sku, "Quantidade": new_item_quantidade, 
                                    "Valor Unitário": new_item_valor_unitario,
                                    "Denominação do produto": new_item_denominacao, "Detalhamento complementar do produto": new_item_detalhamento,
                                    "Fornecedor": current_fornecedor_context, "Invoice N#": current_invoice_n_context
                                }
                                # Padronizar e recalcular valores do item
                                standardized_new_item_data = _standardize_item_data(raw_new_item_data, current_fornecedor_context, current_invoice_n_context)
                                standardized_new_item_data["Valor total do item"] = standardized_new_item_data["Quantidade"] * standardized_new_item_data["Valor Unitário"]
                                
                                # --- Automação da busca de NCM/Descrição para item manual ---
                                if standardized_new_item_data.get('NCM'):
                                    ncm_info = db_utils.get_ncm_item_by_ncm_code(standardized_new_item_data['NCM'])
                                    if ncm_info:
                                        standardized_new_item_data['Denominação do produto'] = ncm_info.get('descricao_item', standardized_new_item_data.get('Denominação do produto'))
                                        logger.info(f"[Adicionar Item] NCM {standardized_new_item_data['NCM']} encontrado. Descrição: {ncm_info.get('descricao_item')}")
                                    else:
                                        logger.warning(f"[Adicionar Item] NCM {standardized_new_item_data['NCM']} não encontrado no banco de dados")
                                elif standardized_new_item_data.get('Denominação do produto'):
                                    ncm_info_by_desc = db_utils.search_ncm_by_description(standardized_new_item_data['Denominação do produto'])
                                    if ncm_info_by_desc:
                                        standardized_new_item_data['NCM'] = ncm_info_by_desc.get('ncm_code', standardized_new_item_data.get('NCM'))
                                        standardized_new_item_data['Denominação do produto'] = ncm_info_by_desc.get('descricao_item', standardized_new_item_data.get('Denominação do produto'))
                                        logger.info(f"[Adicionar Item] Busca por descrição encontrou NCM {ncm_info_by_desc.get('ncm_code')}")
                                    else:
                                        logger.warning(f"[Adicionar Item] Nenhum NCM encontrado para descrição: {standardized_new_item_data['Denominação do produto']}")

                                # Anexa o novo item ao process_items_data
                                st.session_state.process_items_data.append(standardized_new_item_data)
                                
                                # Recalcular totais globais e impostos de todos os itens
                                # Criar um DataFrame temporário para os cálculos agregados
                                temp_df_for_calc = pd.DataFrame(st.session_state.process_items_data)
                                total_invoice_value_usd_recalc = temp_df_for_calc["Valor total do item"].sum() if "Valor total do item" in temp_df_for_calc.columns else 0.0
                                # Como removemos Peso Unitário, usamos um peso padrão baseado no valor
                                total_invoice_weight_kg_recalc = total_invoice_value_usd_recalc * 0.5  # Peso estimado baseado no valor
                                
                                st.session_state.total_invoice_value_usd = total_invoice_value_usd_recalc
                                st.session_state.total_invoice_weight_kg = total_invoice_weight_kg_recalc

                                # Recalcular impostos para CADA item após a mudança de totais
                                dolar_brl = st.session_state[form_state_key].get("Estimativa_Dolar_BRL", 0.0)
                                frete_usd = st.session_state[form_state_key].get('Estimativa_Frete_USD', 0.0)
                                seguro_brl = st.session_state[form_state_key].get('Estimativa_Seguro_BRL', 0.0)

                                for item_in_list in st.session_state.process_items_data:
                                    calculate_item_taxes_and_values(
                                        item_in_list, dolar_brl, total_invoice_value_usd_recalc, total_invoice_weight_kg_recalc,
                                        frete_usd, seguro_brl
                                    )
                                
                                _display_message_box("Item adicionado com sucesso!", "success")
                                st.session_state.show_add_item_popup = False
                                st.rerun() # Força uma recarga para atualizar a tabela e totais
                                
                st.markdown("---")
                st.subheader("Importar Itens do Excel (CSV/XLSX)") # Alterado o título
                uploaded_file = st.file_uploader("Upload Excel (CSV/XLSX) de Pedido de Compra", type=["csv", "xlsx"], key="upload_excel_or_csv_file") # Alterado o tipo e a chave
                current_file_upload_key = (uploaded_file.name, uploaded_file.size) if uploaded_file else None

                # Lógica para recarregar itens após anexar o Excel
                if uploaded_file is not None:
                    # Se um novo arquivo foi carregado ou se o mesmo arquivo foi re-selecionado (para forçar re-processamento)
                    if current_file_upload_key != st.session_state.get('uploaded_file_key') or \
                       (current_file_upload_key == st.session_state.get('uploaded_file_key') and not st.session_state.get('process_items_data')):
                        
                        with st.spinner("Extraindo itens do Excel (CSV/XLSX)..."): # Alterado o texto
                            extracted_items = _extract_items_from_excel_or_csv(uploaded_file) # Chamada da nova função
                            if extracted_items:
                                # Adiciona os itens extraídos do arquivo à lista de itens do processo
                                # Limpa os itens existentes se for uma nova importação
                                st.session_state.process_items_data = [] 
                                st.session_state.process_items_data.extend(extracted_items)
                                st.session_state.uploaded_file_key = current_file_upload_key # Atualiza a chave do upload
                                _display_message_box(f"{len(extracted_items)} itens extraídos do arquivo e adicionados.", "success") # Alterado o texto
                                st.rerun() # Força recarga para exibir os cards
                            else:
                                _display_message_box("Nenhum item encontrado no arquivo ou erro na extração.", "warning") # Alterado o texto
                                st.session_state.uploaded_file_key = None # Não salva a chave se a extração falhou
                                st.session_state.process_items_data = [] # Garante que a lista de itens esteja vazia
                                st.rerun() # Força re-renderização para limpar a tabela
                
                st.markdown("---") 

                # Implementação da visualização Mestre-Detalhe
                if st.session_state.process_items_data:
                    st.markdown('<div class="item-section">', unsafe_allow_html=True)
                    st.markdown("#### Itens do Processo:")
                    
                    col_master, col_detail = st.columns([0.4, 0.6]) # Proporção para os painéis

                    with col_master:
                        st.markdown('<div class="item-list-radio">', unsafe_allow_html=True)
                        st.markdown("##### Lista de Itens")
                        # Cria um DataFrame para a lista mestre (apenas colunas essenciais para identificação)
                        df_master_list = pd.DataFrame(st.session_state.process_items_data)
                        
                        # Adiciona uma coluna de seleção de rádio para selecionar o item
                        # Usamos st.radio com o índice do item para seleção
                        # Ajuste do título de cada item para Código, SKU, quantidade
                        selected_item_index = st.radio(
                            "Selecione um item para editar:",
                            options=range(len(df_master_list)),
                            format_func=lambda idx: f"Cód: {df_master_list.loc[idx, 'Código Interno']} | SKU: {df_master_list.loc[idx, 'SKU']} | Quant: {df_master_list.loc[idx, 'Quantidade']}",
                            key=f"{form_state_key}_master_list_selection"
                        )

                        # Armazena o item selecionado no estado da sessão para o painel de detalhes
                        if selected_item_index is not None:
                            st.session_state.selected_item_for_detail_edit = st.session_state.process_items_data[selected_item_index]
                        else:
                            st.session_state.selected_item_for_detail_edit = None
                        st.markdown('</div>', unsafe_allow_html=True)

                    with col_detail:
                        st.markdown("##### Detalhes do Item Selecionado")
                        if st.session_state.selected_item_for_detail_edit:
                            current_item = st.session_state.selected_item_for_detail_edit
                            item_idx = st.session_state.process_items_data.index(current_item) # Obter o índice do item

                            with st.form(key=f"detail_edit_form_{item_idx}"):
                                st.markdown('<div class="item-detail-form">', unsafe_allow_html=True)
                                # Campos para preencher/selecionar manualmente
                                current_item['Código Interno'] = st.text_input("Código Interno", value=current_item.get('Código Interno', ''), key=f"det_cod_int_{item_idx}")
                                current_item['SKU'] = st.text_input("SKU", value=current_item.get('SKU', ''), key=f"det_sku_{item_idx}")
                                current_item['Denominação do produto'] = st.text_area("Denominação do produto", value=current_item.get('Denominação do produto', ''), key=f"det_den_prod_{item_idx}")
                                
                                # NCM com busca automática
                                current_ncm = current_item.get('NCM', '')
                                formatted_ncm = ncm_list_page.format_ncm_code(str(current_ncm)) if ncm_list_page and current_ncm else ''
                                new_ncm_input = st.text_input("NCM (formato xxxx.xx.xx):", value=formatted_ncm, key=f"det_ncm_{item_idx}")
                                current_item['NCM'] = re.sub(r'\D', '', new_ncm_input) if new_ncm_input else None
                                
                                # Cobertura como Selectbox
                                current_cobertura = current_item.get('Cobertura', 'NÃO')
                                current_item['Cobertura'] = st.selectbox("Cobertura", options=["SIM", "NÃO"], index=0 if current_cobertura == "SIM" else 1, key=f"det_cob_{item_idx}")

                                current_item['Quantidade'] = st.number_input("Quantidade", value=int(current_item.get('Quantidade', 0)), min_value=0, step=1, key=f"det_quant_{item_idx}")
                                current_item['Valor Unitário'] = st.number_input("Valor Unitário (USD)", value=float(current_item.get('Valor Unitário', 0.0)), format="%.2f", key=f"det_val_unit_{item_idx}")

                                # Campos de impostos (somente leitura, calculados)
                                st.markdown('<div class="tax-info">', unsafe_allow_html=True)
                                st.markdown(f"**II (R$):** {current_item.get('Estimativa_II_BR', 0.0):.2f}")
                                st.markdown(f"**IPI (R$):** {current_item.get('Estimativa_IPI_BR', 0.0):.2f}")
                                st.markdown(f"**PIS (R$):** {current_item.get('Estimativa_PIS_BR', 0.0):.2f}")
                                st.markdown(f"**COFINS (R$):** {current_item.get('Estimativa_COFINS_BR', 0.0):.2f}")
                                st.markdown(f"**ICMS (R$):** {current_item.get('Estimativa_ICMS_BR', 0.0):.2f}")
                                st.markdown(f"**VLMD (R$):** {current_item.get('VLMD_Item', 0.0):.2f}")
                                st.markdown(f"**Frete Rateado (USD):** {current_item.get('Frete_Rateado_USD', 0.0):.2f}")
                                st.markdown(f"**Seguro Rateado (BRL):** {current_item.get('Seguro_Rateado_BRL', 0.0):.2f}")
                                st.markdown(f"**Valor Total do Item:** {current_item.get('Valor total do item', 0.0):.2f}")
                                st.markdown('</div>', unsafe_allow_html=True)
                                
                                st.markdown('</div>', unsafe_allow_html=True)  # Fecha item-detail-form
                                st.markdown('<div class="item-buttons">', unsafe_allow_html=True)
                                col_save_item, col_cancel_item, col_delete_item_detail = st.columns(3) # Adicionado col_delete_item_detail
                                with col_save_item:
                                    if st.form_submit_button("Salvar Item"):
                                        # Recalcular valores e impostos para o item editado
                                        # Automação da busca de NCM/Descrição
                                        if current_item.get('NCM'):
                                            ncm_info = db_utils.get_ncm_item_by_ncm_code(current_item['NCM'])
                                            if ncm_info:
                                                current_item['Denominação do produto'] = ncm_info.get('descricao_item', current_item.get('Denominação do produto'))
                                                logger.info(f"[Editar Item] NCM {current_item['NCM']} encontrado. Descrição: {ncm_info.get('descricao_item')}")
                                            else:
                                                logger.warning(f"[Editar Item] NCM {current_item['NCM']} não encontrado no banco de dados")
                                        elif current_item.get('Denominação do produto'):
                                            ncm_info_by_desc = db_utils.search_ncm_by_description(current_item['Denominação do produto'])
                                            if ncm_info_by_desc:
                                                current_item['NCM'] = ncm_info_by_desc.get('ncm_code', current_item.get('NCM'))
                                                current_item['Denominação do produto'] = ncm_info_by_desc.get('descricao_item', current_item.get('Denominação do produto'))
                                                logger.info(f"[Editar Item] Busca por descrição encontrou NCM {ncm_info_by_desc.get('ncm_code')}")
                                            else:
                                                logger.warning(f"[Editar Item] Nenhum NCM encontrado para descrição: {current_item['Denominação do produto']}")

                                        current_item["Valor total do item"] = current_item["Quantidade"] * current_item["Valor Unitário"]
                                        
                                        dolar_brl = st.session_state[form_state_key].get("Estimativa_Dolar_BRL", 0.0)
                                        frete_usd = st.session_state[form_state_key].get('Estimativa_Frete_USD', 0.0)
                                        seguro_brl = st.session_state[form_state_key].get('Estimativa_Seguro_BRL', 0.0)
                                        
                                        # Recalcular totais globais para todos os itens
                                        temp_df_for_calc = pd.DataFrame(st.session_state.process_items_data)
                                        total_invoice_value_usd_recalc = temp_df_for_calc["Valor total do item"].sum() if "Valor total do item" in temp_df_for_calc.columns else 0.0
                                        # Como removemos Peso Unitário, usamos um peso padrão baseado no valor
                                        total_invoice_weight_kg_recalc = total_invoice_value_usd_recalc * 0.5  # Peso estimado baseado no valor

                                        calculate_item_taxes_and_values(
                                            current_item, dolar_brl, total_invoice_value_usd_recalc, total_invoice_weight_kg_recalc,
                                            frete_usd, seguro_brl
                                        )
                                        st.session_state.process_items_data[item_idx] = current_item # Atualiza o item na lista principal
                                        _display_message_box("Item salvo com sucesso!", "success")
                                        st.session_state.selected_item_for_detail_edit = None # Limpa a seleção
                                        st.rerun() # Força a re-renderização para atualizar a lista mestre
                                with col_cancel_item:
                                    if st.form_submit_button("Cancelar"):
                                        st.session_state.selected_item_for_detail_edit = None # Limpa a seleção
                                        st.rerun()
                                with col_delete_item_detail: # NOVO: Botão de exclusão
                                    if st.form_submit_button("Excluir Item"):
                                        # Lógica para excluir o item
                                        if item_idx is not None:
                                            del st.session_state.process_items_data[item_idx]
                                            _display_message_box("Item excluído com sucesso!", "success")
                                            st.session_state.selected_item_for_detail_edit = None # Limpa a seleção
                                            st.rerun() # Força a re-renderização
                                        else:
                                            _display_message_box("Nenhum item selecionado para exclusão.", "warning")
                                st.markdown('</div>', unsafe_allow_html=True)  # Fecha item-buttons
                        else:
                            st.info("Selecione um item na lista à esquerda para ver e editar seus detalhes.")
                    st.markdown('</div>', unsafe_allow_html=True)  # Fecha item-section
                else:
                    st.info("Nenhum item adicionado a este processo ainda. Use o upload do Excel (CSV/XLSX) ou o botão 'Adicionar Item Manualmente'.") # Alterado o texto

            elif tab_name == "Valores e Estimativas":
                st.subheader("Valores e Estimativas")
                
                # Obtém os totais dos itens do st.session_state, que já foram calculados em _initialize_form_state ou ao adicionar/editar itens.
                total_itens_usd_from_session = st.session_state.get('total_invoice_value_usd', 0.0)
                
                # Obtém o valor do câmbio, usando PTAX Venda se for 0.0 ou não existir
                dolar_brl_current = st.session_state[form_state_key].get("Estimativa_Dolar_BRL", 0.0)
                if not dolar_brl_current or dolar_brl_current == 0.0:
                    dolar_brl_current = get_current_dolar_ptax_venda()
                    st.session_state[form_state_key]["Estimativa_Dolar_BRL"] = dolar_brl_current
                    logger.info(f"[Valores e Estimativas] Atualizando câmbio para PTAX Venda: {dolar_brl_current}")
                dolar_brl_current = float(dolar_brl_current)
                logger.info(f"[Valores e Estimativas] Câmbio atual: {dolar_brl_current}")
                
                # Atualiza o Valor_USD no estado do formulário com o total calculado
                st.session_state[form_state_key]["Valor_USD"] = total_itens_usd_from_session 
                
                # Campos de Valores e Estimativas
                frete_usd_current = float(st.session_state[form_state_key].get("Estimativa_Frete_USD", 0.0) or 0.0)
                seguro_brl_current = float(st.session_state[form_state_key].get("Estimativa_Seguro_BRL", 0.0) or 0.0)
                
                col_1, col_2 = st.columns(2)

                with col_1:
                    # Input para Dólar/BRL, e os demais são exibição ou entrada
                    st.session_state[form_state_key]["Estimativa_Dolar_BRL"] = st.number_input(
                        f"{campos_config_tabs['Valores e Estimativas']['Estimativa_Dolar_BRL']['icon']} {campos_config_tabs['Valores e Estimativas']['Estimativa_Dolar_BRL']['label']}", 
                        value=dolar_brl_current, format="%.2f", key=f"{form_state_key}_Estimativa_Dolar_BRL"
                    )
                    st.number_input(
                        f"{campos_config_tabs['Valores e Estimativas']['Valor_USD']['icon']} {campos_config_tabs['Valores e Estimativas']['Valor_USD']['label']}", 
                        value=float(st.session_state[form_state_key]["Valor_USD"] or 0.0), format="%.2f",
                        key=f"{form_state_key}_Valor_USD_display", disabled=True
                    )
                    st.session_state[form_state_key]["Estimativa_Frete_USD"] = st.number_input(
                        f"{campos_config_tabs['Valores e Estimativas']['Estimativa_Frete_USD']['icon']} {campos_config_tabs['Valores e Estimativas']['Estimativa_Frete_USD']['label']}", 
                        value=frete_usd_current, format="%.2f", key=f"{form_state_key}_Estimativa_Frete_USD"
                    )
                    st.session_state[form_state_key]["Estimativa_Seguro_BRL"] = st.number_input(
                        f"{campos_config_tabs['Valores e Estimativas']['Estimativa_Seguro_BRL']['icon']} {campos_config_tabs['Valores e Estimativas']['Estimativa_Seguro_BRL']['label']}", 
                        value=seguro_brl_current, format="%.2f", key=f"{form_state_key}_Estimativa_Seguro_BRL"
                    )

                    st.session_state[form_state_key]["Estimativa_Impostos_BR"] = st.number_input(
                        f"{campos_config_tabs['Valores e Estimativas']['Estimativa_Impostos_BR']['icon']} {campos_config_tabs['Valores e Estimativas']['Estimativa_Impostos_BR']['label']}:", 
                        value=float(st.session_state[form_state_key].get("Estimativa_Impostos_BR", 0.0) or 0.0), 
                        format="%.2f", key=f"{form_state_key}_Estimativa_Impostos_BR", disabled=True,
                        help="Campo de impostos para compatibilidade com versões antigas do DB."
                    )
                    
                    # Soma os impostos dos itens que já estão calculados em st.session_state.process_items_data
                    total_ii = total_ipi = total_pis = total_cofins = total_icms_calculated_sum = 0.0
                    if st.session_state.process_items_data:
                        for item in st.session_state.process_items_data:
                            total_ii += item.get('Estimativa_II_BR', 0.0)
                            total_ipi += item.get('Estimativa_IPI_BR', 0.0)
                            total_pis += item.get('Estimativa_PIS_BR', 0.0)
                            total_cofins += item.get('Estimativa_COFINS_BR', 0.0)
                            total_icms_calculated_sum += item.get('Estimativa_ICMS_BR', 0.0)

                    # Atualiza os valores calculados no estado do formulário
                    st.session_state[form_state_key]['Estimativa_II_BR'] = total_ii
                    st.session_state[form_state_key]['Estimativa_IPI_BR'] = total_ipi
                    st.session_state[form_state_key]['Estimativa_PIS_BR'] = total_pis
                    st.session_state[form_state_key]['Estimativa_COFINS_BR'] = total_cofins
                    st.session_state[form_state_key]['Estimativa_ICMS_BR'] = total_icms_calculated_sum
                    
                    # Soma total de impostos (agora usando o ICMS calculado dos itens)
                    total_impostos_reais = total_ii + total_ipi + total_pis + total_cofins + total_icms_calculated_sum
                    st.session_state[form_state_key]['Estimativa_Impostos_Total'] = total_impostos_reais

                with col_2:
                    st.number_input(f"{campos_config_tabs['Valores e Estimativas']['Estimativa_II_BR']['icon']} Estimativa de II (R$ - Calculado):", value=st.session_state[form_state_key].get('Estimativa_II_BR', 0.0), format="%.2f", disabled=True, key=f"display_{form_state_key}_II_BR_calc")
                    st.number_input(f"{campos_config_tabs['Valores e Estimativas']['Estimativa_IPI_BR']['icon']} Estimativa de IPI (R$ - Calculado):", value=st.session_state[form_state_key].get('Estimativa_IPI_BR', 0.0), format="%.2f", disabled=True, key=f"display_{form_state_key}_IPI_BR_calc")
                    st.number_input(f"{campos_config_tabs['Valores e Estimativas']['Estimativa_PIS_BR']['icon']} Estimativa de PIS (R$ - Calculado):", value=st.session_state[form_state_key].get('Estimativa_PIS_BR', 0.0), format="%.2f", disabled=True, key=f"display_{form_state_key}_PIS_BR_calc")
                    st.number_input(f"{campos_config_tabs['Valores e Estimativas']['Estimativa_COFINS_BR']['icon']} Estimativa de COFINS (R$ - Calculado):", value=st.session_state[form_state_key].get('Estimativa_COFINS_BR', 0.0), format="%.2f", disabled=True, key=f"display_{form_state_key}_COFINS_BR_calc")
                    st.number_input(f"{campos_config_tabs['Valores e Estimativas']['Estimativa_ICMS_BR']['icon']} Estimativa de ICMS (R$ - Calculado):", value=st.session_state[form_state_key].get('Estimativa_ICMS_BR', 0.0), format="%.2f", disabled=True, key=f"display_{form_state_key}_ICMS_BR_calc")
                    st.number_input(f"{campos_config_tabs['Valores e Estimativas']['Estimativa_Impostos_Total']['icon']} Estimativa Impostos (R$):", value=st.session_state[form_state_key].get('Estimativa_Impostos_Total', 0.0), format="%.2f", disabled=True, key=f"display_{form_state_key}_Impostos_Total_calc")
                    st.caption("Os valores acima são a soma dos impostos calculados para cada item com base no NCM.")
                
                # Recalcular automaticamente todos os itens se os campos relevantes mudarem
                _recalculate_all_items_if_needed(form_state_key)

            elif tab_name == "Status Operacional":
                st.subheader("Status Operacional")
                # OBSERVAÇÃO: Estes campos foram movidos do Status Operacional original para Dados Gerais.
                # Se desejar mantê-los aqui e remover de Dados Gerais, faça o ajuste na campos_config_tabs
                # A configuração atual reflete que esses campos são para "Dados Gerais"
                for field_name, config in campos_config_tabs[tab_name].items():
                    current_value = st.session_state[form_state_key].get(field_name)
                    label_with_icon = f"{config.get('icon', '')} {config['label']}" # Adiciona ícone ao label

                    if config["type"] == "date":
                        current_value_dt = None
                        if current_value:
                            try:
                                if isinstance(current_value, str):
                                    current_value_dt = datetime.strptime(current_value, "%Y-%m-%d").date()
                                elif isinstance(current_value, (datetime, date)):
                                    current_value_dt = current_value.date()
                            except ValueError:
                                current_value_dt = None
                        widget_value = st.date_input(label_with_icon, value=current_value_dt, key=f"{form_state_key}_{field_name}", format="DD/MM/YYYY")
                        st.session_state[form_state_key][field_name] = widget_value.strftime("%Y-%m-%d") if widget_value else None
                    elif config["type"] == "dropdown":
                        options = config["values"]
                        default_index = 0
                        if current_value in options:
                            default_index = options.index(current_value)
                        elif current_value is not None and str(current_value).strip() != "" and current_value not in options:
                            options = [current_value] + options
                            default_index = 0
                        widget_value = st.selectbox(label_with_icon, options=options, index=default_index, key=f"{form_state_key}_{field_name}")
                        st.session_state[form_state_key][field_name] = widget_value if widget_value else None
                    else:
                        widget_value = st.text_input(label_with_icon, value=current_value if current_value is not None else "", key=f"{form_state_key}_{field_name}")
                        st.session_state[form_state_key][field_name] = widget_value if widget_value else None

    st.markdown("---")
    
    # Container para observação com estilo melhorado
    st.markdown("<div class='observation-container'>", unsafe_allow_html=True)
    st.markdown("<div class='observation-title'>📝 Observações do Processo</div>", unsafe_allow_html=True)
    st.session_state[form_state_key]["Observacao"] = st.text_area(
        "Adicione notas, comentários ou informações adicionais sobre este processo",
        value=st.session_state[form_state_key].get("Observacao", "") or "",
        height=120,
        key=f"{form_state_key}_Observacao_dedicated",
        placeholder="Adicione aqui qualquer informação relevante sobre este processo..."
    )
    st.session_state[form_state_key]["Observacao"] = st.session_state[form_state_key]["Observacao"] if st.session_state[form_state_key]["Observacao"] else None
    st.markdown("</div>", unsafe_allow_html=True)

    # Botões de ação em um layout mais atraente
    with st.form(key=f"followup_process_form_submit_buttons_{process_id}", clear_on_submit=False):
        col_save, col_cancel, col_delete = st.columns([0.4, 0.3, 0.3]) # Layout mais equilibrado

        with col_save:
            if st.form_submit_button("💾 Salvar Processo"): # Ícone adicionado
                edited_data_to_save = {}
                for tab_name, tab_config in campos_config_tabs.items():
                    if "col1" in tab_config:
                        for field_name, config in tab_config["col1"].items():
                            edited_data_to_save[field_name] = st.session_state.get(f"{form_state_key}_{field_name}")
                    if "col2" in tab_config:
                        for field_name, config in tab_config["col2"].items():
                            # Se o campo condicional está desabilitado, garante que seu valor seja None
                            is_conditional_field = "conditional_field" in config
                            is_field_enabled = True
                            if is_conditional_field:
                                parent_field_value = None
                                if config["conditional_field"] == "Modal":
                                    parent_field_value = st.session_state.get(f"{form_state_key}_Modal")
                                elif config["conditional_field"] == "Consolidado":
                                    parent_field_value = st.session_state.get(f"{form_state_key}_Consolidado")
                                
                                if parent_field_value != config["conditional_value"]:
                                    is_field_enabled = False
                            
                            if not is_field_enabled:
                                edited_data_to_save[field_name] = None
                            else:
                                edited_data_to_save[field_name] = st.session_state.get(f"{form_state_key}_{field_name}")
                                
                    if tab_name not in ["Dados Gerais", "Itens"]:
                        for field_name, config in tab_config.items():
                            # Se o campo é desabilitado e do tipo moeda BR, usa o valor do st.session_state[form_state_key] (já calculado)
                            if config.get("disabled", False) and config.get("type") == "currency_br":
                                edited_data_to_save[field_name] = st.session_state[form_state_key].get(field_name)
                            # Para os campos de arquivo, pegamos diretamente do session_state[form_state_key]
                            elif field_name in ["Nome_do_arquivo", "Tipo_do_arquivo", "Conteudo_do_arquivo"]:
                                edited_data_to_save[field_name] = st.session_state[form_state_key].get(field_name)
                            else:
                                edited_data_to_save[field_name] = st.session_state.get(f"{form_state_key}_{field_name}")
                edited_data_to_save["Observacao"] = st.session_state.get(f"{form_state_key}_Observacao_dedicated")
                
                # Garante que todos os campos de cálculo e totais sejam passados corretamente
                # Eles já estão atualizados em st.session_state[form_state_key] devido aos cálculos anteriores
                edited_data_to_save.update({
                    'Valor_USD': st.session_state[form_state_key].get('Valor_USD', 0.0),
                    'Estimativa_Impostos_Total': st.session_state[form_state_key].get('Estimativa_Impostos_Total', 0.0),
                    'Estimativa_II_BR': st.session_state[form_state_key].get('Estimativa_II_BR', 0.0),
                    'Estimativa_IPI_BR': st.session_state[form_state_key].get('Estimativa_IPI_BR', 0.0),
                    'Estimativa_PIS_BR': st.session_state[form_state_key].get('Estimativa_PIS_BR', 0.0),
                    'Estimativa_COFINS_BR': st.session_state[form_state_key].get('Estimativa_COFINS_BR', 0.0),
                    'Estimativa_Frete_USD': st.session_state[form_state_key].get('Estimativa_Frete_USD', 0.0),
                    'Estimativa_Seguro_BRL': st.session_state[form_state_key].get('Estimativa_Seguro_BRL', 0.0),
                    'Estimativa_Dolar_BRL': st.session_state[form_state_key].get('Estimativa_Dolar_BRL', 0.0),
                    'Estimativa_ICMS_BR': st.session_state[form_state_key].get('Estimativa_ICMS_BR', 0.0),
                })

                logger.info(f"Dados coletados para salvar (process_form_page): {edited_data_to_save} (total de chaves: {len(edited_data_to_save)})")

                is_new_process_for_save = st.session_state.get(f'{form_state_key}_is_new_process_flag', False)
                process_id_arg_for_save_action = None if is_new_process_for_save else process_id

                saved_process_id = _save_process_action(process_id_arg_for_save_action, edited_data_to_save, is_new_process_for_save, form_state_key)
                
                if saved_process_id:
                    st.session_state.current_page = "Follow-up Importação"
                    st.session_state.form_process_identifier = saved_process_id
                    st.session_state.form_is_cloning = False
                    st.session_state.last_cloned_from_id = None
                else:
                    st.session_state.current_page = "Follow-up Importação"
                    st.session_state.form_is_cloning = False
                    st.session_state.last_cloned_from_id = None

                st.session_state.form_reload_processes_callback() # Callback para recarregar a lista principal
                st.rerun()

        with col_cancel:
            if st.form_submit_button("❌ Cancelar"): # Ícone adicionado
                st.session_state.current_page = "Follow-up Importação"
                # Limpa apenas os estados de sessão específicos deste formulário
                if form_state_key in st.session_state:
                    del st.session_state[form_state_key]
                st.session_state.show_add_item_popup = False
                st.session_state.process_items_data = [] # Garante que itens sejam limpos
                st.session_state.last_processed_upload_key = None
                st.session_state.process_items_loaded_for_id = None 
                st.session_state.form_is_cloning = False
                st.rerun()

        with col_delete:
            if not is_new_process:
                confirm_delete = st.checkbox("✅ Confirmar exclusão", key=f"confirm_delete_process_{process_id}") # Ícone adicionado
                if st.form_submit_button("🗑️ Excluir Processo"): # Ícone adicionado
                    if confirm_delete:
                        _display_message_box("⚠️ A funcionalidade de exclusão direta por este formulário está temporariamente desabilitada. Por favor, use o botão de exclusão na tela principal de Follow-up.", "warning")
                    else:
                        st.warning("⚠️ Marque a caixa de confirmação para excluir o processo.")
            else:
                st.info("🔒 Excluir disponível após salvar o processo.")
        
    if linked_di_id is not None and linked_di_number:
        st.markdown("---")
        col1, col2 = st.columns([0.7, 0.3])
        with col1:
            st.info(f"**🔗 DI Vinculada:** {linked_di_number}")
        with col2:
            if st.button(f"👁️ Ver Detalhes da DI", key=f"view_linked_di_outside_form_{process_id}"):
                st.session_state.current_page = "Importar XML DI"
                st.session_state.selected_di_id = linked_di_id
                st.rerun()

    elif linked_di_id is not None and not linked_di_number: 
        st.markdown("---")
        st.warning(f"🔗 DI vinculada (ID: {linked_di_id}) não encontrada no banco de dados de Declarações de Importação.")


def _recalculate_all_items_if_needed(form_state_key: str):
    """
    Recalcula automaticamente todos os itens quando valores que afetam os cálculos mudarem.
    Garante que sempre use as alíquotas mais atualizadas do Firestore.
    """
    if not st.session_state.process_items_data:
        return
    
    # Valores atuais dos campos que afetam os cálculos
    current_dolar_brl = st.session_state[form_state_key].get("Estimativa_Dolar_BRL", 0.0)
    current_frete_usd = st.session_state[form_state_key].get("Estimativa_Frete_USD", 0.0)
    current_seguro_brl = st.session_state[form_state_key].get("Estimativa_Seguro_BRL", 0.0)
    
    # Valores anteriores (para detectar mudanças)
    cache_key = f"{form_state_key}_last_calc_values"
    if cache_key not in st.session_state:
        st.session_state[cache_key] = {}
    
    last_values = st.session_state[cache_key]
    
    # Verifica se houve mudanças nos valores que afetam os cálculos
    values_changed = (
        last_values.get("dolar_brl") != current_dolar_brl or
        last_values.get("frete_usd") != current_frete_usd or
        last_values.get("seguro_brl") != current_seguro_brl
    )
    
    if values_changed:
        logger.info(f"[_recalculate_all_items_if_needed] Recalculando todos os itens devido a mudanças nos valores base")
        
        # Recalcula totais
        temp_df = pd.DataFrame(st.session_state.process_items_data)
        total_invoice_value_usd = temp_df["Valor total do item"].sum() if "Valor total do item" in temp_df.columns else 0.0
        total_invoice_weight_kg = total_invoice_value_usd * 0.5  # Peso estimado baseado no valor
        
        # Recalcula impostos para todos os itens - sempre busca alíquotas atualizadas
        for item in st.session_state.process_items_data:
            calculate_item_taxes_and_values(
                item, current_dolar_brl, total_invoice_value_usd, total_invoice_weight_kg,
                current_frete_usd, current_seguro_brl
            )
        
        # Atualiza totais globais de impostos
        total_ii = total_ipi = total_pis = total_cofins = total_icms = 0.0
        for item in st.session_state.process_items_data:
            total_ii += item.get('Estimativa_II_BR', 0.0)
            total_ipi += item.get('Estimativa_IPI_BR', 0.0)
            total_pis += item.get('Estimativa_PIS_BR', 0.0)
            total_cofins += item.get('Estimativa_COFINS_BR', 0.0)
            total_icms += item.get('Estimativa_ICMS_BR', 0.0)
        
        # Atualiza os totais no estado do formulário
        st.session_state[form_state_key]['Estimativa_II_BR'] = total_ii
        st.session_state[form_state_key]['Estimativa_IPI_BR'] = total_ipi
        st.session_state[form_state_key]['Estimativa_PIS_BR'] = total_pis
        st.session_state[form_state_key]['Estimativa_COFINS_BR'] = total_cofins
        st.session_state[form_state_key]['Estimativa_ICMS_BR'] = total_icms
        st.session_state[form_state_key]['Estimativa_Impostos_Total'] = total_ii + total_ipi + total_pis + total_cofins + total_icms
        
        # Atualiza cache dos valores
        st.session_state[cache_key] = {
            "dolar_brl": current_dolar_brl,
            "frete_usd": current_frete_usd,
            "seguro_brl": current_seguro_brl
        }
        
        logger.info(f"[_recalculate_all_items_if_needed] Recálculo concluído. Totais atualizados: II=R${total_ii:.2f}, IPI=R${total_ipi:.2f}, PIS=R${total_pis:.2f}, COFINS=R${total_cofins:.2f}, ICMS=R${total_icms:.2f}")
