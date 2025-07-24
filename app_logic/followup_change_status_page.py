import streamlit as st
from datetime import datetime, date # NOVO: Importar 'date' explicitamente
from typing import Any, Optional, Dict, List
import sys
import os
import pandas as pd # Importar pandas para manipulação de dados
import io # Importar io para manipulação de streams de I/O
import gspread # Importar gspread para Google Sheets
from oauth2client.service_account import ServiceAccountCredentials # Importar para autenticação Google Sheets

# Configuração de logging para este módulo
import logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Adiciona o diretório pai ao sys.path para importações relativas
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Importar db_manager (assumindo que está no diretório pai)
import followup_db_manager as db_manager

# NOVO: Importar db_utils para acesso às funções de DI/XML
try:
    from app_logic import db_utils
except ImportError:
    logger.error("Módulo 'app_logic.db_utils' não encontrado. Funções de DI/XML podem não funcionar.")
    # Mock básico para evitar quebras, mas a funcionalidade não estará presente
    class MockDbUtils:
        def parse_xml_data_to_dict(self, xml_content): return None, None
        def get_declaracao_by_id(self, di_id): return None
        def get_declaracao_by_referencia(self, ref): return None
        def save_parsed_di_data(self, di_data, itens_data): return False
        def _clean_reference_string(self, s): return s if s is not None else ''
    db_utils = MockDbUtils()


# Importar funções de utilidade do módulo utils
try:
    from app_logic.utils import set_background_image
except ImportError:
    logging.warning("Módulo 'app_logic.utils' não encontrado. Funções de imagem de fundo podem não funcionar.")
    def set_background_image(image_path, opacity=None):
        pass # Função mock se utils não for encontrado

# REMOVIDO: Importação direta de _partial_cache_update_after_edit.
# A função será passada como argumento para display_change_status_page.
# try:
#     from app_logic.followup_importacao_page import _partial_cache_update_after_edit
# except ImportError:
#     logger.error("Não foi possível importar _partial_cache_update_after_edit de followup_importacao_page.")
#     def _partial_cache_update_after_edit(process_id: Any, update_type: str):
#         st.error("Erro interno: Função de atualização de cache não carregada.")
#         return False

# Adicionado safe_float para robustez (copiado de process_query_page)
def safe_float(value: Any, default_value: float = 0.0) -> float:
    """
    Tenta converter um valor para float. Retorna default_value se a conversão falhar.
    Útil para lidar com valores potencialmente não numéricos em dados.
    """
    if value is None:
        return default_value
    try:
        if isinstance(value, str):
            value = value.replace(',', '.')
        return float(value)
    except (ValueError, TypeError):
        return default_value

def _format_di_number(di_number):
    """Formata o número da DI para o padrão **/*******-*."""
    if di_number and isinstance(di_number, str) and len(di_number) == 10:
        return f"{di_number[0:2]}/{di_number[2:9]}-{di_number[9]}"
    return di_number

# NOVO: Função para formatar data para exibição DD/MM/AAAA
def _format_date_for_display_ddmmyyyy(date_obj: Optional[date]) -> str: # Usar date de datetime
    """Formata um objeto date para exibição no formato DD/MM/AAAA."""
    if date_obj:
        return date_obj.strftime("%d/%m/%Y")
    return "N/A"

def _handle_xml_di_upload(process_data_in_session_state: Dict[str, Any], uploaded_file: Any, unique_key_prefix: str):
    """Lida com o upload de um XML da DI, parseia, salva e tenta vincular ao processo."""
    if uploaded_file is not None:
        # Gerar um hash único para o arquivo XML
        current_file_hash = uploaded_file.name + str(uploaded_file.size) + uploaded_file.type
        
        if st.session_state.get(f'{unique_key_prefix}_last_uploaded_xml_di_hash') != current_file_hash:
            try:
                xml_content = uploaded_file.getvalue().decode("utf-8")
                # AGORA: Chama db_utils.parse_xml_data_to_dict
                di_data_parsed, itens_data_parsed_raw = db_utils.parse_xml_data_to_dict(xml_content)
                itens_data_parsed = itens_data_parsed_raw if itens_data_parsed_raw is not None else []

                if di_data_parsed:
                    # AGORA: Chama db_utils._clean_reference_string
                    processo_novo_ref = db_utils._clean_reference_string(process_data_in_session_state.get('Processo_Novo'))
                    if not processo_novo_ref:
                        st.error("Não foi possível vincular a DI: O processo atual não tem uma referência válida ('Processo Novo').")
                        st.session_state[f'{unique_key_prefix}_last_uploaded_xml_di_hash'] = None
                        return

                    di_numero_from_xml = di_data_parsed.get('numero_di')
                    if not di_numero_from_xml:
                        st.error("Não foi possível extrair o número da DI do arquivo XML. Verifique o formato do arquivo.")
                        st.session_state[f'{unique_key_prefix}_last_uploaded_xml_di_hash'] = None
                        return
                    
                    # AGORA: Chama db_utils.get_declaracao_by_id
                    existing_di_by_num = db_utils.get_declaracao_by_id(di_numero_from_xml)
                    if existing_di_by_num:
                        st.warning(f"Uma DI com o número '{_format_di_number(di_numero_from_xml)}' já existe no banco de dados. Importação não realizada.")
                        st.session_state[f'{unique_key_prefix}_last_uploaded_xml_di_hash'] = None
                        return

                    # Vincular a DI ao processo atual pela referência (informacao_complementar)
                    di_data_parsed['informacao_complementar'] = processo_novo_ref
                    
                    # AGORA: Chama db_utils.save_parsed_di_data
                    success = db_utils.save_parsed_di_data(di_data_parsed, itens_data_parsed)

                    if success:
                        st.success(f"XML da DI '{_format_di_number(di_numero_from_xml)}' importado e vinculado ao processo '{processo_novo_ref}' com sucesso!")
                        
                        # AGORA: Chama db_utils.get_declaracao_by_referencia
                        newly_saved_di_data = db_utils.get_declaracao_by_referencia(processo_novo_ref)
                        if newly_saved_di_data and 'id' in newly_saved_di_data:
                            process_data_in_session_state['DI_ID_Vinculada'] = newly_saved_di_data['id']
                            st.session_state[f'{unique_key_prefix}_last_uploaded_xml_di_hash'] = current_file_hash
                            # Não precisa de rerun aqui, o formulário já vai submeter e recarregar
                        else:
                            st.warning("DI importada, mas não foi possível obter o ID para vincular automaticamente ao processo.")
                            st.session_state[f'{unique_key_prefix}_last_uploaded_xml_di_hash'] = None
                    else:
                        st.error("Falha ao salvar a DI importada no banco de dados.")
                        st.session_state[f'{unique_key_prefix}_last_uploaded_xml_di_hash'] = None
                else:
                    st.error("Não foi possível extrair dados válidos do arquivo XML da DI. Verifique o formato do arquivo.")
                    st.session_state[f'{unique_key_prefix}_last_uploaded_xml_di_hash'] = None
            except Exception as e:
                st.error(f"Erro ao processar o arquivo XML da DI: {e}")
                logger.error(f"Erro ao processar o arquivo XML da DI: {e}", exc_info=True)
                st.session_state[f'{unique_key_prefix}_last_uploaded_xml_di_hash'] = None

def _change_process_status_action(process_id: Any, new_status: str, new_observacao: Optional[str], current_username: str, additional_updates: Dict[str, Any], reload_processes_callback: Optional[callable]):
    """Altera o status, observação e campos adicionais de um processo no banco de dados."""
    with st.spinner("Atualizando status do processo..."):
        # Tenta obter os dados originais do processo usando o Processo_Novo (string) primeiro
        # Isso é mais robusto se o Firestore estiver a usar Processo_Novo como ID do documento
        original_process_data_raw = db_manager.obter_processo_by_processo_novo(process_id)
        if not original_process_data_raw:
            # Se não encontrar pelo Processo_Novo, tenta pelo ID numérico (fallback para SQLite)
            original_process_data_raw = db_manager.obter_processo_por_id(process_id)

        if not original_process_data_raw:
            st.error(f"Processo ID {process_id} não encontrado para alteração de status/observação.")
            return

        original_process_data = dict(original_process_data_raw)
        
        updates = {}
        # Adiciona o status e observação se houver mudança
        if new_status != original_process_data.get('Status_Geral'):
            updates["Status_Geral"] = new_status
        if new_observacao != original_process_data.get('Observacao'): 
            updates["Observacao"] = new_observacao
        
        # Adiciona os campos adicionais passados
        for key, value in additional_updates.items():
            # NOVO: Garante que o valor da data seja convertido para string antes de adicionar aos updates
            if isinstance(value, date): # Verifica se é um objeto date (retornado por st.date_input)
                value = value.strftime("%Y-%m-%d") # Converte para string YYYY-MM-DD
            # Verifica se o valor mudou antes de adicionar aos updates
            if value != original_process_data.get(key):
                updates[key] = value

        # Define o ID de atualização a ser usado no db_manager.atualizar_processo
        # Se estiver a usar Firestore, o ID será o Processo_Novo. Caso contrário, será o ID numérico.
        update_target_id = process_id # Assume que process_id já é o Processo_Novo ou o ID numérico
        if db_manager._USE_FIRESTORE_AS_PRIMARY:
            update_target_id = original_process_data.get('Processo_Novo')


        if updates: 
            if db_manager.atualizar_processo(update_target_id, updates):
                # Registrar histórico para cada campo que foi atualizado
                for field, new_value in updates.items():
                    old_value = original_process_data.get(field)
                    db_manager.inserir_historico_processo(
                        update_target_id, field, old_value, new_value, # Usa update_target_id para o histórico
                        current_username, db_type="Firestore" if db_manager._USE_FIRESTORE_AS_PRIMARY else "SQLite"
                    )
                
                st.toast(f"✅ Status alterado com sucesso!", icon="✅") # NOVO: Mensagem de sucesso
            else:
                st.error(f"Falha ao atualizar processo ID {process_id}.")
        else:
            st.info("Nenhuma alteração de status ou observação detectada.")
        
        # Atualiza o cache da página principal usando o callback fornecido
        if reload_processes_callback:
            success = reload_processes_callback(process_id, "status_change")
            if not success:
                st.session_state.all_processes_raw_data_cache = []
                st.session_state.consolidated_groups_data_raw_cache = []
        else:
            logger.warning("reload_processes_callback não fornecido. O cache da página principal pode não ser atualizado.")
        
        # REMOVIDO: Navegação automática e rerun daqui
        # st.session_state.current_page = "Follow-up Importação"
        # st.rerun()

        # NOVO: Define a flag para mostrar o botão de retorno
        st.session_state.show_return_button_after_save = True


def _on_new_status_change_callback():
    """Callback para forçar o re-render da página quando o status é alterado."""
    # Atualiza o st.session_state.new_status_selected_for_display com o valor do selectbox
    st.session_state.new_status_selected_for_display = st.session_state.new_status_selectbox_page
    # Removido st.rerun() - a alteração no session_state já aciona o rerun automaticamente
    

def display_change_status_page(reload_processes_callback: Optional[callable] = None): # NOVO: Aceita callback como argumento
    """Exibe a página dedicada para alterar o status e a observação de um processo."""
    background_image_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'assets', 'logo_navio_atracado.png')
    set_background_image(background_image_path)

    st.subheader("Alterar Status do Processo")

    process_id = st.session_state.get('process_id_to_change_status')
    process_name = st.session_state.get('process_name_to_change_status')
    current_username = st.session_state.get('user_info', {}).get('username', 'Desconhecido')

    if process_id is None:
        st.warning("Nenhum processo selecionado para alteração de status. Retornando para a página principal.")
        st.session_state.current_page = "Follow-up Importação"
        st.rerun()
        return

    # Tenta obter os dados mais recentes do processo
    # Prioriza a busca por Processo_Novo (string) para consistência com Firestore
    current_process_data = db_manager.obter_processo_by_processo_novo(process_id)
    if not current_process_data:
        # Fallback para ID numérico se Processo_Novo não funcionar
        current_process_data = db_manager.obter_processo_por_id(process_id)

    if not current_process_data:
        st.error(f"Processo '{process_name}' (ID: {process_id}) não encontrado para alteração de status/observação.")
        st.session_state.current_page = "Follow-up Importação"
        st.rerun()
        return

    current_status = current_process_data.get('Status_Geral')
    current_observacao = current_process_data.get('Observacao', '')
    current_modal = current_process_data.get('Modal', 'N/A')
    
    # Inicializa st.session_state.new_status_selected_for_display na primeira carga ou mudança de processo
    if 'new_status_selected_for_display' not in st.session_state or \
       st.session_state.get('last_process_id_for_status_change') != process_id:
        st.session_state.new_status_selected_for_display = current_status
        st.session_state.last_process_id_for_status_change = process_id
        st.session_state.show_return_button_after_save = False # NOVO: Reseta a flag ao carregar um novo processo

    st.markdown(f"### Ajustar Status e Observação para: **{process_name}**")

    status_options = db_manager.STATUS_OPTIONS
    default_index_status = 0
    if current_status in status_options:
        default_index_status = status_options.index(current_status)
    
    # Selectbox fora do formulário para permitir on_change
    st.session_state.new_status_selected_for_display = st.selectbox(
        "Novo Status:", 
        options=status_options, 
        index=default_index_status, 
        key="new_status_selectbox_page",
        on_change=_on_new_status_change_callback # Adicionado o callback aqui
    )

    # Variáveis para os campos condicionais (inicializadas com None ou False)
    new_previsao_pichau = None
    new_eta_recinto = None
    new_data_embarque = None
    new_navio = None
    archive_process = False
    uploaded_xml_di_file = None

    # O formulário que conterá os campos condicionais e o botão de submissão
    with st.form(key=f"change_status_form_page_{process_id}"):
        # Usa o status selecionado do session_state para renderizar campos condicionais
        selected_new_status = st.session_state.new_status_selected_for_display

        if selected_new_status == 'Encerrado':
            archive_process = st.checkbox("Deseja arquivar o processo?", key="archive_process_checkbox")
        
        elif selected_new_status == 'Pré Embarque' or selected_new_status == 'Embarcado':
            st.markdown("---")
            st.markdown("#### Detalhes de Embarque/Chegada")
            
            # Converte as datas atuais para objetos datetime para os date_input
            current_previsao_pichau_dt = None
            if current_process_data.get('Previsao_Pichau'):
                try:
                    current_previsao_pichau_dt = datetime.strptime(current_process_data['Previsao_Pichau'], "%Y-%m-%d")
                except ValueError:
                    pass

            current_eta_recinto_dt = None
            if current_process_data.get('ETA_Recinto'):
                try:
                    current_eta_recinto_dt = datetime.strptime(current_process_data['ETA_Recinto'], "%Y-%m-%d")
                except ValueError:
                    pass

            current_data_embarque_dt = None
            if current_process_data.get('Data_Embarque'):
                try:
                    current_data_embarque_dt = datetime.strptime(current_process_data['Data_Embarque'], "%Y-%m-%d")
                except ValueError:
                    pass

            new_previsao_pichau = st.date_input(
                "Previsão Pichau:", 
                value=current_previsao_pichau_dt, 
                key="previsao_pichau_dateinput",
                format="DD/MM/YYYY" # Adicionado o formato
            )
            # Removido st.markdown de data selecionada abaixo do campo, pois o formato agora está no campo
            # if new_previsao_pichau: # Exibe a data formatada
            #     st.markdown(f"**Data selecionada:** {_format_date_for_display_ddmmyyyy(new_previsao_pichau)}")

            new_eta_recinto = st.date_input(
                "ETA Recinto:", 
                value=current_eta_recinto_dt, 
                key="eta_recinto_dateinput",
                format="DD/MM/YYYY" # Adicionado o formato
            )
            # Removido st.markdown de data selecionada abaixo do campo
            # if new_eta_recinto: # Exibe a data formatada
            #     st.markdown(f"**Data selecionada:** {_format_date_for_display_ddmmyyyy(new_eta_recinto)}")

            new_data_embarque = st.date_input(
                "Data de Embarque:", 
                value=current_data_embarque_dt, 
                key="data_embarque_dateinput",
                format="DD/MM/YYYY" # Adicionado o formato
            )
            # Removido st.markdown de data selecionada abaixo do campo
            # if new_data_embarque: # Exibe a data formatada
            #     st.markdown(f"**Data selecionada:** {_format_date_for_display_ddmmyyyy(new_data_embarque)}")

            if current_modal in ['Maritimo', 'Consolidado']:
                new_navio = st.text_input(
                    "Navio:", 
                    value=current_process_data.get('Navio', ''), 
                    key="navio_textinput"
                )

        elif selected_new_status == 'Chegada Recinto':
            st.markdown("---")
            st.markdown("#### Detalhes de Chegada no Recinto")
            
            current_previsao_pichau_dt = None
            if current_process_data.get('Previsao_Pichau'):
                try:
                    current_previsao_pichau_dt = datetime.strptime(current_process_data['Previsao_Pichau'], "%Y-%m-%d")
                except ValueError:
                    pass

            current_eta_recinto_dt = None
            if current_process_data.get('ETA_Recinto'):
                try:
                    current_eta_recinto_dt = datetime.strptime(current_process_data['ETA_Recinto'], "%Y-%m-%d")
                except ValueError:
                    pass

            new_previsao_pichau = st.date_input(
                "Previsão Pichau:", 
                value=current_previsao_pichau_dt, 
                key="previsao_pichau_dateinput_chegada",
                format="DD/MM/YYYY" # Adicionado o formato
            )
            # Removido st.markdown de data selecionada abaixo do campo
            # if new_previsao_pichau: # Exibe a data formatada
            #     st.markdown(f"**Data selecionada:** {_format_date_for_display_ddmmyyyy(new_previsao_pichau)}")

            new_eta_recinto = st.date_input(
                "ETA Recinto:", 
                value=current_eta_recinto_dt, 
                key="eta_recinto_dateinput_chegada",
                format="DD/MM/YYYY" # Adicionado o formato
            )
            # Removido st.markdown de data selecionada abaixo do campo
            # if new_eta_recinto: # Exibe a data formatada
            #     st.markdown(f"**Data selecionada:** {_format_date_for_display_ddmmyyyy(new_eta_recinto)}")

        elif selected_new_status == 'Registrado':
            st.markdown("---")
            st.markdown("#### Detalhes de Registro")
            
            current_previsao_pichau_dt = None
            if current_process_data.get('Previsao_Pichau'):
                try:
                    current_previsao_pichau_dt = datetime.strptime(current_process_data['Previsao_Pichau'], "%Y-%m-%d")
                except ValueError:
                    pass
            new_previsao_pichau = st.date_input(
                "Previsão Pichau:", 
                value=current_previsao_pichau_dt, 
                key="previsao_pichau_dateinput_registrado",
                format="DD/MM/YYYY" # Adicionado o formato
            )
            # Removido st.markdown de data selecionada abaixo do campo
            # if new_previsao_pichau: # Exibe a data formatada
            #     st.markdown(f"**Data selecionada:** {_format_date_for_display_ddmmyyyy(new_previsao_pichau)}")

            st.markdown("##### Inserir DI (XML)")
            # Lógica de busca da DI associada para exibir o status
            # AGORA: Chama db_utils.get_declaracao_by_referencia
            declaracao_di_data = db_utils.get_declaracao_by_referencia(current_process_data.get('Processo_Novo'))
            if declaracao_di_data:
                st.info(f"Declaração de Importação associada: **{_format_di_number(declaracao_di_data.get('numero_di', 'N/A'))}**")
            else:
                st.info(f"Ao importar um XML, a DI será salva e vinculada a esta referência: **{current_process_data.get('Processo_Novo', 'N/A')}**")

            uploaded_xml_di_file = st.file_uploader(
                "Carregar XML da DI",
                type=["xml"],
                key=f"di_xml_uploader_{process_id}"
            )
            # O processamento do upload será feito no submit do formulário
            
        elif selected_new_status == 'Liberado':
            st.markdown("---")
            st.markdown("#### Detalhes de Liberação")
            
            current_previsao_pichau_dt = None
            if current_process_data.get('Previsao_Pichau'):
                try:
                    current_previsao_pichau_dt = datetime.strptime(current_process_data['Previsao_Pichau'], "%Y-%m-%d")
                except ValueError:
                    pass
            new_previsao_pichau = st.date_input(
                "Previsão Pichau:", 
                value=current_previsao_pichau_dt, 
                key="previsao_pichau_dateinput_liberado",
                format="DD/MM/YYYY" # Adicionado o formato
            )
            # Removido st.markdown de data selecionada abaixo do campo
            # if new_previsao_pichau: # Exibe a data formatada
            #     st.markdown(f"**Data selecionada:** {_format_date_for_display_ddmmyyyy(new_previsao_pichau)}")

        new_observacao = st.text_area("Observação:", value=current_observacao, key="new_observacao_textarea_page")

        col_apply, col_cancel = st.columns(2)
        with col_apply:
            if st.form_submit_button("Aplicar Alterações"):
                updates_to_db = {}
                
                # Adiciona campos de data, se existirem
                if new_previsao_pichau is not None:
                    updates_to_db['Previsao_Pichau'] = new_previsao_pichau
                if new_eta_recinto is not None:
                    updates_to_db['ETA_Recinto'] = new_eta_recinto
                if new_data_embarque is not None:
                    updates_to_db['Data_Embarque'] = new_data_embarque
                if new_navio is not None:
                    updates_to_db['Navio'] = new_navio
                
                # Lógica para arquivar o processo se o checkbox estiver marcado
                if selected_new_status == 'Encerrado' and archive_process:
                    updates_to_db['Status_Arquivado'] = 'Arquivado'
                elif selected_new_status != 'Encerrado' and current_process_data.get('Status_Arquivado') == 'Arquivado':
                    # Se o status mudou de Encerrado para outro, e estava arquivado, desarquiva
                    updates_to_db['Status_Arquivado'] = 'Não Arquivado'

                # Processar upload da DI se o status for 'Registrado'
                if selected_new_status == 'Registrado' and uploaded_xml_di_file:
                    _handle_xml_di_upload(current_process_data, uploaded_xml_di_file, f"change_status_page_{process_id}")
                    # A DI_ID_Vinculada será atualizada em current_process_data dentro de _handle_xml_di_upload
                    # e será salva no _change_process_status_action

                _change_process_status_action(process_id, selected_new_status, new_observacao, current_username, updates_to_db, reload_processes_callback) # Passa o callback
        with col_cancel:
            if st.form_submit_button("Cancelar"):
                st.session_state.current_page = "Follow-up Importação"
                st.rerun()

    # Este bloco foi movido para FORA do st.form
    # Ele só será renderizado se selected_new_status for 'Registrado'
    if selected_new_status == 'Registrado':
        # Re-obter declaracao_di_data aqui para garantir que esteja atualizado após um possível upload
        declaracao_di_data = db_utils.get_declaracao_by_referencia(current_process_data.get('Processo_Novo'))
        if declaracao_di_data:
            st.markdown("---")
            col_di_buttons = st.columns(2)
            with col_di_buttons[0]:
                if st.button("Pagamentos da DI", key=f"btn_pagamentos_di_{process_id}"):
                    st.session_state.current_page = "Pagamentos"
                    st.session_state.detalhes_di_input_text = declaracao_di_data.get('informacao_complementar')
                    st.rerun()
            with col_di_buttons[1]:
                if st.button("Acessar Custo do Processo da DI", key=f"btn_acessar_custo_di_{process_id}"):
                    st.session_state.current_page = "Custo do Processo"
                    st.session_state.custo_search_ref_input = declaracao_di_data.get('informacao_complementar')
                    st.rerun()
            st.markdown("---")

    # NOVO: Botão separado para voltar para a tela de Follow-up (visível após a tentativa de salvar)
    if st.session_state.get('show_return_button_after_save', False):
        if st.button("⬅️ Voltar para Follow-up Importação", key=f"return_to_followup_btn_{process_id}"):
            st.session_state.current_page = "Follow-up Importação"
            st.session_state.show_return_button_after_save = False # Reseta a flag para a próxima vez
            st.rerun()
