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
from typing import Optional, Any
import numpy as np
import base64 # Importa base64 para codificar imagens

import followup_db_manager as db_manager

# Importa db_utils para obter detalhes da DI
try:
    import db_utils
except ImportError:
    class MockDbUtils:
        def get_db_path(self, db_name):
            _base_path = os.path.dirname(os.path.abspath(__file__))
            _app_root_path = os.path.dirname(_base_path) if os.path.basename(_base_path) == 'app_logic' else _base_path
            _DEFAULT_DB_FOLDER = "data"
            return os.path.join(_app_root_path, _DEFAULT_DB_FOLDER, f"{db_name}.db")
        def get_declaracao_by_id(self, di_id):
            return None # Função mock para simulação
    db_utils = MockDbUtils()
except Exception as e:
    class MockDbUtils:
        def get_db_path(self, db_name):
            _base_path = os.path.dirname(os.path.abspath(__file__))
            _app_root_path = os.path.dirname(_base_path) if os.path.basename(_base_path) == 'app_logic' else _base_path
            _DEFAULT_DB_FOLDER = "data"
            return os.path.join(_app_root_path, _DEFAULT_DB_FOLDER, f"{db_name}.db")
        def get_declaracao_by_id(self, di_id):
            return None # Função mock para simulação
    db_utils = MockDbUtils()
    logging.error(f"Erro ao importar 'db_utils' em followup_importacao_page: {e}. Usando simulação.")


logger = logging.getLogger(__name__)

# --- Função para definir imagem de fundo com opacidade (copiada de app_main.py) ---
def set_background_image(image_path):
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

def _format_date_display(date_str):
    """Formata uma string de data (YYYY-MM-DD) para exibição (DD/MM/YYYY)."""
    if date_str and isinstance(date_str, str):
        try:
            return datetime.strptime(date_str, "%Y-%m-%d").strftime("%d/%m/%Y")
        except ValueError:
            return date_str
    return ""

def _format_currency_display(value):
    """Formata um valor numérico para o formato de moeda R$ X.XXX,XX."""
    try:
        val = float(value)
        return f"R$ {val:,.2f}".replace('.', '#').replace(',', '.').replace('#', ',')
    except (ValueError, TypeError):
        return "R$ 0,00"

def _format_usd_display(value):
    """Formata um valor numérico para o formato de moeda US$ X.XXX,XX."""
    try:
        val = float(value)
        return f"US$ {val:,.2f}".replace('.', '#').replace(',', '.').replace('#', ',')
    except (ValueError, TypeError):
        return "US$ 0,00"

def _format_int_display(value):
    """Formata um valor para inteiro."""
    try:
        val = int(value)
        return str(val)
    except (ValueError, TypeError):
        return ""

# NOVO: Função para formatar o número da DI
def _format_di_number(di_number):
    """Formata o número da DI para o padrão **/*******-*."""
    if di_number and isinstance(di_number, str) and len(di_number) == 10:
        return f"{di_number[0:2]}/{di_number[2:9]}-{di_number[9]}"
    return di_number

# NOVO: Função para obter o número da DI a partir do ID
def _get_di_number_from_id(di_id: int) -> str:
    """Obtém o número da DI a partir do seu ID no banco de dados de XML DI."""
    di_data = db_utils.get_declaracao_by_id(di_id)
    if di_data:
        return _format_di_number(di_data['numero_di'])
    return "DI Não Encontrada"

# --- Funções Auxiliares (movidas para o topo) ---

# Função para expandir todos os expanders
def _expand_all_expanders():
    st.session_state.followup_expand_all_expanders = True

# Função para recolher todos os expanders
def _collapse_all_expanders():
    st.session_state.followup_collapse_all_expanders = True # Define isso como True
    st.session_state.followup_expand_all_expanders = False # Garante que isso seja False

# NOVO: Função para exibir o pop-up de confirmação de exclusão
def _display_delete_confirm_popup():
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
                # A função _delete_process_action agora é responsável por fechar o pop-up e rerunnar
        with col_no:
            if st.form_submit_button("Não, Cancelar"):
                st.session_state.show_delete_confirm_popup = False
                st.session_state.delete_process_id_to_confirm = None
                st.session_state.delete_process_name_to_confirm = None
                st.rerun()

def _load_processes():
    """Carrega os processos do DB aplicando filtros e termos de pesquisa."""
    if not db_manager.get_followup_db_path():
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
    status_from_db = db_manager.obter_status_gerais_distintos()
    all_status_options = ["Todos", "Arquivados"] + sorted([s for s in status_from_db if s not in ["Todos", "Arquivados"]])
    st.session_state.followup_all_status_options = all_status_options

def _import_file_action(uploaded_file):
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


def _open_edit_process_popup(process_identifier=None):
    """Abre o pop-up de edição/criação de processo."""
    st.session_state.show_followup_edit_popup = True
    st.session_state.followup_editing_process_identifier = process_identifier
    st.rerun()

def _display_edit_process_popup():
    """Exibe o pop-up de edição/criação de processo."""
    if not st.session_state.get('show_followup_edit_popup', False):
        return

    process_identifier = st.session_state.get('followup_editing_process_identifier')
    is_new_process = process_identifier is None

    process_data = {}
    process_id = None

    if not is_new_process:
        if isinstance(process_identifier, int):
            raw_data = db_manager.obter_processo_por_id(process_identifier)
        elif isinstance(process_identifier, str):
            raw_data = db_manager.obter_processo_by_processo_novo(process_identifier)
        else:
            raw_data = None
            logger.error(f"Tipo inesperado para process_identifier: {type(process_identifier)} - {process_identifier}")
        
        if raw_data:
            process_data = dict(raw_data) # Convertendo sqlite3.Row para dict
            process_id = process_data['id']
        else:
            st.error(f"Processo '{process_identifier}' não encontrado para edição.")
            st.session_state.show_followup_edit_popup = False
            return
    else:
        process_id = None

    # NOVO: Variáveis para o botão "Ver Detalhes da DI" fora do formulário
    linked_di_id = process_data.get('DI_ID_Vinculada')
    linked_di_number = None
    if linked_di_id:
        linked_di_data = db_utils.get_declaracao_by_id(linked_di_id)
        if linked_di_data:
            linked_di_number = _format_di_number(linked_di_data['numero_di'])

    with st.form(key=f"followup_process_form_{process_id}"):
        st.markdown(f"### {'Novo Processo' if is_new_process else f'Editar Processo: {process_data.get('Processo_Novo', '')}'}")

        col1, col2, col3 = st.columns(3)
        edited_data = {}

        campos_config_ui = {
            "Processo_Novo": {"label": "Processo:", "type": "text"},
            "Fornecedor": {"label": "Fornecedor:", "type": "text"},
            "Tipos_de_item": {"label": "Tipos de item:", "type": "text"},
            "N_Invoice": {"label": "Nº Invoice:", "type": "text"},
            "Quantidade": {"label": "Quantidade:", "type": "number"},
            "Valor_USD": {"label": "Valor (USD):", "type": "currency_usd"},
            "Pago": {"label": "Pago?:", "type": "dropdown", "values": ["", "Sim", "Não"]},
            "N_Ordem_Compra": {"label": "Nº da Ordem de Compra:", "type": "text"},
            "Data_Compra": {"label": "Data de Compra:", "type": "date"},
            "Estimativa_Impostos_BR": {"label": "Estimativa de Impostos (R$):", "type": "currency_br"},
            "Estimativa_Frete_USD": {"label": "Estimativa de Frete (USD):", "type": "currency_usd"},
            "Data_Embarque": {"label": "Data de Embarque:", "type": "date"},
            "Agente_de_Carga_Novo": {"label": "Agente de Carga:", "type": "text"},
            "Status_Geral": {"label": "Status Geral:", "type": "dropdown", "values": db_manager.STATUS_OPTIONS},
            "Previsao_Pichau": {"label": "Previsão na Pichau:", "type": "date"},
            "Modal": {"label": "Modal:", "type": "dropdown", "values": ["", "Aéreo", "Maritimo"]},
            "Navio": {"label": "Navio:", "type": "text", "conditional_field": "Modal", "conditional_value": "Maritimo"},
            "Origem": {"label": "Origem:", "type": "text"},
            "Destino": {"label": "Destino:", "type": "text"},
            "INCOTERM": {"label": "INCOTERM:", "type": "dropdown", "values": ["", "EXW","FCA","FAS","FOB","CFR","CIF","CPT","CIP","DPU","DAP","DDP"]},
            "Comprador": {"label": "Comprador:", "type": "text"},
            "Documentos_Revisados": {"label": "Documentos Revisados:", "type": "dropdown", "values": ["", "Sim", "Não"]},
            "Conhecimento_Embarque": {"label": "Conhecimento de embarque:", "type": "dropdown", "values": ["", "Sim", "Não"]},
            "Descricao_Feita": {"label": "Descrição Feita:", "type": "dropdown", "values": ["", "Sim", "Não"]},
            "Descricao_Enviada": {"label": "Descrição Enviada:", "type": "dropdown", "values": ["", "Sim", "Não"]},
            "Caminho_da_pasta": {"label": "Caminho da pasta:", "type": "folder_path"},
            "ETA_Recinto": {"label": "ETA no Recinto:", "type": "date"},
            "Data_Registro": {"label": "Data de Registro:", "type": "date"},
            "Observacao": {"label": "Observação:", "type": "text_area"},
            "DI_ID_Vinculada": {"label": "DI Vinculada (ID):", "type": "text", "disabled": True, "help": "ID da Declaração de Importação vinculada a este processo."}, # NOVO CAMPO
        }

        all_fields = list(campos_config_ui.keys())

        col1_fields = [
            "Processo_Novo", "Fornecedor", "Tipos_de_item", "N_Invoice",
            "Quantidade", "Valor_USD", "Pago", "N_Ordem_Compra", "Data_Compra"
        ]
        col2_fields = [
            "Estimativa_Impostos_BR", "Estimativa_Frete_USD", "Data_Embarque",
            "Agente_de_Carga_Novo", "Status_Geral", "Previsao_Pichau", "Modal",
            "ETA_Recinto", "Data_Registro"
        ]
        col3_fields = [
            "Origem", "Destino", "INCOTERM", "Comprador",
            "Documentos_Revisados", "Conhecimento_Embarque", "Descricao_Feita",
            "Descricao_Enviada", "Caminho_da_pasta", "DI_ID_Vinculada" # Adicionado aqui
        ]
        
        for field_name in all_fields:
            config = campos_config_ui[field_name]
            
            if field_name == "Navio":
                modal_value_current = edited_data.get("Modal", process_data.get("Modal", ""))
                if modal_value_current != "Maritimo":
                    continue
            
            target_column = None
            if field_name in col1_fields:
                target_column = col1
            elif field_name in col2_fields:
                target_column = col2
            elif field_name in col3_fields:
                target_column = col3
            elif field_name == "Observacao":
                continue
            else:
                logger.warning(f"Campo '{field_name}' não mapeado para nenhuma coluna de UI.")
                continue


            with target_column:
                label = config["label"]
                current_value = process_data.get(field_name)

                if config["type"] == "date":
                    if current_value:
                        try:
                            current_value_dt = datetime.strptime(current_value, "%Y-%m-%d")
                        except ValueError:
                            current_value_dt = None
                    else:
                        current_value_dt = None
                    widget_value = st.date_input(label, value=current_value_dt, key=f"edit_{process_id}_{field_name}", format="DD/MM/YYYY") # Formatar data de entrada
                    edited_data[field_name] = widget_value.strftime("%Y-%m-%d") if widget_value else None

                elif config["type"] == "number":
                    widget_value = st.number_input(label, value=float(current_value) if current_value is not None else 0.0, format="%d", key=f"edit_{process_id}_{field_name}")
                    edited_data[field_name] = int(widget_value)
                
                elif config["type"] == "currency_usd":
                    widget_value = st.number_input(label, value=float(current_value) if current_value is not None else 0.0, format="%.2f", key=f"edit_{process_id}_{field_name}")
                    edited_data[field_name] = widget_value
                
                elif config["type"] == "dropdown":
                    options = config["values"]
                    default_index = 0
                    if current_value in options:
                        default_index = options.index(current_value)
                    elif current_value is not None and str(current_value).strip() != "" and current_value not in options:
                        options = [current_value] + options
                        default_index = 0

                    widget_value = st.selectbox(label, options=options, index=default_index, key=f"edit_{process_id}_{field_name}")
                    edited_data[field_name] = widget_value if widget_value else None
                
                elif config["type"] == "folder_path":
                    edited_data[field_name] = st.text_input(label, value=current_value if current_value is not None else "", key=f"edit_{process_id}_{field_name}_path_input")
                
                elif config["type"] == "text" and config.get("disabled"): # Lidar com campo de texto desabilitado para DI_ID_Vinculada
                    display_value = str(current_value) if current_value is not None else ""
                    st.text_input(label, value=display_value, key=f"edit_{process_id}_{field_name}", disabled=True)
                    edited_data[field_name] = current_value # Manter o valor original para o campo desabilitado
                
                else: # Default para tipo "text"
                    widget_value = st.text_input(label, value=current_value if current_value is not None else "", key=f"edit_{process_id}_{field_name}")
                    edited_data[field_name] = widget_value if widget_value else None
            
        st.markdown("---")
        st.markdown("##### Observação (Campo Dedicado)")
        edited_data["Observacao"] = st.text_area("Observação", value=process_data.get("Observacao", ""), height=150, key=f"edit_{process_id}_Observacao_dedicated")
        edited_data["Observacao"] = edited_data["Observacao"] if edited_data["Observacao"] else None

        st.markdown("---")
        st.markdown("##### Histórico do Processo")
        if not is_new_process:
            history_data_raw = db_manager.obter_historico_processo(process_id)
            if history_data_raw:
                history_df = pd.DataFrame(history_data_raw, columns=["Campo", "Valor Antigo", "Valor Novo", "Timestamp", "Usuário"])
                history_df["Timestamp"] = history_df["Timestamp"].apply(lambda x: datetime.strptime(x, "%Y-%m-%d %H:%M:%S").strftime("%d/%m/%Y %H:%M:%S") if x else "")
                st.dataframe(history_df, use_container_width=True, hide_index=True)
            else:
                st.info("Nenhum histórico de alterações para este processo.")
        else:
            st.info("Histórico disponível apenas para processos existentes após a primeira gravação.")


        col_save, col_cancel  = st.columns([0.03, 0.1])

        with col_save:
            if st.form_submit_button("Salvar Processo"):
                _save_process_action(process_id, edited_data, is_new_process)
        with col_cancel:
            if st.form_submit_button("Cancelar"):
                st.session_state.show_followup_edit_popup = False
                st.rerun()

        col_delete = st.columns([0.0000003, 0.01])[1]  # Usando a segunda coluna para o botão de exclusão

        with col_delete:
            if not is_new_process:
                # Checkbox de confirmação para exclusão
                confirm_delete = st.checkbox("Confirmar exclusão", key=f"confirm_delete_process_{process_id}")
                if st.form_submit_button("Excluir Processo"):
                    if confirm_delete:
                        _delete_process_action(process_id)
                    else:
                        st.warning("Marque a caixa de confirmação para excluir o processo.")
            else:
                st.info("Excluir disponível após salvar o processo.")
        

    # NOVO: Renderiza o botão "Ver Detalhes da DI" FORA do formulário
    if linked_di_id and linked_di_number:
        st.markdown("---")
        st.markdown(f"**DI Vinculada:** {linked_di_number}")
        if st.button(f"Ver Detalhes da DI {linked_di_number}", key=f"view_linked_di_outside_form_{process_id}"):
            st.session_state.current_page = "Importar XML DI"
            st.session_state.selected_di_id = linked_di_id
            st.rerun()
    elif linked_di_id and not linked_di_number:
        st.markdown("---")
        st.warning(f"DI vinculada (ID: {linked_di_id}) não encontrada no banco de dados de Declarações de Importação.")


def _save_process_action(process_id, edited_data, is_new_process):
    """Lógica para salvar ou atualizar um processo."""
    # Obtém a lista completa de colunas do DB, incluindo 'id' e 'Status_Arquivado'
    db_col_names_full = db_manager.obter_nomes_colunas_db()
    
    # Cria um dicionário para armazenar todos os valores a serem salvos,
    # preenchendo com None ou valores padrão/originais
    data_to_save_dict = {col: None for col in db_col_names_full if col != 'id'}

    # Preenche com os dados editados do formulário
    for col_name, value in edited_data.items():
        if col_name in data_to_save_dict: # Garante que a coluna existe no DB antes de tentar atribuir
            if isinstance(value, datetime):
                data_to_save_dict[col_name] = value.strftime("%Y-%m-%d")
            elif isinstance(value, str) and value.strip() == '':
                data_to_save_dict[col_name] = None
            else:
                data_to_save_dict[col_name] = value
        else:
            logger.warning(f"Campo '{col_name}' do formulário não corresponde a uma coluna no DB. Ignorado.")


    # Lida com a coluna Status_Arquivado
    if 'Status_Arquivado' in db_col_names_full:
        if is_new_process:
            data_to_save_dict['Status_Arquivado'] = 'Não Arquivado'
        else:
            # Para processo existente, mantém o valor original do DB
            original_process_data = db_manager.obter_processo_por_id(process_id)
            if original_process_data:
                original_process_data_dict = dict(original_process_data) # Convertendo sqlite3.Row para dict
                original_status_arquivado = original_process_data_dict.get('Status_Arquivado')
                data_to_save_dict['Status_Arquivado'] = original_status_arquivado
            else:
                logger.warning(f"Processo ID {process_id} não encontrado ao tentar obter Status_Arquivado original para salvar.")
                data_to_save_dict['Status_Arquivado'] = 'Não Arquivado' # Fallback
    
    # Lida com a coluna DI_ID_Vinculada
    # Esta coluna é apenas exibida no formulário de edição do processo, mas não editável diretamente.
    # O valor deve vir do banco de dados original ou ser None para um novo processo.
    if 'DI_ID_Vinculada' in db_col_names_full:
        if is_new_process:
            data_to_save_dict['DI_ID_Vinculada'] = None # Novo processo não tem DI vinculada inicialmente
        else:
            original_process_data = db_manager.obter_processo_por_id(process_id)
            if original_process_data:
                original_process_data_dict = dict(original_process_data) # Convertendo sqlite3.Row para dict
                data_to_save_dict['DI_ID_Vinculada'] = original_process_data_dict.get('DI_ID_Vinculada')
            else:
                data_to_save_dict['DI_ID_Vinculada'] = None


    # Adicionar o usuário que fez a alteração
    user_info = st.session_state.get('user_info', {'username': 'Desconhecido'})
    data_to_save_dict['Ultima_Alteracao_Por'] = user_info.get('username')
    data_to_save_dict['Ultima_Alteracao_Em'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Converte o dicionário para uma tupla na ordem exata das colunas do DB (excluindo 'id')
    final_data_tuple = tuple(data_to_save_dict[col] for col in db_col_names_full if col != 'id')

    changes = []
    if not is_new_process:
        original_process_data_dict = dict(db_manager.obter_processo_por_id(process_id)) # Convertendo sqlite3.Row para dict
        username = user_info.get('username')

        # Compara todos as colunas que estão no DB (exceto 'id')
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
    else:
        success = db_manager.atualizar_processo(process_id, final_data_tuple)

    if success:
        st.success(f"Processo {'adicionado' if is_new_process else 'atualizado'} com sucesso!")
        st.session_state.show_followup_edit_popup = False
        _load_processes() # Recarrega a tabela principal

        if not is_new_process: # Registra histórico apenas para edições
            for change in changes:
                db_manager.inserir_historico_processo(process_id, change['field_name'], change['old_value'], change['new_value'], username)
        
        st.rerun()
    else:
        st.error(f"Falha ao {'adicionar' if is_new_process else 'atualizar'} processo.")

def _delete_process_action(process_id):
    """Exclui um processo do banco de dados."""
    if db_manager.excluir_processo(process_id):
        st.success(f"Processo ID {process_id} excluído com sucesso!")
        # Fechar o pop-up de confirmação de exclusão e limpar o estado
        st.session_state.show_delete_confirm_popup = False
        st.session_state.delete_process_id_to_confirm = None
        st.session_state.delete_process_name_to_confirm = None
        st.session_state.followup_selected_process_id = None # Limpar seleção da tabela
        _load_processes() # Recarrega a tabela principal
        st.rerun() # Força um rerun para atualizar a UI
    else:
        st.error(f"Falha ao excluir processo ID {process_id}.")

def _archive_process_action(process_id):
    """Marca um processo como arquivado no banco de dados."""
    if db_manager.arquivar_processo(process_id):
        st.success(f"Processo ID {process_id} arquivado com sucesso!")
        st.session_state.followup_selected_process_id = None
        _load_processes()
        st.rerun()
    else:
        st.error(f"Falha ao arquivar processo ID {process_id}.")

def _unarchive_process_action(process_id):
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
    # Obtém os dados originais do processo para registrar o histórico
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

# --- NOVO: Função de pré-processamento do DataFrame antes de enviar para o DB ---
def _preprocess_dataframe_for_db(df: pd.DataFrame) -> Optional[pd.DataFrame]:
    """
    Realiza o pré-processamento e padronização dos dados do DataFrame
    para o formato esperado pelo banco de dados.
    """
    df_processed = df.copy() # Trabalha em uma cópia para não alterar o DataFrame original

    # Renomear colunas para corresponder aos nomes do DB (caso a planilha ainda use nomes "amigáveis")
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
        "Est. Imposts": "Estimativa_Impostos_BR", # Corrigido aqui
        "Freight Est.": "Estimativa_Frete_USD", # Corrigido aqui
        "Shipping Date (YYYY-MM-DD)": "Data_Embarque", # Corrigido aqui
        "Shipping Company": "Agente_de_Carga_Novo", 
        "Status": "Status_Geral",
        "ETA Pichau (YYYY-MM-DD)": "Previsao_Pichau", # Corrigido aqui
        "Modal": "Modal",
        "Navio": "Navio",
        "Origin": "Origem", # Corrigido aqui
        "Destination": "Destino", # Corrigido aqui
        "INCOTERM": "INCOTERM",
        "Buyer": "Comprador",
        "Docs Reviewed (Sim/Não)": "Documentos_Revisados",
        "BL/AWB (Sim/Não)": "Conhecimento_Embarque",
        "Description Done (Sim/Não)": "Descricao_Feita",
        "Description Sent (Sim/Não)": "Descricao_Enviada",
        "Folder Path": "Folder Path",
        "ETA Recinto (YYYY-MM-DD)": "ETA_Recinto",
        "Data Registro (YYYY-MM-DD)": "Data_Registro",
        "Obs": "Observacao",
        "DI Vinculada ID": "DI_ID_Vinculada", # NOVO: Adicionado para importação via planilha
    }

    df_processed = df_processed.rename(columns=column_mapping_to_db, errors='ignore')

    db_col_names = db_manager.obter_nomes_colunas_db()
    db_col_names_without_id = [col for col in db_col_names if col != 'id']

    # --- Tratamento de Tipos de Dados ---

    # 1. Colunas de Data (Formato DD/MM/YYYY na planilha ->YYYY-MM-DD para DB)
    date_columns_to_process = ["Data_Compra", "Data_Embarque", "Previsao_Pichau", "ETA_Recinto", "Data_Registro"] # Adicionadas novas colunas
    for col in date_columns_to_process:
        if col in df_processed.columns:
            # Converte para datetime, com errors='coerce' para NaT em caso de falha.
            # dayfirst=True é crucial para formatos DD/MM/YYYY.
            df_processed[col] = pd.to_datetime(df_processed[col], errors='coerce', dayfirst=True)
            # Converte para string ympm-MM-DD. NaT se torna None automaticamente aqui.
            # O .fillna(None) é necessário se houver NaT E você quiser None, mas strftime já lida com NaT para None
            df_processed[col] = df_processed[col].dt.strftime('%Y-%m-%d')
            # logger.debug(f"Coluna '{col}' processada para data.") # Removed debug message

    # 2. Colunas Numéricas (Garante que são números, preenche NaN com 0)
    numeric_columns = ["Quantidade", "Valor_USD", "Estimativa_Impostos_BR", "Estimativa_Frete_USD", "DI_ID_Vinculada"] # Adicionado DI_ID_Vinculada
    for col in numeric_columns:
        if col in df_processed.columns:
            # Converte para numérico, forçando erros para NaN, e depois preenche NaN com 0.
            # Trata vírgulas como separadores decimais (com .str.replace se o tipo for object)
            if df_processed[col].dtype == 'object':
                df_processed[col] = df_processed[col].astype(str).str.replace('.', '', regex=False).str.replace(',', '.', regex=False)
            df_processed[col] = pd.to_numeric(df_processed[col], errors='coerce').fillna(0)
            if col == "Quantidade" or col == "DI_ID_Vinculada": # DI_ID_Vinculada também é inteiro
                df_processed[col] = df_processed[col].astype(int)
            else:
                df_processed[col] = df_processed[col].astype(float)
            # logger.debug(f"Coluna '{col}' processada para numérico.") # Removed debug message

    # 3. Colunas de Sim/Não (Padroniza para "Sim" ou "Não" ou None)
    yes_no_columns = [
        "Pago", "Documentos_Revisados", "Conhecimento_Embarque",
        "Descricao_Feita", "Descricao_Enviada"
    ]
    for col in yes_no_columns:
        if col in df_processed.columns:
            df_processed[col] = df_processed[col].astype(str).str.strip().str.lower()
            df_processed[col] = df_processed[col].apply(
                lambda x: "Sim" if x in ["sim", "s"] else ("Não" if x in ["nao", "não", "n"] else None)
            )
            # logger.debug(f"Coluna '{col}' processada para Sim/Não.") # Removed debug message

    # 4. Outras colunas de texto: Garantir que strings vazias sejam None
    for col in df_processed.columns:
        if col not in numeric_columns + date_columns_to_process + yes_no_columns:
            df_processed[col] = df_processed[col].astype(str) 
            df_processed[col] = df_processed[col].replace({'': np.nan})
            df_processed[col] = df_processed[col].replace({'nan': np.nan}) 
            
    # --- Selecionar e reordenar colunas para o DB ---
    final_df_for_db = pd.DataFrame(columns=db_col_names_without_id)
    for col in db_col_names_without_id:
        if col in df_processed.columns:
            final_df_for_db[col] = df_processed[col]
        else:
            final_df_for_db[col] = np.nan # Preenche com NaN para colunas ausentes, será convertido para None

    # Substitui quaisquer valores NaN remanescentes no DataFrame final por None para SQLite
    final_df_for_db = final_df_for_db.where(pd.notnull(final_df_for_db), None)

    return final_df_for_db

# Pop-up de Filtros e Pesquisa
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
                      value=st.session_state.get('followup_search_terms', {}).get('Processo_Novo', ''))
        st.text_input("Pesquisar Fornecedor:", key="popup_followup_search_fornecedor",
                      value=st.session_state.get('followup_search_terms', {}).get('Fornecedor', ''))
        st.text_input("Pesquisar Nº Invoice:", key="popup_followup_search_n_invoice",
                      value=st.session_state.get('followup_search_terms', {}).get('N_Invoice', ''))
        
        col_buttons_popup = st.columns(2)
        with col_buttons_popup[0]:
            if st.form_submit_button("Aplicar Filtros"):
                st.session_state.followup_status_filter = st.session_state.popup_followup_status_filter
                st.session_state.followup_search_terms = {
                    "Processo_Novo": st.session_state.popup_followup_search_processo_novo,
                    "Fornecedor": st.session_state.popup_followup_search_fornecedor,
                    "N_Invoice": st.session_state.popup_followup_search_n_invoice,
                }
                _load_processes() # Recarrega os processos com os novos filtros
                st.session_state.show_filter_search_popup = False # Fecha o pop-up
                st.rerun()
        with col_buttons_popup[1]:
            # Botão Limpar Pesquisa e Filtros
            if st.form_submit_button("Limpar Pesquisa e Filtros"):
                st.session_state.followup_status_filter = 'Todos'
                st.session_state.followup_search_terms = {}
                st.session_state.popup_followup_search_processo_novo = ""
                st.session_state.popup_followup_search_fornecedor = ""
                st.session_state.popup_followup_search_n_invoice = ""
                _load_processes() # Recarrega os processos sem filtros
                st.session_state.show_filter_search_popup = False # Fecha o pop-up
                st.rerun()
        
        if st.form_submit_button("Fechar"):
            st.session_state.show_filter_search_popup = False
            st.rerun()

# Geração de Template Excel
def _generate_excel_template():
    """Gera um arquivo Excel padrão para inserção de dados de Follow-up."""
    template_columns_map = {
        "Processo_Novo": "Process Reference",
        "Supplier": "Supplier",
        "Type of Item": "Type of Item",
        "INV/Invoice": "INV/Invoice",
        "Qtd": "Qtd",
        "Value USD": "Value USD",
        "Paid?": "Paid?",
        "P/O": "P/O",
        "Purchase Date (YYYY-MM-DD)": "Purchase Date (YYYY-MM-DD)",
        "Est. Imposts": "Est. Imposts",
        "Freight Est.": "Est. Freight.",
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
        "Folder Path": "Folder Path",
        "ETA Recinto (YYYY-MM-DD)": "ETA Recinto (YYYY-MM-DD)", # Nova coluna
        "Data Registro (YYYY-MM-DD)": "Data Registro (YYYY-MM-DD)", # Nova coluna
        "Obs": "Obs",
        "DI Vinculada ID": "DI Vinculada ID", # NOVO: Adicionado ao template
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
        "Freight Est.": 1200.00,
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
        "DI Vinculada ID": "", # Exemplo vazio para a nova coluna
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
    try:
        creds_json = st.secrets["gcp_service_account"]
        
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_json, scope)
        
        client = gspread.authorize(creds)
        return client
    except Exception as e:
        logger.error(f"Erro ao autenticar gspread: {e}")
        st.error(f"Erro de autenticação com Google Sheets. Verifique suas credenciais em .streamlit/secrets.toml e as permissões da conta de serviço. Detalhes: {e}")
        return None

def _import_from_google_sheets(sheet_url_or_id, worksheet_name):
    client = _get_gspread_client()
    if not client:
        return False

    try:
        if "https://" in sheet_url_or_id:
            spreadsheet = client.open_by_url(sheet_url_or_id)
        else:
            spreadsheet = client.open_by_key(sheet_url_or_id)
        
        worksheet = spreadsheet.worksheet(worksheet_name)
        
        db_columns_order = db_manager.obter_nomes_colunas_db()
        db_columns_order = [col for col in db_columns_order if col != 'id']

        expected_headers_map = {
            "Process Reference": "Processo_Novo",
            "Supplier": "Fornecedor",
            "Type of Item": "Tipos_de_item",
            "INV/Invoice": "N_Invoice",
            "Qtd": "Quantidade",
            "Value USD": "Valor_USD",
            "Paid?": "Pago",
            "P/O": "N_Ordem_Compra",
            "Purchase Date (YYYY-MM-DD)": "Data_Compra",
            "Est. Imposts": "Estimativa_Impostos_BR",
            "Freight Est.": "Estimativa_Frete_USD",
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
            "Folder Path": "Folder Path",
            "ETA Recinto (YYYY-MM-DD)": "ETA_Recinto",
            "Data Registro (YYYY-MM-DD)": "Data_Registro",
            "Obs": "Observacao",
            "DI Vinculada ID": "DI_ID_Vinculada", # NOVO: Adicionado para importação via Google Sheets
        }
        gsheets_headers = list(expected_headers_map.keys())

        data = worksheet.get_all_records(value_render_option='UNFORMATTED_VALUE', head=1)
        
        if not data:
            st.warning(f"A aba '{worksheet_name}' na planilha '{sheet_url_or_id}' está vazia.")
            return False

        actual_headers = worksheet.row_values(1)

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

# NOVO: Função para abrir o pop-up de edição em massa
def _open_mass_edit_popup():
    st.session_state.show_mass_edit_popup = True
    # Inicializa o texto da área de texto de processos para edição em massa
    if 'mass_edit_process_names_input' not in st.session_state:
        st.session_state.mass_edit_process_names_input = ""
    # Inicializa a lista de processos encontrados
    if 'mass_edit_found_processes' not in st.session_state:
        st.session_state.mass_edit_found_processes = []
    st.rerun()

# NOVO: Função para exibir o pop-up de edição em massa
def _display_mass_edit_popup():
    if not st.session_state.get('show_mass_edit_popup', False):
        return

    with st.form(key="mass_edit_form"):
        st.markdown("### Editar Múltiplos Processos")

        st.markdown("#### 1. Inserir Processos para Edição")
        # Área de texto para inserir nomes de processos
        process_names_input = st.text_area(
            "Insira os nomes dos processos (um por linha):",
            value=st.session_state.mass_edit_process_names_input,
            height=150,
            key="mass_edit_process_names_textarea"
        )
        
        # Botão para buscar os processos inseridos
        if st.form_submit_button("Buscar Processos"):
            st.session_state.mass_edit_process_names_input = process_names_input # Salva o input
            
            # Limpa e busca os processos
            st.session_state.mass_edit_found_processes = []
            if process_names_input:
                names_to_search = [name.strip() for name in process_names_input.split('\n') if name.strip()]
                for name in names_to_search:
                    process_data_row = db_manager.obter_processo_by_processo_novo(name)
                    
                    found_entry = {
                        'Processo_Novo': name, # Mantém o nome original da busca
                        'ID': 'Não encontrado',
                        'Status da Busca': 'Não encontrado',
                        'Status_Geral': 'N/A',
                        'Observacao': 'N/A',
                        'Previsao_Pichau': 'N/A',
                        'Data_Embarque': 'N/A',
                        'ETA_Recinto': 'N/A',
                        'Data_Registro': 'N/A'
                    }

                    if process_data_row:
                        # Converte sqlite3.Row para dict para usar .get() ou acesso por chave
                        process_data = dict(process_data_row) 
                        found_entry['Processo_Novo'] = process_data['Processo_Novo'] # Usa o nome do DB para o encontrado
                        found_entry['ID'] = process_data['id']
                        found_entry['Status da Busca'] = 'Encontrado'
                        # Acessa os valores diretamente ou com .get() se o dicionário for garantido
                        found_entry['Status_Geral'] = process_data['Status_Geral'] if 'Status_Geral' in process_data else 'N/A'
                        found_entry['Observacao'] = process_data['Observacao'] if 'Observacao' in process_data else 'N/A'
                        found_entry['Previsao_Pichau'] = _format_date_display(process_data['Previsao_Pichau']) if 'Previsao_Pichau' in process_data else 'N/A'
                        found_entry['Data_Embarque'] = _format_date_display(process_data['Data_Embarque']) if 'Data_Embarque' in process_data else 'N/A'
                        found_entry['ETA_Recinto'] = _format_date_display(process_data['ETA_Recinto']) if 'ETA_Recinto' in process_data else 'N/A'
                        found_entry['Data_Registro'] = _format_date_display(process_data['Data_Registro']) if 'Data_Registro' in process_data else 'N/A'
                    
                    st.session_state.mass_edit_found_processes.append(found_entry)
            st.rerun() # Força rerun para exibir a tabela de resultados

        # Exibir tabela de resultados da busca
        if st.session_state.mass_edit_found_processes:
            st.markdown("#### Resultados da Busca:")
            df_found_processes = pd.DataFrame(st.session_state.mass_edit_found_processes)
            
            # Colunas a serem exibidas na tabela de resultados da busca
            display_cols_search_results = [
                "Processo_Novo", "Status_Geral", "Observacao", 
                "Previsao_Pichau", "Data_Embarque", "ETA_Recinto", "Data_Registro", "ID", "Status da Busca"
            ]
            
            # Renomear colunas para exibição
            display_col_names_map = {
                "Processo_Novo": "Processo",
                "Status_Geral": "Status Geral",
                "Observacao": "Observação",
                "Previsao_Pichau": "Previsão na Pichau",
                "Data_Embarque": "Data do Embarque",
                "ETA_Recinto": "ETA no Recinto",
                "Data_Registro": "Data de Registro",
                "ID": "ID do DB",
                "Status da Busca": "Status da Busca"
            }
            
            # Filtra apenas as colunas que realmente existem no DataFrame e renomeia
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
                }
            )
            
            # Filtra apenas os processos que foram realmente encontrados para edição
            processes_to_edit_ids = [p['ID'] for p in st.session_state.mass_edit_found_processes if p['ID'] != 'Não encontrado']
            
            if not processes_to_edit_ids:
                st.warning("Nenhum processo válido encontrado para edição. Por favor, corrija os nomes e tente novamente.")
                # Se não há processos válidos, desabilita a seção de edição
                st.session_state.mass_edit_can_proceed = False
            else:
                st.session_state.mass_edit_can_proceed = True
                st.markdown("---")
                st.markdown("#### 2. Selecionar Novos Valores") # Título ajustado

                # Campos de entrada individuais para cada coluna
                new_status_geral = st.selectbox(
                    "Novo Status Geral:",
                    options=[""] + db_manager.STATUS_OPTIONS, # Adiciona opção em branco para "não alterar"
                    key="mass_edit_new_status_value"
                )
                # Converte seleção de string vazia para None para o DB
                if new_status_geral == "":
                    new_status_geral = None

                # Campo de Observação:
                # Usamos uma variável de estado para rastrear se o campo foi "tocado"
                # Isso é uma heurística, pois Streamlit não tem um evento on_change para text_area que diferencia input vazio de não-input
                if 'mass_edit_observacao_touched' not in st.session_state:
                    st.session_state.mass_edit_observacao_touched = False

                new_observacao_input = st.text_area(
                    "Nova Observação:",
                    value="", # Começa em branco
                    key="mass_edit_new_observacao_value"
                )

                # Verifica se o campo de observação foi modificado pelo usuário
                # Isso é uma heurística: se o valor do widget não é a string vazia inicial, consideramos que foi "tocado"
                if new_observacao_input != "":
                    st.session_state.mass_edit_observacao_touched = True
                elif st.session_state.mass_edit_observacao_touched and new_observacao_input == "":
                    # Se foi tocado antes e agora está vazio, significa que o usuário limpou
                    pass # A variável touched permanece True, e a lógica de salvamento abaixo irá definir como None
                else:
                    # Se não foi tocado e continua vazio, não faz nada
                    st.session_state.mass_edit_observacao_touched = False


                # Lógica para campos de data
                # Previsão na Pichau
                new_previsao_pichau_date = st.date_input(
                    "Nova Previsão na Pichau:",
                    value=None, # Começa em branco
                    key="mass_edit_new_previsao_pichau_value",
                    format="DD/MM/YYYY"
                )
                new_previsao_pichau = new_previsao_pichau_date.strftime("%Y-%m-%d") if new_previsao_pichau_date else None


                # Data do Embarque
                new_data_embarque_date = st.date_input(
                    "Nova Data do Embarque:",
                    value=None, # Começa em branco
                    key="mass_edit_new_data_embarque_value",
                    format="DD/MM/YYYY"
                )
                new_data_embarque = new_data_embarque_date.strftime("%Y-%m-%d") if new_data_embarque_date else None


                # ETA no Recinto
                new_eta_recinto_date = st.date_input(
                    "Nova ETA no Recinto:",
                    value=None, # Começa em branco
                    key="mass_edit_new_eta_recinto_value",
                    format="DD/MM/YYYY"
                )
                new_eta_recinto = new_eta_recinto_date.strftime("%Y-%m-%d") if new_eta_recinto_date else None


                # Data de Registro
                new_data_registro_date = st.date_input(
                    "Nova Data de Registro:",
                    value=None, # Começa em branco
                    key="mass_edit_new_data_registro_value",
                    format="DD/MM/YYYY"
                )
                new_data_registro = new_data_registro_date.strftime("%Y-%m-%d") if new_data_registro_date else None


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
                                    original_process_data = dict(original_process_data_row) # Convertendo sqlite3.Row para dict
                                    
                                    # Dicionário para armazenar apenas as mudanças que serão aplicadas
                                    changes_to_apply = {}

                                    # Status Geral: só adiciona se um novo valor foi selecionado (não None)
                                    if new_status_geral is not None:
                                        changes_to_apply["Status_Geral"] = new_status_geral
                                    
                                    # Observacao:
                                    # Só altera se o campo foi "tocado" (digitado algo ou limpo explicitamente)
                                    if st.session_state.mass_edit_observacao_touched:
                                        changes_to_apply["Observacao"] = new_observacao_input if new_observacao_input != "" else None
                                    
                                    # Campos de data: só adiciona se uma nova data foi selecionada (não None)
                                    if new_previsao_pichau is not None:
                                        changes_to_apply["Previsao_Pichau"] = new_previsao_pichau
                                    if new_data_embarque is not None:
                                        changes_to_apply["Data_Embarque"] = new_data_embarque
                                    if new_eta_recinto is not None:
                                        changes_to_apply["ETA_Recinto"] = new_eta_recinto
                                    if new_data_registro is not None:
                                        changes_to_apply["Data_Registro"] = new_data_registro

                                    # Se não há mudanças a serem aplicadas para este processo, pule
                                    if not changes_to_apply:
                                        st.info(f"Nenhuma alteração detectada para o processo {original_process_data['Processo_Novo']} (ID: {p_id}).")
                                        continue

                                    # Prepara a tupla completa para atualização, preservando campos inalterados
                                    db_col_names_full = db_manager.obter_nomes_colunas_db()
                                    data_tuple_for_db = []
                                    for col_name in db_col_names_full:
                                        if col_name == 'id':
                                            continue
                                        if col_name in changes_to_apply:
                                            data_tuple_for_db.append(changes_to_apply[col_name])
                                        else:
                                            data_tuple_for_db.append(original_process_data.get(col_name)) # Usa o valor original

                                    if db_manager.atualizar_processo(p_id, tuple(data_tuple_for_db)):
                                        successful_updates_count += 1
                                        # Registra o histórico para cada alteração real
                                        for field_name, new_val in changes_to_apply.items():
                                            db_manager.inserir_historico_processo(p_id, field_name, original_process_data.get(field_name), new_val, username)
                                    else:
                                        st.error(f"Falha ao atualizar processo ID {p_id}.")
                                else:
                                    st.error(f"Processo ID {p_id} não encontrado para atualização.")

                            if successful_updates_count > 0:
                                st.success(f"{successful_updates_count} processos atualizados com sucesso!")
                                st.session_state.show_mass_edit_popup = False
                                st.session_state.mass_edit_process_names_input = "" # Limpa o input
                                st.session_state.mass_edit_found_processes = [] # Limpa os resultados
                                st.session_state.mass_edit_observacao_touched = False # Reseta o estado da observação
                                _load_processes() # Recarrega a tabela principal
                                st.rerun()
                            else:
                                st.warning("Nenhum processo foi atualizado ou nenhuma alteração foi detectada para aplicar.")

                with col_cancel:
                    if st.form_submit_button("Cancelar"):
                        st.session_state.show_mass_edit_popup = False
                        st.session_state.mass_edit_process_names_input = "" # Limpa o input
                        st.session_state.mass_edit_found_processes = [] # Limpa os resultados
                        st.session_state.mass_edit_observacao_touched = False # Reseta o estado da observação
                        st.rerun()
        else: # Se não há processos buscados, ainda pode cancelar
            col_empty, col_cancel_only = st.columns([0.7, 0.3])
            with col_cancel_only:
                if st.form_submit_button("Fechar"):
                    st.session_state.show_mass_edit_popup = False
                    st.session_state.mass_edit_process_names_input = "" # Limpa o input
                    st.session_state.mass_edit_found_processes = [] # Limpa os resultados
                    st.session_state.mass_edit_observacao_touched = False # Reseta o estado da observação
                    st.rerun()


# UI Principal
def show_page():
    # --- Configuração da Imagem de Fundo para a página Follow-up ---
    # Certifique-se de que o caminho para a imagem esteja correto
    background_image_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'assets', 'logo_navio_atracado.png')
    set_background_image(background_image_path)
    # --- Fim da Configuração da Imagem de Fundo ---

    st.subheader("Follow-up Importação")

    # Inicializa estados de sessão
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
    if 'show_followup_edit_popup' not in st.session_state:
        st.session_state.show_followup_edit_popup = False
    if 'followup_editing_process_id' not in st.session_state:
        st.session_state.followup_editing_process_id = None
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
    if 'show_mass_edit_popup' not in st.session_state: # NOVO: Estado para o pop-up de edição em massa
        st.session_state.show_mass_edit_popup = False
    if 'mass_edit_process_names_input' not in st.session_state: # NOVO: Input da área de texto de edição em massa
        st.session_state.mass_edit_process_names_input = ""
    if 'mass_edit_found_processes' not in st.session_state: # NOVO: Processos encontrados para edição em massa
        st.session_state.mass_edit_found_processes = []
    if 'mass_edit_can_proceed' not in st.session_state: # NOVO: Flag para habilitar/desabilitar a edição
        st.session_state.mass_edit_can_proceed = False


    # Chama os pop-ups primeiro (eles lidam com seus próprios reruns)
    _display_edit_process_popup()
    _display_filter_search_popup()
    _display_import_popup()
    _display_delete_confirm_popup()
    _display_mass_edit_popup() # NOVO: Chama o pop-up de edição em massa

    # Se qualquer pop-up estiver ativo, para de renderizar a página principal para evitar conflitos
    if st.session_state.get('show_followup_edit_popup', False) or \
       st.session_state.get('show_filter_search_popup', False) or \
       st.session_state.get('show_import_popup', False) or \
       st.session_state.get('show_delete_confirm_popup', False) or \
       st.session_state.get('show_mass_edit_popup', False): # NOVO: Verifica o pop-up de edição em massa
        return

    # Carrega os processos inicialmente e sempre que os filtros/termos de pesquisa mudam
    _load_processes() 

    st.markdown("---")
    
    # Linha 1: Adicionar Novo Processo, Filtros e Pesquisa, Expandir Todos, Recolher Todos, Edição em Massa
    # Larguras de coluna ajustadas para caber todos os 5 botões em uma linha
    col1_add, col1_filter, col1_mass_edit,  = st.columns([0.032, 0.03, 0.15]) 
    with col1_add:
        if st.button("Adicionar Novo Processo", key="add_new_process_button"):
            _open_edit_process_popup(None)
    with col1_filter:
        if st.button("Filtros e Pesquisa", key="open_filter_search_popup_button"):
            _open_filter_search_popup()
    with col1_mass_edit:
        if st.button("Editar Múltiplos Processos", key="mass_edit_processes_button"):
            _open_mass_edit_popup()

    # Linha 2: Pesquisar e Abrir para Editar (selectbox), Limpar Pesquisa, Abrir Edição
    # Larguras de coluna ajustadas para um layout mais compacto
    col2_search_select, col2_clear_search = st.columns([0.5, 0.2]) 
    with col2_search_select:
        # Cria um dicionário {nome_processo: id_processo} para o selectbox
        process_name_to_id_map = {p['Processo_Novo']: p['id'] for p in st.session_state.followup_processes_data if p.get('Processo_Novo')}
        sorted_process_names = [""] + sorted(process_name_to_id_map.keys())

        # Determina o índice padrão para o selectbox com base no termo de pesquisa atual
        current_search_term_for_selectbox = st.session_state.get('followup_search_terms', {}).get('Processo_Novo', '')
        try:
            default_selectbox_index = sorted_process_names.index(current_search_term_for_selectbox)
        except ValueError:
            default_selectbox_index = 0 # Padrão para a string vazia se não encontrado

        edited_process_name_selected = st.selectbox(
            "Pesquisar e Abrir para Editar:", 
            options=sorted_process_names,
            index=default_selectbox_index, # Usa o índice determinado dinamicamente
            key="followup_edit_process_name_search_input",
            label_visibility="visible"
        )
        
        # Atualiza o termo de pesquisa no estado da sessão se o valor do selectbox mudar
        # Isso irá disparar um rerun e _load_processes aplicará o filtro
        if edited_process_name_selected != current_search_term_for_selectbox:
            st.session_state.followup_search_terms['Processo_Novo'] = edited_process_name_selected
            st.rerun() # Dispara rerun para aplicar filtro e atualizar tabela

        # O botão "Abrir Edição" para o processo selecionado
        if edited_process_name_selected:
            selected_process_identifier = process_name_to_id_map.get(edited_process_name_selected)
            if selected_process_identifier:
                # O botão "Abrir Edição de '{edited_process_name_selected}'" está fora do formulário principal
                # e não precisa ser um st.form_submit_button.
                if st.button(f"Abrir Edição de '{edited_process_name_selected}'", key=f"edit_process_from_search_button_outside_form"):
                    _open_edit_process_popup(selected_process_identifier)
            else:
                pass 

    with col2_clear_search:
        st.markdown("<div style='height: 28px; visibility: hidden;'>.</div>", unsafe_allow_html=True) # Espaçamento invisível para alinhamento
        if st.button("Limpar Pesquisa", key="clear_process_search_button"):
            st.session_state.followup_search_terms['Processo_Novo'] = "" # Limpa o termo de pesquisa
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
    
    
    # A função _load_processes() no início de show_page() agora lida com a filtragem
    # Não há necessidade de uma segunda chamada aqui.

    if st.session_state.followup_processes_data:
        df_all_processes = pd.DataFrame(st.session_state.followup_processes_data)
        
        if 'Status_Geral' not in df_all_processes.columns:
            df_all_processes['Status_Geral'] = 'Sem Status'
        if 'Modal' not in df_all_processes.columns:
            df_all_processes['Modal'] = 'Sem Modal'
        
        df_all_processes['Status_Geral'] = df_all_processes['Status_Geral'].fillna('Sem Status')
        df_all_processes['Modal'] = df_all_processes['Modal'].fillna('Sem Modal')

        # Definir a ordem personalizada dos status
        custom_status_order = [
            'Encerrado','Chegada Pichau', 'Agendado', 'Liberado', 'Registrado',
            'Chegada Recinto', 'Embarcado', 'Verificando', 'Pré Embarque', 
            'Em produção', 'Processo Criado', 
            'Sem Status', 'Status Desconhecido', 'Arquivados' # Arquivados por último
        ]

        # Garantir que todos os status únicos no DF estejam na lista de ordem, adicionando-os no final se faltarem
        for status_val in df_all_processes['Status_Geral'].unique():
            if status_val not in custom_status_order:
                custom_status_order.append(status_val)

        # Criar uma categoria ordenada para a coluna 'Status_Geral'
        df_all_processes['Status_Geral'] = pd.Categorical(
            df_all_processes['Status_Geral'],
            categories=custom_status_order,
            ordered=True
        )

        df_all_processes = df_all_processes.sort_values(by=['Status_Geral', 'Modal'])

        # Usar `observed=False` para manter todas as categorias de status, mesmo que vazias no DF atual
        grouped_by_status = df_all_processes.groupby('Status_Geral', observed=False) 

        # --- Colunas a serem exibidas no st.dataframe ---
        display_columns_for_dataframe = [
            "Processo_Novo",  "Fornecedor", "Tipos_de_item","Observacao", "Data_Embarque", "ETA_Recinto",
            "Previsao_Pichau", "Documentos_Revisados", "Conhecimento_Embarque",
            "Descricao_Feita", "Descricao_Enviada","N_Invoice",
            "Quantidade", "Valor_USD", "Pago", "N_Ordem_Compra", "Data_Compra",
            "Estimativa_Impostos_BR", "Estimativa_Frete_USD", "Agente_de_Carga_Novo",
            "Caminho_da_pasta", "Origem", "Destino", "INCOTERM", "Comprador", "Navio",
            "Data_Registro",
            "DI_ID_Vinculada", # NOVO: Coluna para exibir o ID da DI vinculada
            "id" # Movido para o final
        ]
        # Filtrar apenas as colunas que realmente existem no DataFrame
        cols_to_display_in_table = [col for col in display_columns_for_dataframe if col in df_all_processes.columns]


        # --- Configuração das colunas para o st.dataframe ---
        column_config_for_dataframe = {
            "Processo_Novo": st.column_config.TextColumn("Processo", width="medium"),
            "Fornecedor": st.column_config.TextColumn("Fornecedor", width="small"),
            "Tipos_de_item": st.column_config.TextColumn("Tipo Item", width="small"),
            "Observacao": st.column_config.TextColumn("Observação", width="medium"),
            "Data_Embarque": st.column_config.TextColumn("Data Emb.", width="small"),
            "Data_ETA": st.column_config.TextColumn("Data ETA", width="small"),
            "Previsao_Pichau": st.column_config.TextColumn("Prev. Pichau", width="small"),
            "Documentos_Revisados": st.column_config.TextColumn("Docs Rev.", width="small"),
            "Conhecimento_Embarque": st.column_config.TextColumn("Conh. Emb.", width="small"),
            "Descricao_Feita": st.column_config.TextColumn("Desc. Feita", width="small"),
            "Descricao_Enviada": st.column_config.TextColumn("Desc. Envia.", width="small"),            
            "N_Invoice": st.column_config.TextColumn("Nº Invoice", width="small"),
            "Quantidade": st.column_config.TextColumn("Qtd", width="tiny"),
            "Valor_USD": st.column_config.TextColumn("Valor (US$)", width="small"),
            "Pago": st.column_config.TextColumn("Pago?", width="tiny"),
            "N_Ordem_Compra": st.column_config.TextColumn("Nº OC", width="small"),
            "Data_Compra": st.column_config.TextColumn("Data Compra", width="small"),
            "Estimativa_Impostos_BR": st.column_config.TextColumn("Est. Impostos (R$)", width="medium"),
            "Estimativa_Frete_USD": st.column_config.TextColumn("Est. Frete (US$)", width="medium"),
            "Agente_de_Carga_Novo": st.column_config.TextColumn("Agente Carga", width="small"),
            "Caminho_da_pasta": st.column_config.TextColumn("Caminho Pasta", width="small"),
            "Origem": st.column_config.TextColumn("Origem", width="small"),
            "Destino": st.column_config.TextColumn("Destino", width="small"),
            "INCOTERM": st.column_config.TextColumn("INCOTERM", width="small"),
            "Comprador": st.column_config.TextColumn("Comprador", width="small"),
            "Navio": st.column_config.TextColumn("Navio", width="small"),
            "ETA_Recinto": st.column_config.TextColumn("ETA Recinto", width="small"),
            "Data_Registro": st.column_config.TextColumn("Data Registro", width="small"),
            "DI_ID_Vinculada": st.column_config.TextColumn("DI Vinculada", width="small", help="Número da DI vinculada a este processo"), # NOVO: Configuração da coluna
            "Status_Geral": st.column_config.Column(disabled=True, width="tiny"),
            "Modal": st.column_config.Column(disabled=True, width="tiny"),
            "Status_Arquivado": st.column_config.Column(disabled=True, width="tiny"),
            "id": st.column_config.NumberColumn("ID", width="tiny", help="ID Único do Processo")
        }


        # Mapeamento de cores para os status (para os expanders)
        status_color_hex = {
            'Encerrado': '#404040',
            'Chegada Pichau': "#7F81D3",
            'Agendado': "#534E6B",
            'Liberado': '#A0A0A0',
            'Registrado': '#C0C0C0',
            'Chegada Recinto': '#008000',
            'Embarcado': '#6A0DAD', # Roxo para "Embarcado"
            'Pré Embarque': '#FFFFE0',
            'Verificando': '#F08080',
            'Em produção': '#FFB6C1',
            'Processo Criado': '#FFFFFF',            
            'Arquivados': '#C0C0C0', # Cinza para arquivados
            'Sem Status': '#909090',
            'Status Desconhecido': '#B0B0B0',
        }

        for status in custom_status_order:
            status_group_df = df_all_processes[df_all_processes['Status_Geral'] == status]
            
            if status_group_df.empty:
                continue

            bg_color = status_color_hex.get(status, '#333333')
            text_color = '#FFFFFF' if bg_color in ['#404040', '#6A0DAD', '#606060', '#333333'] else '#000000'

            # Aplica a cor de fundo apenas ao título do status, como era originalmente
            st.markdown(f"<h4 style='background-color:{bg_color}; color:{text_color}; padding: 10px 10px 10px 25px; border-radius: 15px; margin-bottom: 15px;'>Status: {status} - {len(status_group_df)} processo(s)</h4>", unsafe_allow_html=True)

            # O expander em si não terá a cor de fundo, apenas o conteúdo dentro dele
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
                    if "Estimativa_Impostos_BR" in df_modal_display.columns:
                        df_modal_display["Estimativa_Impostos_BR"] = df_modal_display["Estimativa_Impostos_BR"].apply(_format_currency_display)
                    if "Quantidade" in df_modal_display.columns:
                        df_modal_display["Quantidade"] = df_modal_display["Quantidade"].apply(_format_int_display)
                    for col_name in ["Documentos_Revisados", "Conhecimento_Embarque", "Descricao_Feita", "Descricao_Enviada", "Pago"]:
                        if col_name in df_modal_display.columns:
                            df_modal_display[col_name] = df_modal_display[col_name].apply(lambda x: "✅ Sim" if str(x).lower() == "sim" else ("⚠️ Não" if str(x).lower() == "não" else ""))
                    
                    # NOVO: Formatar a coluna DI_ID_Vinculada para exibir o número da DI
                    if 'DI_ID_Vinculada' in df_modal_display.columns:
                        df_modal_display['DI_ID_Vinculada'] = df_modal_display['DI_ID_Vinculada'].apply(lambda di_id: _get_di_number_from_id(di_id) if di_id else "N/A")

                    selected_rows_data = st.dataframe(
                        df_modal_display[cols_to_display_in_table], # DataFrame formatado e com 'id' visível no final
                        key=f"dataframe_group_{status}_{modal}",
                        hide_index=True,
                        use_container_width=True,
                        column_config=column_config_for_dataframe, 
                        selection_mode='single-row', 
                        on_select='rerun', 
                    )

                    # --- Botões de Ação para Linha Selecionada ---
                    if selected_rows_data and selected_rows_data['selection']['rows']:
                        selected_index_in_df_modal = selected_rows_data['selection']['rows'][0]
                        
                        # Obter o Processo_Novo da linha selecionada na tabela exibida
                        selected_process_name_from_display = df_modal_display.iloc[selected_index_in_df_modal]['Processo_Novo']

                        # Usar o Processo_Novo para buscar o ID correspondente na lista original de dados
                        selected_original_process = next((p for p in st.session_state.followup_processes_data if p.get('Processo_Novo') == selected_process_name_from_display), None)

                        if selected_original_process:
                            selected_process_id = selected_original_process['id']
                            selected_process_name = selected_original_process['Processo_Novo']
                            
                            col_edit_btn, col_delete_btn = st.columns(2)
                            with col_edit_btn:
                                if st.button(f"Editar Processo Selecionado: {selected_process_name}", key=f"edit_selected_btn_{selected_process_id}"):
                                    _open_edit_process_popup(selected_process_id)
                            with col_delete_btn:
                                if st.button(f"Excluir Processo Selecionado: {selected_process_name}", key=f"delete_selected_btn_{selected_process_id}"):
                                    # Ativar o pop-up de confirmação de exclusão
                                    st.session_state.show_delete_confirm_popup = True
                                    st.session_state.delete_process_id_to_confirm = selected_process_id
                                    st.session_state.delete_process_name_to_confirm = selected_process_name
                                    st.rerun() # Força um rerun para exibir o pop-up
                        else:
                            st.error(f"Erro: Processo '{selected_process_name_from_display}' não encontrado nos dados originais para edição/exclusão.")
    else:
        st.info("Nenhum processo de importação encontrado. Adicione um novo ou importe via arquivo.")

    st.markdown("---")
    # NOVO: Botão "Importação de dados" no final da página
    col_import_data_btn, _ = st.columns([0.2, 0.8]) # Usar uma coluna para o botão e outra vazia para espaçamento
    with col_import_data_btn:
        if st.button("Importação de Dados", key="open_import_options_button_bottom"):
            st.session_state.show_import_popup = True
            st.rerun()

    st.write("Esta tela permite gerenciar o follow-up de processos de importação.")

    # NOVO: Aviso de conexão do banco no final da pagina
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
        st.error(f"Não foi possível conectar ao banco de dados de Follow-up em: {db_manager.get_db_path()}")
