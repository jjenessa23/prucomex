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
from typing import Optional, Any, Dict, List, Union
import numpy as np # Importar numpy explicitamente
import base64 # Importar base64 explicitamente

import followup_db_manager as db_manager # Importa o módulo db_manager
# NOVO: Importa a nova página de formulário de processo
from app_logic import process_form_page


# Configura o logger
logger = logging.getLogger(__name__)

# Define a classe MockDbUtils globalmente, para evitar redeclarações
class MockDbUtils:
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
    
    def get_declaracao_by_process_number(self, process_number: str) -> Optional[dict]:
        """Função mock para simulação de obtenção de DI por número de processo."""
        if process_number == "MOCK-DI-123": # Exemplo de DI mock
            return {'numero_di': '9988776654', 'id': 999}
        return None

# Importa db_utils real, ou usa o mock se houver erro
db_utils: Union[Any, MockDbUtils] 
try:
    import db_utils # type: ignore # Ignora o erro de importação se o módulo não for encontrado inicialmente
    if not hasattr(db_utils, 'get_declaracao_by_id') or \
       not hasattr(db_utils, 'get_declaracao_by_process_number'):
        logger.warning("Módulo 'db_utils' real não contém funções esperadas. Usando MockDbUtils.")
        db_utils = MockDbUtils()
except ImportError:
    logger.warning("Módulo 'db_utils' não encontrado. Usando MockDbUtils.")
    db_utils = MockDbUtils()
except Exception as e:
    logger.error(f"Erro ao importar ou inicializar 'db_utils': {e}. Usando MockDbUtils.")
    db_utils = MockDbUtils()


# --- Função para definir imagem de fundo com opacidade (copiada de app_main.py) ---
def set_background_image(image_path: str):
    """Define uma imagem de fundo para o aplicativo Streamlit com opacidade."""
    try:
        with open(image_path, "rb") as image_file:
            encoded_string = base64.b64encode(image_file.read()).decode()
        st.markdown(
            f"""
            <style>
            .stApp {{
                background-color: transparent !important; /* Garante que o fundo do app seja transparente */
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
                opacity: 0.20; /* Opacidade ajustada para 20% */
                z-index: -1; /* Garante que o pseudo-elemento fique atrás do conteúdo */
            }}
            </style>
            """,
            unsafe_allow_html=True
        )
    except FileNotFoundError:
        st.warning(f"A imagem de fundo não foi encontrada no caminho: {image_path}")
    except Exception as e:
        st.error(f"Erro ao carregar a imagem de fundo: {e}")

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
        val = float(value)
        return f"R$ {val:,.2f}".replace('.', '#').replace(',', '.').replace('#', ',')
    except (ValueError, TypeError):
        return "R$ 0,00"

def _format_usd_display(value: Any) -> str:
    """Formata um valor numérico para o formato de moeda US$ X.XXX,XX."""
    try:
        val = float(value)
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

# Função para formatar o número da DI
def _format_di_number(di_number: Optional[str]) -> str:
    """Formata o número da DI para o padrão **/*******-*."""
    if di_number and isinstance(di_number, str) and len(di_number) == 10:
        return f"{di_number[0:2]}/{di_number[2:9]}-{di_number[9]}"
    return di_number if di_number is not None else ""

# Função para obter o número da DI a partir do ID
def _get_di_number_from_id(di_id: Optional[int]) -> str:
    """Obtém o número da DI a partir do seu ID no banco de dados de XML DI."""
    if di_id is None:
        return "N/A"
    di_data = db_utils.get_declaracao_by_id(di_id) # Acessa get_declaracao_by_id do db_utils
    if di_data:
        # Garante que 'numero_di' é uma string antes de passar para _format_di_number
        return _format_di_number(str(di_data.get('numero_di')))
    return "DI Não Encontrada"

# --- Funções Auxiliares ---

def _expand_all_expanders():
    """Define o estado da sessão para expandir todos os expanders."""
    st.session_state.followup_expand_all_expanders = True

def _collapse_all_expanders():
    """Define o estado da sessão para recolher todos os expanders."""
    st.session_state.followup_collapse_all_expanders = True
    st.session_state.followup_expand_all_expanders = False

def _display_delete_confirm_popup():
    """Exibe um pop-up de confirmação antes de excluir um processo."""
    if not st.session_state.get('show_delete_confirm_popup', False):
        return

    process_id_to_delete = st.session_state.get('delete_process_id_to_confirm')
    process_name_to_delete = st.session_state.get('delete_process_name_to_confirm')

    if process_id_to_delete is None:
        st.session_state.show_delete_confirm_popup = False
        return

    with st.form(key=f"delete_confirm_form_{process_id_to_delete}"):
        st.markdown(f"### Confirmar Exclusão")
        st.warning(f"Tem certeza que deseja excluir o processo '{process_name_to_delete}' (ID: {process_id_to_delete})?")
        
        col_yes, col_no = st.columns(2)
        with col_yes:
            if st.form_submit_button("Sim, Excluir"):
                _delete_process_action(process_id_to_delete)
        with col_no:
            if st.form_submit_button("Não, Cancelar"):
                st.session_state.show_delete_confirm_popup = False
                st.session_state.delete_process_id_to_confirm = None
                st.session_state.delete_process_name_to_confirm = None
                st.rerun()

def _load_processes():
    """Carrega os processos do DB aplicando filtros e termos de pesquisa."""
    # Verificação robusta para o caminho do DB
    if not hasattr(db_manager, 'get_followup_db_path') or not db_manager.get_followup_db_path(): # type: ignore
        st.warning("Caminho do banco de dados de Follow-up não configurado. Por favor, selecione um DB.")
        st.session_state.followup_processes_data = []
        return

    conn = db_manager.conectar_followup_db()
    if conn:
        try:
            db_manager.criar_tabela_followup(conn)
        except Exception as e:
            st.error(f"Erro ao criar/verificar tabelas do DB de Follow-up: {e}")
        finally:
            conn.close()
    else:
        st.error("Não foi possível conectar ao banco de dados de Follow-up.")
        st.session_state.followup_processes_data = []
        return

    selected_status_filter = st.session_state.get('followup_status_filter', 'Todos')
    search_terms = st.session_state.get('followup_search_terms', {})

    processes_raw = db_manager.obter_processos_filtrados(selected_status_filter, search_terms)
    
    processes_dicts = [dict(row) for row in processes_raw]

    st.session_state.followup_processes_data = processes_dicts
    _update_status_filter_options()

def _update_status_filter_options():
    """Atualiza as opções do filtro de status com base nos status do DB."""
    # Acesso a obter_status_gerais_distintos do db_manager
    status_from_db = db_manager.obter_status_gerais_distintos()
    all_status_options = ["Todos", "Arquivados"] + sorted([s for s in status_from_db if s not in ["Todos", "Arquivados"]])
    st.session_state.followup_all_status_options = all_status_options

def _import_file_action(uploaded_file: Any) -> bool:
    """
    Ação de importar arquivo CSV/Excel.
    Esta função agora processará o DataFrame diretamente para lidar com formatações.
    """
    if uploaded_file is None:
        return False

    file_extension = os.path.splitext(uploaded_file.name)[1]
    df = None

    try:
        if file_extension.lower() in ('.csv'):
            try:
                df = pd.read_csv(uploaded_file, encoding='utf-8')
            except UnicodeDecodeError:
                df = pd.read_csv(uploaded_file, encoding='latin-1')
            except Exception:
                df = pd.read_csv(uploaded_file, sep=';')
        elif file_extension.lower() in ('.xlsx', '.xls'):
            df = pd.read_excel(uploaded_file)
        else:
            st.error("Formato de arquivo não suportado. Por favor, use .csv, .xls ou .xlsx.")
            return False

        df_processed = _preprocess_dataframe_for_db(df)

        if df_processed is None: # Se o pré-processamento falhou
            st.error("Falha no pré-processamento dos dados do arquivo local.")
            return False

        if db_manager.importar_csv_para_db_from_dataframe(df_processed):
            st.success("Dados do arquivo local importados com sucesso! A tabela foi recarregada.")
            _load_processes()
            return True
        else:
            st.error("Falha ao importar dados do arquivo local para o banco de dados.")
            return False

    except Exception as e:
        st.error(f"Erro ao processar o arquivo local: {e}")
        logger.exception("Erro durante a importação do arquivo local.")
        return False


def _open_edit_process_popup(process_identifier: Optional[Any] = None):
    """
    Navega para a página dedicada de formulário de processo, passando os dados
    necessários via session_state.
    """
    st.session_state.form_process_identifier = process_identifier
    st.session_state.form_reload_processes_callback = _load_processes
    st.session_state.current_page = "Formulário Processo"
    # Ensure all other popups are closed when navigating to a new main page
    st.session_state.show_filter_search_popup = False
    st.session_state.show_import_popup = False
    st.session_state.show_delete_confirm_popup = False
    st.session_state.show_mass_edit_popup = False
    st.rerun()


def _delete_process_action(process_id: int):
    """Exclui um processo do banco de dados."""
    if db_manager.excluir_processo(process_id):
        st.success(f"Processo ID {process_id} excluído com sucesso!")
        st.session_state.show_delete_confirm_popup = False
        st.session_state.delete_process_id_to_confirm = None
        st.session_state.delete_process_name_to_confirm = None
        st.session_state.followup_selected_process_id = None
        _load_processes()
        st.rerun()
    else:
        st.error(f"Falha ao excluir processo ID {process_id}.")

def _archive_process_action(process_id: int):
    """Marca um processo como arquivado no banco de dados."""
    if db_manager.arquivar_processo(process_id):
        st.success(f"Processo ID {process_id} arquivado com sucesso!")
        st.session_state.followup_selected_process_id = None
        _load_processes()
        st.rerun()
    else:
        st.error(f"Falha ao arquivar processo ID {process_id}.")

def _unarchive_process_action(process_id: int):
    """Marca um processo como não arquivado (define Status_Arquivado para NULL)."""
    if db_manager.desarquivar_processo(process_id):
        st.success(f"Processo ID {process_id} desarquivado com sucesso!")
        st.session_state.followup_selected_process_id = None
        _load_processes()
        st.rerun()
    else:
        st.error(f"Falha ao desarquivar processo ID {process_id}.")

def _update_status_action(process_id: int, novo_status: Optional[str]):
    """Atualiza o Status_Geral de um processo específico."""
    original_process_data = db_manager.obter_processo_por_id(process_id)
    original_status = original_process_data['Status_Geral'] if original_process_data else None
    
    if db_manager.atualizar_status_processo(process_id, novo_status):
        st.success(f"Status do processo ID {process_id} atualizado para '{novo_status}'.")
        user_info = st.session_state.get('user_info', {'username': 'Desconhecido'})
        username = user_info.get('username')
        db_manager.inserir_historico_processo(process_id, "Status_Geral", original_status, novo_status, username)
        _load_processes()
        st.rerun()
    else:
        st.error(f"Falha ao atualizar status do processo ID {process_id}.")

def _preprocess_dataframe_for_db(df: pd.DataFrame) -> Optional[pd.DataFrame]:
    """
    Realiza o pré-processamento e padronização dos dados do DataFrame
    para o formato esperado pelo banco de dados.
    """
    df_processed = df.copy()

    column_mapping_to_db = {
        "Process Reference": "Processo_Novo",
        "Supplier": "Fornecedor",
        "Type of Item": "Tipos_de_item",
        "INV/Invoice": "N_Invoice",
        "Qtd": "Quantidade",
        "Value USD": "Valor_USD",
        "Paid?": "Pago",
        "P/O": "N_Ordem_Compra",
        "Purchase Date (YYYY-MM-DD)": "Data_Compra",
        "Est. Imposts": "Estimativa_Impostos_BR", # Este campo será mantido no DB, mas não exibido na tabela principal
        "Est. Freight.": "Estimativa_Frete_USD",
        "Shipping Date (YYYY-MM-DD)": "Data_Embarque",
        "Shipping Company": "Agente_de_Carga_Novo", 
        "Status": "Status_Geral",
        "ETA Pichau (YYYY-MM-DD)": "Previsao_Pichau",
        "Modal": "Modal",
        "Navio": "Navio",
        "Origin": "Origem",
        "Destination": "Destino",
        "INCOTERM": "INCOTERM",
        "Buyer": "Comprador",
        "Docs Reviewed (Sim/Não)": "Documentos_Revisados",
        "BL/AWB (Sim/Não)": "Conhecimento_Embarque",
        "Description Done (Sim/Não)": "Descricao_Feita",
        "Description Sent (Sim/Não)": "Descricao_Enviada",
        "Folder Path": "Caminho_da_pasta",
        "ETA Recinto (YYYY-MM-DD)": "ETA_Recinto",
        "Data Registro (YYYY-MM-DD)": "Data_Registro",
        "Obs": "Observacao",
        "DI Vinculada ID": "DI_ID_Vinculada", # Este campo será mantido no DB, mas não exibido na tabela principal
        "Nota feita": "Nota_feita", # Nova coluna
        "Conferido": "Conferido", # Nova coluna, se aplicável
    }

    df_processed = df_processed.rename(columns=column_mapping_to_db, errors='ignore')

    db_col_names = db_manager.obter_nomes_colunas_db()
    db_col_names_without_id = [col for col in db_col_names if col != 'id']

    date_columns_to_process = ["Data_Compra", "Data_Embarque", "Previsao_Pichau", "ETA_Recinto", "Data_Registro"]
    for col in date_columns_to_process:
        if col in df_processed.columns:
            df_processed[col] = pd.to_datetime(df_processed[col], errors='coerce', dayfirst=True)
            df_processed[col] = df_processed[col].dt.strftime('%Y-%m-%d')
            df_processed[col] = df_processed[col].replace({pd.NaT: None})

    numeric_columns = ["Quantidade", "Valor_USD", "Estimativa_Impostos_BR", "Estimativa_Frete_USD", "DI_ID_Vinculada", "Estimativa_Impostos_Total"] # Adicionado Estimativa_Impostos_Total
    for col in numeric_columns:
        if col in df_processed.columns:
            if df_processed[col].dtype == 'object':
                df_processed[col] = df_processed[col].astype(str).str.replace('.', '', regex=False).str.replace(',', '.', regex=False)
            df_processed[col] = pd.to_numeric(df_processed[col], errors='coerce').fillna(0)
            if col == "Quantidade" or col == "DI_ID_Vinculada":
                df_processed[col] = df_processed[col].astype(int)
            else:
                df_processed[col] = df_processed[col].astype(float)

    yes_no_columns = [
        "Pago", "Documentos_Revisados", "Conhecimento_Embarque",
        "Descricao_Feita", "Descricao_Enviada", "Nota_feita", "Conferido" # Adicionada "Nota_feita" e "Conferido"
    ]
    for col in yes_no_columns:
        if col in df_processed.columns:
            df_processed[col] = df_processed[col].astype(str).str.strip().str.lower()
            df_processed[col] = df_processed[col].apply(
                lambda x: "Sim" if x in ["sim", "s"] else ("Não" if x in ["nao", "não", "n"] else None)
            )
            
    for col in df_processed.columns:
        if col not in numeric_columns + date_columns_to_process + yes_no_columns:
            df_processed[col] = df_processed[col].astype(str).replace({'': np.nan, 'nan': np.nan}) 
            df_processed[col] = df_processed[col].apply(lambda x: None if pd.isna(x) else x)
            
    final_df_for_db = pd.DataFrame(columns=db_col_names_without_id)
    for col in db_col_names_without_id:
        if col in df_processed.columns:
            final_df_for_db[col] = df_processed[col]
        else:
            final_df_for_db[col] = None

    return final_df_for_db

def _open_filter_search_popup():
    """Abre um pop-up para a seleção de filtros e termos de pesquisa."""
    st.session_state.show_filter_search_popup = True
    st.rerun()

def _display_filter_search_popup():
    """Exibe o pop-up de filtros e pesquisa."""
    if not st.session_state.get('show_filter_search_popup', False):
        return

    with st.form(key="filter_search_form"):
        st.markdown("### Filtros e Pesquisa de Processos")

        current_filter_value = st.session_state.get('followup_status_filter', 'Todos')
        try:
            default_index = st.session_state.followup_all_status_options.index(current_filter_value)
        except ValueError:
            default_index = 0

        st.selectbox(
            "Filtrar por Status:",
            options=st.session_state.followup_all_status_options,
            index=default_index,
            key="popup_followup_status_filter"
        )

        st.text_input("Pesquisar Processo:", key="popup_followup_search_processo_novo", 
                      value=st.session_state.get('followup_search_terms', {}).get('Processo_Novo', '') or "")
        st.text_input("Pesquisar Fornecedor:", key="popup_followup_search_fornecedor",
                      value=st.session_state.get('followup_search_terms', {}).get('Fornecedor', '') or "")
        st.text_input("Pesquisar Nº Invoice:", key="popup_followup_search_n_invoice",
                      value=st.session_state.get('followup_search_terms', {}).get('N_Invoice', '') or "")
        
        col_buttons_popup = st.columns(2)
        with col_buttons_popup[0]:
            if st.form_submit_button("Aplicar Filtros"):
                st.session_state.followup_status_filter = st.session_state.popup_followup_status_filter
                st.session_state.followup_search_terms = {
                    "Processo_Novo": st.session_state.popup_followup_search_processo_novo,
                    "Fornecedor": st.session_state.popup_followup_search_fornecedor,
                    "N_Invoice": st.session_state.popup_followup_search_n_invoice,
                }
                _load_processes()
                st.session_state.show_filter_search_popup = False
                st.rerun()
        with col_buttons_popup[1]:
            if st.form_submit_button("Limpar Pesquisa e Filtros"):
                st.session_state.followup_status_filter = 'Todos'
                st.session_state.followup_search_terms = {}
                st.session_state.popup_followup_search_processo_novo = ""
                st.session_state.popup_followup_search_fornecedor = ""
                st.session_state.popup_followup_search_n_invoice = ""
                _load_processes()
                st.session_state.show_filter_search_popup = False
                st.rerun()
        
        if st.form_submit_button("Fechar"):
            st.session_state.show_filter_search_popup = False
            st.rerun()

def _generate_excel_template():
    """Gera um arquivo Excel padrão para inserção de dados de Follow-up."""
    template_columns_map = {
        "Processo_Novo": "Process Reference",
        "Fornecedor": "Supplier",
        "Tipos_de_item": "Type of Item",
        "N_Invoice": "INV/Invoice",
        "Qtd": "Qtd",
        "Value USD": "Value USD",
        "Paid?": "Paid?",
        "P/O": "P/O",
        "Purchase Date (YYYY-MM-DD)": "Purchase Date (YYYY-MM-DD)",
        "Est. Imposts": "Est. Imposts", # Mantido no template para compatibilidade, mas a exibição principal usará 'Estimativa_Impostos_Total'
        "Est. Freight.": "Est. Freight.",
        "Shipping Date (YYYY-MM-DD)": "Shipping Date (YYYY-MM-DD)",
        "Shipping Company": "Shipping Company", 
        "Status": "Status",
        "ETA Pichau (YYYY-MM-DD)": "ETA Pichau (YYYY-MM-DD)",
        "Modal": "Modal",
        "Navio": "Navio",
        "Origin": "Origin",
        "Destination": "Destination",
        "INCOTERM": "INCOTERM",
        "Buyer": "Buyer",
        "Docs Reviewed (Sim/Não)": "Docs Reviewed (Sim/Não)",
        "BL/AWB (Sim/Não)": "BL/AWB (Sim/Não)",
        "Description Done (Sim/Não)": "Description Done (Sim/Não)",
        "Description Sent (Sim/Não)": "Description Sent (Sim/Não)",
        "Caminho_da_pasta": "Folder Path",
        "ETA Recinto (YYYY-MM-DD)": "ETA Recinto (YYYY-MM-DD)",
        "Data Registro (YYYY-MM-DD)": "Data Registro (YYYY-MM-DD)",
        "Observacao": "Obs",
        "DI Vinculada ID": "DI Vinculada ID", # Mantido no template para compatibilidade, mas removido da exibição principal
        "Nota feita": "Nota feita", # Nova coluna no template
        "Conferido": "Conferido", # Nova coluna no template
        "Estimativa Impostos Total": "Estimativa_Impostos_Total", # Nova coluna no template
    }

    df_template = pd.DataFrame(columns=list(template_columns_map.values()))

    example_row = {
        "Process Reference": "EXEMPLO-001",
        "Supplier": "Exemplo Fornecedor Ltda.",
        "Type of Item": "Eletrônicos",
        "INV/Invoice": "INV-2023-001",
        "Qtd": 100,
        "Value USD": 15000.00,
        "Paid?": "Não",
        "P/O": "PO-XYZ-456",
        "Purchase Date (YYYY-MM-DD)": "2023-01-15",
        "Est. Imposts": 5000.00,
        "Est. Freight.": 1200.00,
        "Shipping Date (YYYY-MM-DD)": "2023-02-01",
        "Shipping Company": "Agente ABC",
        "Status": "Processo Criado",
        "ETA Pichau (YYYY-MM-DD)": "2023-03-10",
        "Modal": "Maritimo",
        "Navio": "Navio Exemplo",
        "Origin": "China",
        "Destination": "Brasil",
        "INCOTERM": "FOB",
        "Buyer": "Comprador X",
        "Docs Reviewed (Sim/Não)": "Não",
        "BL/AWB (Sim/Não)": "Sim",
        "Description Done (Sim/Não)": "Não",
        "Description Sent (Sim/Não)": "Não",
        "Folder Path": "C:\\Exemplo\\Pasta\\Processo_EXEMPLO-001",
        "ETA Recinto (YYYY-MM-DD)": "2023-03-05",
        "Data Registro (YYYY-MM-DD)": "2023-03-08",
        "Obs": "Observação de exemplo para o processo.",
        "DI Vinculada ID": "",
        "Nota feita": "Não", # Exemplo no template
        "Conferido": "Não", # Exemplo no template
        "Estimativa Impostos Total": 5000.00, # Exemplo no template
    }
    df_template = pd.DataFrame([example_row], columns=list(template_columns_map.values()))

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df_template.to_excel(writer, index=False, sheet_name='Follow-up Template')
    output.seek(0)

    st.download_button(
        label="Baixar Template Excel",
        data=output,
        file_name="followup_template.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key="download_excel_template"
    )

def _get_gspread_client():
    """Autentica e retorna um cliente gspread para interagir com o Google Sheets."""
    try:
        if "gcp_service_account" not in st.secrets:
            st.error("Credenciais do Google Cloud (gcp_service_account) não encontradas em .streamlit/secrets.toml. Por favor, configure.")
            return None

        creds_json = st.secrets["gcp_service_account"]
        
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_json, scope)
        
        client = gspread.authorize(creds)
        return client
    except Exception as e:
        logger.error(f"Erro ao autenticar gspread: {e}")
        st.error(f"Erro de autenticação com Google Sheets. Verifique suas credenciais em .streamlit/secrets.toml e as permissões da conta de serviço. Detalhes: {e}")
        return None

def _import_from_google_sheets(sheet_url_or_id: str, worksheet_name: str) -> bool:
    """Importa dados de uma planilha Google Sheets para o banco de dados."""
    client = _get_gspread_client()
    if not client:
        return False

    try:
        if "https://" in sheet_url_or_id:
            spreadsheet = client.open_by_url(sheet_url_or_id)
        else:
            spreadsheet = client.open_by_key(sheet_url_or_id)
        
        worksheet = spreadsheet.worksheet(worksheet_name)
        
        data = worksheet.get_all_records(value_render_option='UNFORMATTED_VALUE', head=1)
        
        if not data:
            st.warning(f"A aba '{worksheet_name}' na planilha '{sheet_url_or_id}' está vazia.")
            return False

        df_from_gsheets = pd.DataFrame(data)

        df_processed = _preprocess_dataframe_for_db(df_from_gsheets)

        if df_processed is None:
            st.error("Falha no pré-processamento dos dados do Google Sheets.")
            return False

        if db_manager.importar_csv_para_db_from_dataframe(df_processed):
            st.success("Dados do Google Sheets importados com sucesso! A tabela foi recarregada.")
            _load_processes()
            return True
        else:
            st.error("Falha ao importar dados do Google Sheets para o banco de dados.")
            return False
    
    except gspread.exceptions.SpreadsheetNotFound:
        st.error(f"Planilha Google Sheets não encontrada com ID/URL: {sheet_url_or_id}. Verifique o ID/URL e as permissões.")
        logger.error(f"SpreadsheetNotFound: {sheet_url_or_id}")
        return False
    except gspread.exceptions.WorksheetNotFound:
        st.error(f"Aba '{worksheet_name}' não encontrada na planilha. Verifique o nome da aba.")
        logger.error(f"WorksheetNotFound: {worksheet_name}")
        return False
    except Exception as e:
        st.error(f"Erro ao ler ou importar dados do Google Sheets: {e}")
        logger.exception("Erro inesperado ao importar do Google Sheets.")
        return False

def _display_import_popup():
    """Exibe o pop-up unificado para importação via Google Sheets ou Excel/CSV."""
    if not st.session_state.get('show_import_popup', False):
        return

    with st.form(key="import_popup_form"):
        st.markdown("### Opções de Importação")

        st.markdown("#### Importar do Google Sheets")
        st.info("Insira a URL ou ID da planilha e o nome da aba.")
        st.session_state.gsheets_url_id = st.text_input("URL ou ID da Planilha:", value=st.session_state.gsheets_url_id, key="popup_gsheets_url_id")
        st.session_state.gsheets_worksheet_name = st.text_input("Nome da Aba:", value=st.session_state.gsheets_worksheet_name, key="popup_gsheets_worksheet_name")
        
        confirm_gsheets_overwrite = st.checkbox("Confirmar substituição de dados no DB (Google Sheets)", key="popup_confirm_gsheets_overwrite")

        if st.form_submit_button("Importar Planilha do Google Sheets"):
            if st.session_state.popup_gsheets_url_id and st.session_state.popup_gsheets_worksheet_name:
                if confirm_gsheets_overwrite:
                    if _import_from_google_sheets(st.session_state.popup_gsheets_url_id, st.session_state.popup_gsheets_worksheet_name):
                        st.session_state.show_import_popup = False
                        st.rerun()
                else:
                    st.warning("Marque a caixa de confirmação para importar do Google Sheets.")
            else:
                st.warning("Por favor, forneça a URL/ID da Planilha e o Nome da Aba para Google Sheets.")

        st.markdown("---")

        st.markdown("#### Importar de Arquivo Excel/CSV Local")
        uploaded_file = st.file_uploader("Escolha um arquivo (.csv, .xls, .xlsx)", type=["csv", "xls", "xlsx"], key="file_uploader_local")
        
        confirm_local_overwrite = st.checkbox("Confirmar substituição de dados no DB (Arquivo Local)", key="popup_confirm_local_overwrite")

        if st.form_submit_button("Importar Arquivo Local"):
            if uploaded_file is not None:
                if confirm_local_overwrite:
                    if _import_file_action(uploaded_file):
                        st.session_state.show_import_popup = False
                        st.rerun()
                else:
                    st.warning("Marque a caixa de confirmação para importar o arquivo local.")
            else:
                st.warning("Por favor, selecione um arquivo para importação local.")
        
        if st.form_submit_button("Fechar Opções de Importação"):
            st.session_state.show_import_popup = False
            st.rerun()

    st.markdown("---")
    _generate_excel_template()

def _open_mass_edit_popup():
    """Abre o pop-up para edição em massa de processos."""
    st.session_state.show_mass_edit_popup = True
    if 'mass_edit_process_names_input' not in st.session_state:
        st.session_state.mass_edit_process_names_input = ""
    if 'mass_edit_found_processes' not in st.session_state:
        st.session_state.mass_edit_found_processes = []
    st.rerun()

def _display_mass_edit_popup():
    """Exibe o pop-up para edição em massa de processos."""
    if not st.session_state.get('show_mass_edit_popup', False):
        return

    with st.form(key="mass_edit_form"):
        st.markdown("### Editar Múltiplos Processos")

        st.markdown("#### 1. Inserir Processos para Edição")
        process_names_input = st.text_area(
            "Insira os nomes dos processos (um por linha):",
            value=st.session_state.mass_edit_process_names_input,
            height=150,
            key="mass_edit_process_names_textarea"
        )
        
        if st.form_submit_button("Buscar Processos"):
            st.session_state.mass_edit_process_names_input = process_names_input
            
            st.session_state.mass_edit_found_processes = []
            if process_names_input:
                names_to_search = [name.strip() for name in process_names_input.split('\n') if name.strip()]
                for name in names_to_search:
                    process_data_row = db_manager.obter_processo_by_processo_novo(name)
                    
                    found_entry = {
                        'Processo_Novo': name,
                        'ID': 'Não encontrado',
                        'Status da Busca': 'Não encontrado',
                        'Status_Geral': 'N/A',
                        'Observacao': 'N/A',
                        'Previsao_Pichau': 'N/A',
                        'Data_Embarque': 'N/A',
                        'ETA_Recinto': 'N/A',
                        'Data_Registro': 'N/A',
                        'Estimativa_Impostos_Total': 'N/A', # Adicionado para exibição na busca em massa
                        'Nota_feita': 'N/A', # Adicionado para exibição na busca em massa
                    }

                    if process_data_row:
                        process_data = dict(process_data_row) 
                        found_entry['Processo_Novo'] = process_data['Processo_Novo']
                        found_entry['ID'] = process_data['id']
                        found_entry['Status da Busca'] = 'Encontrado'
                        found_entry['Status_Geral'] = process_data.get('Status_Geral', 'N/A')
                        found_entry['Observacao'] = process_data.get('Observacao', 'N/A')
                        found_entry['Previsao_Pichau'] = _format_date_display(process_data.get('Previsao_Pichau'))
                        found_entry['Data_Embarque'] = _format_date_display(process_data.get('Data_Embarque'))
                        found_entry['ETA_Recinto'] = _format_date_display(process_data.get('ETA_Recinto'))
                        found_entry['Data_Registro'] = _format_date_display(process_data.get('Data_Registro'))
                        found_entry['Estimativa_Impostos_Total'] = _format_currency_display(process_data.get('Estimativa_Impostos_Total'))
                        found_entry['Nota_feita'] = process_data.get('Nota_feita', 'N/A')
                    
                    st.session_state.mass_edit_found_processes.append(found_entry)
            st.rerun()

        if st.session_state.mass_edit_found_processes:
            st.markdown("#### Resultados da Busca:")
            df_found_processes = pd.DataFrame(st.session_state.mass_edit_found_processes)
            
            display_cols_search_results = [
                "Processo_Novo", "Status_Geral", "Observacao", 
                "Previsao_Pichau", "Data_Embarque", "ETA_Recinto", "Data_Registro", "ID", "Status da Busca", 
                "Estimativa_Impostos_Total", "Nota_feita" # Adicionado Nota_feita aqui
            ]
            
            display_col_names_map = {
                "Processo_Novo": "Processo",
                "Status_Geral": "Status Geral",
                "Observacao": "Observação",
                "Previsao_Pichau": "Previsão na Pichau",
                "Data_Embarque": "Data do Embarque",
                "ETA_Recinto": "ETA no Recinto",
                "Data de Registro": "Data de Registro",
                "ID": "ID do DB",
                "Status da Busca": "Status da Busca",
                "Estimativa_Impostos_Total": "Imp. Totais (R$)",
                "Nota_feita": "Nota feita", # Mapeamento para Nota_feita
            }
            
            df_display_search_results = df_found_processes[[col for col in display_cols_search_results if col in df_found_processes.columns]].rename(columns=display_col_names_map)

            st.dataframe(
                df_display_search_results,
                hide_index=True,
                use_container_width=True,
                column_config={
                    "Processo": st.column_config.TextColumn("Processo", width="medium"),
                    "Status Geral": st.column_config.TextColumn("Status Geral", width="small"),
                    "Observação": st.column_config.TextColumn("Observação", width="medium"),
                    "Previsão na Pichau": st.column_config.TextColumn("Previsão na Pichau", width="small"),
                    "Data do Embarque": st.column_config.TextColumn("Data do Embarque", width="small"),
                    "ETA no Recinto": st.column_config.TextColumn("ETA no Recinto", width="small"),
                    "Data de Registro": st.column_config.TextColumn("Data de Registro", width="small"),
                    "ID do DB": st.column_config.TextColumn("ID do DB", width="small"),
                    "Status da Busca": st.column_config.TextColumn("Status da Busca", width="small"),
                    "Imp. Totais (R$)": st.column_config.TextColumn("Imp. Totais (R$)", width="small"),
                    "Nota feita": st.column_config.TextColumn("Nota feita", width="small"), # Configuração da coluna Nota feita
                }
            )
            
            processes_to_edit_ids = [p['ID'] for p in st.session_state.mass_edit_found_processes if p['ID'] != 'Não encontrado']
            
            if not processes_to_edit_ids:
                st.warning("Nenhum processo válido encontrado para edição. Por favor, corrija os nomes e tente novamente.")
                st.session_state.mass_edit_can_proceed = False
            else:
                st.session_state.mass_edit_can_proceed = True
                st.markdown("---")
                st.markdown("#### 2. Selecionar Novos Valores")

                new_status_geral = st.selectbox(
                    "Novo Status Geral:",
                    options=[""] + db_manager.STATUS_OPTIONS,
                    key="mass_edit_new_status_value"
                )
                if new_status_geral == "":
                    new_status_geral = None

                if 'mass_edit_observacao_touched' not in st.session_state:
                    st.session_state.mass_edit_observacao_touched = False

                new_observacao_input = st.text_area(
                    "Nova Observação:",
                    value="",
                    key="mass_edit_new_observacao_value"
                )

                if new_observacao_input != "":
                    st.session_state.mass_edit_observacao_touched = True
                elif st.session_state.mass_edit_observacao_touched and new_observacao_input == "":
                    pass
                else:
                    st.session_state.mass_edit_observacao_touched = False

                new_previsao_pichau_date = st.date_input(
                    "Nova Previsão na Pichau:",
                    value=None,
                    key="mass_edit_new_previsao_pichau_value",
                    format="DD/MM/YYYY"
                )
                new_previsao_pichau = new_previsao_pichau_date.strftime("%Y-%m-%d") if new_previsao_pichau_date else None

                new_data_embarque_date = st.date_input(
                    "Nova Data do Embarque:",
                    value=None,
                    key="mass_edit_new_data_embarque_value",
                    format="DD/MM/YYYY"
                )
                new_data_embarque = new_data_embarque_date.strftime("%Y-%m-%d") if new_data_embarque_date else None

                new_eta_recinto_date = st.date_input(
                    "Nova ETA no Recinto:",
                    value=None,
                    key="mass_edit_new_eta_recinto_value",
                    format="DD/MM/YYYY"
                )
                new_eta_recinto = new_eta_recinto_date.strftime("%Y-%m-%d") if new_eta_recinto_date else None

                new_data_registro_date = st.date_input(
                    "Nova Data de Registro:",
                    value=None,
                    key="mass_edit_new_data_registro_value",
                    format="DD/MM/YYYY"
                )
                new_data_registro = new_data_registro_date.strftime("%Y-%m-%d") if new_data_registro_date else None

                new_nota_feita = st.selectbox( # Novo campo para edição em massa
                    "Nova Nota feita?:",
                    options=["", "Não", "Sim"],
                    key="mass_edit_new_nota_feita_value"
                )
                if new_nota_feita == "":
                    new_nota_feita = None

                col_save, col_cancel = st.columns(2)

                with col_save:
                    if st.form_submit_button("Aplicar Alterações", disabled=not st.session_state.mass_edit_can_proceed):
                        if not processes_to_edit_ids:
                            st.warning("Nenhum processo válido selecionado para edição.")
                        else:
                            user_info = st.session_state.get('user_info', {'username': 'Desconhecido'})
                            username = user_info.get('username')

                            successful_updates_count = 0
                            for p_id in processes_to_edit_ids:
                                original_process_data_row = db_manager.obter_processo_por_id(p_id)
                                if original_process_data_row:
                                    original_process_data = dict(original_process_data_row)
                                    
                                    changes_to_apply = {}

                                    if new_status_geral is not None:
                                        changes_to_apply["Status_Geral"] = new_status_geral
                                    
                                    if st.session_state.mass_edit_observacao_touched:
                                        changes_to_apply["Observacao"] = new_observacao_input if new_observacao_input != "" else None
                                    
                                    if new_previsao_pichau is not None:
                                        changes_to_apply["Previsao_Pichau"] = new_previsao_pichau
                                    if new_data_embarque is not None:
                                        changes_to_apply["Data_Embarque"] = new_data_embarque
                                    if new_eta_recinto is not None:
                                        changes_to_apply["ETA_Recinto"] = new_eta_recinto
                                    if new_data_registro is not None:
                                        changes_to_apply["Data_Registro"] = new_data_registro
                                    if new_nota_feita is not None: # Aplicar mudança para Nota_feita
                                        changes_to_apply["Nota_feita"] = new_nota_feita

                                    if not changes_to_apply:
                                        st.info(f"Nenhuma alteração detectada para o processo {original_process_data.get('Processo_Novo', 'N/A')} (ID: {p_id}).")
                                        continue

                                    db_col_names_full = db_manager.obter_nomes_colunas_db()
                                    data_tuple_for_db = []
                                    for col_name in db_col_names_full:
                                        if col_name == 'id':
                                            continue
                                        if col_name in changes_to_apply:
                                            data_tuple_for_db.append(changes_to_apply[col_name])
                                        else:
                                            data_tuple_for_db.append(original_process_data.get(col_name))

                                    if db_manager.atualizar_processo(p_id, tuple(data_tuple_for_db)):
                                        successful_updates_count += 1
                                        for field_name, new_val in changes_to_apply.items():
                                            db_manager.inserir_historico_processo(p_id, field_name, original_process_data.get(field_name), new_val, username)
                                    else:
                                        st.error(f"Falha ao atualizar processo ID {p_id}.")
                                else:
                                    st.error(f"Processo ID {p_id} não encontrado para atualização.")

                            if successful_updates_count > 0:
                                st.success(f"{successful_updates_count} processos atualizados com sucesso!")
                                st.session_state.show_mass_edit_popup = False
                                st.session_state.mass_edit_process_names_input = ""
                                st.session_state.mass_edit_found_processes = []
                                st.session_state.mass_edit_observacao_touched = False
                                _load_processes()
                                st.rerun()
                            else:
                                st.warning("Nenhum processo foi atualizado ou nenhuma alteração foi detectada para aplicar.")

                with col_cancel:
                    if st.form_submit_button("Cancelar"):
                        st.session_state.show_mass_edit_popup = False
                        st.session_state.mass_edit_process_names_input = ""
                        st.session_state.mass_edit_found_processes = []
                        st.session_state.mass_edit_observacao_touched = False
                        st.rerun()
        else:
            col_empty, col_cancel_only = st.columns([0.7, 0.3])
            with col_cancel_only:
                if st.form_submit_button("Fechar"):
                    st.session_state.show_mass_edit_popup = False
                    st.session_state.mass_edit_process_names_input = ""
                    st.session_state.mass_edit_found_processes = []
                    st.session_state.mass_edit_observacao_touched = False
                    st.rerun()


def show_page():
    """Função principal para exibir a página de Follow-up de Importação."""
    background_image_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'assets', 'logo_navio_atracado.png')
    set_background_image(background_image_path)

    st.subheader("Follow-up Importação")

    # Inicialização dos estados de sessão, garantindo que existem
    if 'followup_processes_data' not in st.session_state:
        st.session_state.followup_processes_data = []
    if 'followup_selected_process_id' not in st.session_state:
        st.session_state.followup_selected_process_id = None
    if 'followup_status_filter' not in st.session_state:
        st.session_state.followup_status_filter = 'Todos'
    if 'followup_search_terms' not in st.session_state:
        st.session_state.followup_search_terms = {}
    if 'followup_all_status_options' not in st.session_state:
        st.session_state.followup_all_status_options = db_manager.STATUS_OPTIONS + ["Todos", "Arquivados"]
    # Removido show_followup_edit_popup e followup_editing_process_id daqui, pois serão gerenciados pela navegação de página
    if 'show_filter_search_popup' not in st.session_state:
        st.session_state.show_filter_search_popup = False
    if 'gsheets_url_id' not in st.session_state:
        st.session_state.gsheets_url_id = ""
    if 'gsheets_worksheet_name' not in st.session_state:
        st.session_state.gsheets_worksheet_name = "Sheet1"
    if 'show_delete_confirm_popup' not in st.session_state:
        st.session_state.show_delete_confirm_popup = False
    if 'delete_process_id_to_confirm' not in st.session_state:
        st.session_state.delete_process_id_to_confirm = None
    if 'delete_process_name_to_confirm' not in st.session_state:
        st.session_state.delete_process_name_to_confirm = None
    if 'show_import_popup' not in st.session_state:
        st.session_state.show_import_popup = False
    if 'followup_expand_all_expanders' not in st.session_state:
        st.session_state.followup_expand_all_expanders = False
    if 'show_mass_edit_popup' not in st.session_state:
        st.session_state.show_mass_edit_popup = False
    if 'mass_edit_process_names_input' not in st.session_state:
        st.session_state.mass_edit_process_names_input = ""
    if 'mass_edit_found_processes' not in st.session_state:
        st.session_state.mass_edit_found_processes = []
    if 'mass_edit_can_proceed' not in st.session_state:
        st.session_state.mass_edit_can_proceed = False

    # Exibe pop-ups que não são de edição de processo
    _display_filter_search_popup()
    _display_import_popup()
    _display_delete_confirm_popup()
    _display_mass_edit_popup()

    # Se qualquer popup (exceto o de edição de processo, que agora é uma página) estiver visível,
    # não renderiza o restante da página principal para evitar sobreposição.
    if st.session_state.get('show_filter_search_popup', False) or \
       st.session_state.get('show_import_popup', False) or \
       st.session_state.get('show_delete_confirm_popup', False) or \
       st.session_state.get('show_mass_edit_popup', False):
        return # Impede a renderização da página principal enquanto um popup estiver ativo

    _load_processes() 

    st.markdown("---")
    
    col1_add, col1_filter, col1_mass_edit = st.columns([0.032, 0.03, 0.15]) 
    with col1_add:
        if st.button("Adicionar Novo Processo", key="add_new_process_button"):
            _open_edit_process_popup(None) # Chamará a nova página de formulário
    with col1_filter:
        if st.button("Filtros e Pesquisa", key="open_filter_search_popup_button"):
            _open_filter_search_popup()
    with col1_mass_edit:
        if st.button("Editar Múltiplos Processos", key="mass_edit_processes_button"):
            _open_mass_edit_popup()

    col2_search_select, col2_clear_search = st.columns([0.5, 0.2]) 
    with col2_search_select:
        process_name_to_id_map = {p['Processo_Novo']: p['id'] for p in st.session_state.followup_processes_data if p.get('Processo_Novo')}
        sorted_process_names = [""] + sorted(process_name_to_id_map.keys())

        current_search_term_for_selectbox = st.session_state.get('followup_search_terms', {}).get('Processo_Novo', '') or ""
        try:
            default_selectbox_index = sorted_process_names.index(current_search_term_for_selectbox)
        except ValueError:
            default_selectbox_index = 0

        edited_process_name_selected = st.selectbox(
            "Pesquisar e Abrir para Editar:", 
            options=sorted_process_names,
            index=default_selectbox_index,
            key="followup_edit_process_name_search_input",
            label_visibility="visible"
        )
        
        if edited_process_name_selected != current_search_term_for_selectbox:
            st.session_state.followup_search_terms['Processo_Novo'] = edited_process_name_selected
            st.rerun()

        if edited_process_name_selected:
            selected_process_identifier = process_name_to_id_map.get(edited_process_name_selected)
            if selected_process_identifier:
                if st.button(f"Abrir Edição de '{edited_process_name_selected}'", key=f"edit_process_from_search_button_outside_form"):
                    _open_edit_process_popup(selected_process_identifier) # Chamará a nova página de formulário
            else:
                pass 

    with col2_clear_search:
        st.markdown("<div style='height: 28px; visibility: hidden;'>.</div>", unsafe_allow_html=True)
        if st.button("Limpar Pesquisa", key="clear_process_search_button"):
            st.session_state.followup_search_terms['Processo_Novo'] = ""
            st.rerun()

    st.markdown("---")
    st.markdown("#### Processos de Importação")
    
    col3_expand, col3_collapse = st.columns([0.07, 0.5])
    with col3_expand:
        if st.button("Expandir Todos", key="expand_all_button"):
            _expand_all_expanders()
    
    with col3_collapse:
        if st.button("Recolher Todos", key="collapse_all_button"):
            _collapse_all_expanders()
    
    if st.session_state.followup_processes_data:
        df_all_processes = pd.DataFrame(st.session_state.followup_processes_data)
        
        if 'Status_Geral' not in df_all_processes.columns:
            df_all_processes['Status_Geral'] = 'Sem Status'
        if 'Modal' not in df_all_processes.columns:
            df_all_processes['Modal'] = 'Sem Modal'
        
        df_all_processes['Status_Geral'] = df_all_processes['Status_Geral'].fillna('Sem Status')
        df_all_processes['Modal'] = df_all_processes['Modal'].fillna('Sem Modal')

        custom_status_order = [
            'Encerrado','Chegada Pichau', 'Agendado', 'Liberado', 'Registrado',
            'Chegada Recinto', 'Embarcado', 'Verificando', 'Pré Embarque', 
            'Em produção', 'Processo Criado', 
            'Sem Status', 'Status Desconhecido', 'Arquivados'
        ]

        for status_val in df_all_processes['Status_Geral'].unique():
            if status_val not in custom_status_order:
                custom_status_order.append(status_val)

        df_all_processes['Status_Geral'] = pd.Categorical(
            df_all_processes['Status_Geral'],
            categories=custom_status_order,
            ordered=True
        )

        df_all_processes = df_all_processes.sort_values(by=['Status_Geral', 'Modal'])

        grouped_by_status = df_all_processes.groupby('Status_Geral', observed=False) 

        display_columns_for_dataframe = [
            "Processo_Novo",  "Fornecedor", "Tipos_de_item","Observacao", "Data_Embarque", "ETA_Recinto",
            "Previsao_Pichau", "Documentos_Revisados", "Conhecimento_Embarque",
            "Descricao_Feita", "Descricao_Enviada","Nota_feita", "N_Invoice",
            "Quantidade", "Valor_USD", "Pago", "N_Ordem_Compra", "Data_Compra",
            "Estimativa_Frete_USD", "Agente_de_Carga_Novo",
            "Caminho_da_pasta",
            "Origem", "Destino", "INCOTERM", "Comprador", "Navio",
            "Data_Registro",
            "Estimativa_Impostos_Total", # Mantido, refletindo a soma total
            "id"
        ]
        # Filtrar as colunas para garantir que apenas as existentes no DataFrame sejam exibidas
        cols_to_display_in_table = [col for col in display_columns_for_dataframe if col in df_all_processes.columns]

        column_config_for_dataframe = {
            "Processo_Novo": st.column_config.TextColumn("Processo", width="medium"),
            "Fornecedor": st.column_config.TextColumn("Fornecedor", width="small"),
            "Tipos_de_item": st.column_config.TextColumn("Tipo Item", width="small"),
            "Observacao": st.column_config.TextColumn("Observação", width="medium"),
            "Data_Embarque": st.column_config.TextColumn("Data Emb.", width="small"),
            "ETA_Recinto": st.column_config.TextColumn("ETA Recinto", width="small"),
            "Previsao_Pichau": st.column_config.TextColumn("Prev. Pichau", width="small"),
            "Documentos_Revisados": st.column_config.TextColumn("Docs Rev.", width="small"),
            "Conhecimento_Embarque": st.column_config.TextColumn("Conh. Emb.", width="small"),
            "Descricao_Feita": st.column_config.TextColumn("Desc. Feita", width="small"),
            "Descricao_Enviada": st.column_config.TextColumn("Desc. Envia.", width="small"),            
            "Nota_feita": st.column_config.TextColumn("Nota feita", width="small"), # Configuração da coluna Nota feita
            "N_Invoice": st.column_config.TextColumn("Nº Invoice", width="small"),
            "Quantidade": st.column_config.TextColumn("Qtd", width="small"), 
            "Valor_USD": st.column_config.TextColumn("Valor (US$)", width="small"),
            "Pago": st.column_config.TextColumn("Pago?", width="small"), 
            "N_Ordem_Compra": st.column_config.TextColumn("Nº OC", width="small"),
            "Data_Compra": st.column_config.TextColumn("Data Compra", width="small"),
            "Estimativa_Frete_USD": st.column_config.TextColumn("Est. Frete (US$)", width="medium"),
            "Agente_de_Carga_Novo": st.column_config.TextColumn("Agente Carga", width="small"),
            "Caminho_da_pasta": st.column_config.TextColumn("Documentos Anexados", width="medium"),
            "Origem": st.column_config.TextColumn("Origem", width="small"),
            "Destino": st.column_config.TextColumn("Destino", width="small"),
            "INCOTERM": st.column_config.TextColumn("INCOTERM", width="small"),
            "Comprador": st.column_config.TextColumn("Comprador", width="small"),
            "Navio": st.column_config.TextColumn("Navio", width="small"),
            "Data_Registro": st.column_config.TextColumn("Data Registro", width="small"),
            "Estimativa_Impostos_Total": st.column_config.TextColumn("Imp. Totais (R$)", width="medium"), # Configuração para o campo total
            "Status_Geral": st.column_config.Column(disabled=True, width="small"), 
            "Modal": st.column_config.Column(disabled=True, width="small"), 
            "Status_Arquivado": st.column_config.Column(disabled=True, width="small"), 
            "id": st.column_config.NumberColumn("ID", width="small", help="ID Único do Processo")
        }


        status_color_hex = {
            'Encerrado': '#404040',
            'Chegada Pichau': "#7F81D3",
            'Agendado': "#534E6B",
            'Liberado': '#A0A0A0',
            'Registrado': '#C0C0C0',
            'Chegada Recinto': '#008000',
            'Embarcado': '#6A0DAD',
            'Pré Embarque': '#FFFFE0',
            'Verificando': '#F08080',
            'Em produção': '#FFB6C1',
            'Processo Criado': '#FFFFFF',            
            'Arquivados': '#C0C0C0',
            'Sem Status': '#909090',
            'Status Desconhecido': '#B0B0B0',
        }

        for status in custom_status_order:
            status_group_df = df_all_processes[df_all_processes['Status_Geral'] == status]
            
            if status_group_df.empty:
                continue

            bg_color = status_color_hex.get(status, '#333333')
            text_color = '#FFFFFF' if bg_color in ['#404040', '#6A0DAD', '#606060', '#333333'] else '#000000'

            st.markdown(f"<h4 style='background-color:{bg_color}; color:{text_color}; padding: 10px 10px 10px 25px; border-radius: 15px; margin-bottom: 15px;'>Status: {status} - {len(status_group_df)} processo(s)</h4>", unsafe_allow_html=True)

            with st.expander(f"Detalhes do Status {status}", expanded=st.session_state.followup_expand_all_expanders): 
                grouped_by_modal = status_group_df.groupby('Modal')

                for modal, modal_group_df in grouped_by_modal:
                    st.markdown(f"<p style='color: #FFFFFF;'><b>Modal:</b> {modal} ({len(modal_group_df)} processos)</p>", unsafe_allow_html=True)
                    
                    df_modal_display = modal_group_df.copy()
                    
                    for col_name in ["Data_Compra", "Data_Embarque", "Previsao_Pichau", "ETA_Recinto", "Data_Registro"]:
                        if col_name in df_modal_display.columns:
                            df_modal_display[col_name] = df_modal_display[col_name].apply(_format_date_display)
                    for col_name in ["Valor_USD", "Estimativa_Frete_USD"]:
                        if col_name in df_modal_display.columns:
                            df_modal_display[col_name] = df_modal_display[col_name].apply(_format_usd_display)
                    if "Estimativa_Impostos_Total" in df_modal_display.columns: # Formatar o novo campo
                        df_modal_display["Estimativa_Impostos_Total"] = df_modal_display["Estimativa_Impostos_Total"].apply(_format_currency_display)
                    if "Quantidade" in df_modal_display.columns:
                        df_modal_display["Quantidade"] = df_modal_display["Quantidade"].apply(_format_int_display)
                    for col_name in ["Documentos_Revisados", "Conhecimento_Embarque", "Descricao_Feita", "Descricao_Enviada", "Pago", "Nota_feita", "Conferido"]: # Adicionada Nota_feita e Conferido
                        if col_name in df_modal_display.columns:
                            df_modal_display[col_name] = df_modal_display[col_name].apply(lambda x: "✅ Sim" if str(x).lower() == "sim" else ("⚠️ Não" if str(x).lower() == "não" else ""))
                    
                    # Coluna DI_ID_Vinculada removida da exibição
                    # if 'DI_ID_Vinculada' in df_modal_display.columns:
                    #     df_modal_display['DI_ID_Vinculada'] = df_modal_display['DI_ID_Vinculada'].apply(lambda di_id: _get_di_number_from_id(di_id) if di_id is not None else "N/A")

                    selected_rows_data = st.dataframe(
                        df_modal_display[cols_to_display_in_table],
                        key=f"dataframe_group_{status}_{modal}",
                        hide_index=True,
                        use_container_width=True,
                        column_config=column_config_for_dataframe, 
                        selection_mode='single-row', 
                        on_select='rerun', 
                    )

                    if selected_rows_data and \
                       selected_rows_data.get('selection') and \
                       selected_rows_data['selection'].get('rows') and \
                       len(selected_rows_data['selection']['rows']) > 0:
                        
                        selected_index_in_df_modal = selected_rows_data['selection']['rows'][0]
                        
                        selected_process_name_from_display = df_modal_display.iloc[selected_index_in_df_modal]['Processo_Novo']

                        selected_original_process = next((p for p in st.session_state.followup_processes_data if p.get('Processo_Novo') == selected_process_name_from_display), None)

                        if selected_original_process:
                            selected_process_id = selected_original_process.get('id')
                            selected_process_name = selected_original_process.get('Processo_Novo')
                            
                            if selected_process_id is not None and selected_process_name is not None:
                                col_edit_btn, col_delete_btn = st.columns(2)
                                with col_edit_btn:
                                    if st.button(f"Editar Processo Selecionado: {selected_process_name}", key=f"edit_selected_btn_{selected_process_id}"):
                                        _open_edit_process_popup(selected_process_id)
                                with col_delete_btn:
                                    if st.button(f"Excluir Processo Selecionado: {selected_process_name}", key=f"delete_selected_btn_{selected_process_id}"):
                                        st.session_state.show_delete_confirm_popup = True
                                        st.session_state.delete_process_id_to_confirm = selected_process_id
                                        st.session_state.delete_process_name_to_confirm = selected_process_name
                                        st.rerun()
                            else:
                                st.error(f"Erro: ID ou Nome do processo '{selected_process_name_from_display}' não encontrado nos dados originais para edição/exclusão.")
                        else:
                            st.error(f"Erro: Processo '{selected_process_name_from_display}' não encontrado nos dados originais para edição/exclusão.")
    else:
        st.info("Nenhum processo de importação encontrado. Adicione um novo ou importe via arquivo.")

    st.markdown("---")
    col_import_data_btn, _ = st.columns([0.2, 0.8])
    with col_import_data_btn:
        if st.button("Importação de Dados", key="open_import_options_button_bottom"):
            st.session_state.show_import_popup = True
            st.rerun()

    st.write("Esta tela permite gerenciar o follow-up de processos de importação.")

    st.markdown("---")
    conn_check = db_manager.conectar_followup_db()
    if conn_check:
        try:
            db_manager.criar_tabela_followup(conn_check)
        except Exception as e:
            st.error(f"Erro ao criar/verificar tabelas do DB de Follow-up: {e}")
        finally:
            conn_check.close()
    else:
        db_path = db_manager.get_followup_db_path() if hasattr(db_manager, 'get_followup_db_path') else "Caminho Desconhecido"
        st.error(f"Não foi possível conectar ao banco de dados de Follow-up em: {db_path}")

