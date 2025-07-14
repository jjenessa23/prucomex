import streamlit as st
import pandas as pd
from datetime import datetime, date
import logging
import os
import uuid
from typing import Any, Dict, List, Optional, Union
import base64
import followup_db_manager as db_manager # Importa o módulo de gerenciamento de banco de dados

# Configura o logger
logger = logging.getLogger(__name__)

# --- Funções Auxiliares de UI e Formatação (copiadas para serem auto-contidas) ---

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

# --- Lógica principal da nova tela de Edição Múltipla ---

def show_page():
    """
    Exibe a tela dedicada para edição em massa de processos.
    Permite buscar processos por nome e aplicar alterações em massa a campos selecionados.
    """
    background_image_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'assets', 'logo_navio_atracado.png')
    set_background_image(background_image_path)

    st.subheader("Editar Múltiplos Processos")
    st.info("Insira os nomes dos processos para buscar e aplicar alterações em massa.")

    # Inicializa estados da sessão específicos desta página
    st.session_state.setdefault('mass_edit_process_names_input', "")
    st.session_state.setdefault('mass_edit_found_processes', [])
    st.session_state.setdefault('mass_edit_can_proceed', False)
    st.session_state.setdefault('mass_edit_observacao_touched', False) # Para controlar a observação vazia
    # NOVO: Adiciona um contador para forçar a re-renderização do text_area de busca
    st.session_state.setdefault('mass_edit_search_form_key_counter', 0)
    # NOVO: Adiciona um contador para forçar a re-renderização do formulário de aplicação de alterações
    st.session_state.setdefault('mass_edit_apply_changes_form_key_counter', 0)


    # Definições mock para STATUS_OPTIONS e MODAL_OPTIONS, caso não venham do db_manager
    # É ALTAMENTE RECOMENDADO QUE ESSAS OPÇÕES SEJAM MANTIDAS NO SEU ARQUIVO db_manager.py
    # ou em um arquivo de configuração/constantes centralizado.
    # Estas são apenas para fins de evitar o AttributeError.
    if not hasattr(db_manager, 'STATUS_OPTIONS'):
        db_manager.STATUS_OPTIONS = [
            'Encerrado', 'Chegada Pichau', 'Agendado', 'Liberado', 'Registrado',
            'Chegada Recinto', 'Embarcado', 'Verificando', 'Limbo Consolidado',
            'Limbo Saldo', 'Pré Embarque', 'Em produção', 'Processo Criado',
            'Sem Status', 'Status Desconhecido', 'Arquivados'
        ]
    
    if not hasattr(db_manager, 'MODAL_OPTIONS'):
        db_manager.MODAL_OPTIONS = ['Aéreo', 'Maritimo', 'Rodoviário', 'Consolidado'] # Exemplo de opções de modal


    # FORM 1: Busca de Processos
    # Usa a key dinâmica para garantir que o formulário e seus widgets sejam resetados
    with st.form(key=f"process_search_form_{st.session_state.mass_edit_search_form_key_counter}"):
        st.markdown("#### 1. Inserir Processos para Edição")
        process_names_input = st.text_area(
            "Insira os nomes dos processos (um por linha):",
            value=st.session_state.mass_edit_process_names_input,
            height=150,
            key=f"mass_edit_process_names_textarea_page_{st.session_state.mass_edit_search_form_key_counter}" # Usa a key dinâmica aqui também
        )
        
        # Colunas para alinhar os botões de busca e limpar busca (MOVIDAS PARA DENTRO DO FORM)
        col_search_button, col_clear_search_button = st.columns([0.3, 0.7])

        with col_search_button:
            # st.form_submit_button deve estar dentro do st.form
            if st.form_submit_button("Buscar Processos"):
                st.session_state.mass_edit_process_names_input = process_names_input
                
                st.session_state.mass_edit_found_processes = []
                if process_names_input:
                    names_to_search = [name.strip() for name in process_names_input.split('\n') if name.strip()]
                    for name in names_to_search:
                        process_data_row = db_manager.obter_processo_by_processo_novo(name)
                        
                        found_entry = {
                            'Processo_Novo': name, 'ID': 'Não encontrado', 'Status da Busca': 'Não encontrado',
                            'Status_Geral': 'N/A', 'Observacao': 'N/A', 'Previsao_Pichau': 'N/A',
                            'Data_Embarque': 'N/A', 'ETA_Recinto': 'N/A', 'Data_Registro': 'N/A',
                            'Estimativa_Impostos_Total': 0.0, # Valor numérico
                            'Nota_feita': 'N/A', # 'Nota_feita' permanece para exibição, mas será removido da edição
                        }

                        if process_data_row:
                            process_data = dict(process_data_row) 
                            found_entry.update({
                                'Processo_Novo': process_data['Processo_Novo'],
                                'ID': process_data.get('id', 'N/A'), # Firestore pode ter ID como Processo_Novo
                                'Status da Busca': 'Encontrado',
                                'Status_Geral': process_data.get('Status_Geral', 'N/A'),
                                'Observacao': process_data.get('Observacao', 'N/A'),
                                'Previsao_Pichau': _format_date_display(process_data.get('Previsao_Pichau')),
                                'Data_Embarque': _format_date_display(process_data.get('Data_Embarque')),
                                'ETA_Recinto': _format_date_display(process_data.get('ETA_Recinto')),
                                'Data_Registro': _format_date_display(process_data.get('Data_Registro')),
                                'Estimativa_Impostos_Total': process_data.get('Estimativa_Impostos_Total', 0.0), # Armazena o valor numérico
                                'Nota_feita': process_data.get('Nota_feita', 'N/A'),
                            })
                        st.session_state.mass_edit_found_processes.append(found_entry)
                
                st.session_state.mass_edit_can_proceed = any(p['ID'] != 'Não encontrado' for p in st.session_state.mass_edit_found_processes)
                # O rerun não é necessário aqui, pois o submit do formulário já causa um rerun
        
        # Botão "Limpar Busca" agora é um form_submit_button dentro do formulário de busca
        with col_clear_search_button:
            # Adiciona um pequeno espaço para melhor alinhamento visual, se necessário
            st.markdown("<div style='height: 25px;'></div>", unsafe_allow_html=True) 
            if st.form_submit_button("Limpar Busca"): # AGORA É UM form_submit_button
                st.session_state.mass_edit_process_names_input = ""
                st.session_state.mass_edit_found_processes = []
                st.session_state.mass_edit_can_proceed = False
                # NOVO: Incrementa o contador para forçar o reset do text_area de busca E do formulário de edição
                st.session_state.mass_edit_search_form_key_counter += 1
                st.session_state.mass_edit_apply_changes_form_key_counter += 1 # Resetar o segundo formulário também
                # Não é necessário st.rerun() aqui, pois o form_submit_button já causa um rerun

    if st.session_state.mass_edit_found_processes:
        st.markdown("#### Resultados da Busca:")
        df_found_processes = pd.DataFrame(st.session_state.mass_edit_found_processes)
        
        display_cols_search_results = [
            "Processo_Novo", "Status_Geral", "Observacao", "Previsao_Pichau", "Data_Embarque", 
            "ETA_Recinto", "Data_Registro", "Estimativa_Impostos_Total", "Nota_feita", "ID", "Status da Busca"
        ]
        
        display_col_names_map = {
            "Processo_Novo": "Processo", "Status_Geral": "Status Geral", "Observacao": "Observação",
            "Previsao_Pichau": "Previsão na Pichau", "Data_Embarque": "Data do Embarque",
            "ETA_Recinto": "ETA no Recinto", "Data_Registro": "Data de Registro", "ID": "ID do DB",
            "Estimativa_Impostos_Total": "Imp. Totais (R$)", "Nota_feita": "Nota feita",
            "Status da Busca": "Status da Busca"
        }
        
        # Filtra e renomeia as colunas para exibição
        df_display_search_results = df_found_processes[[col for col in display_cols_search_results if col in df_found_processes.columns]]
        df_display_search_results = df_display_search_results.rename(columns=display_col_names_map)

        st.dataframe(
            df_display_search_results, hide_index=True, use_container_width=True,
            column_config={
                "Processo": st.column_config.TextColumn("Processo", width="medium"),
                "Status Geral": st.column_config.TextColumn("Status Geral", width="small"),
                "Observação": st.column_config.TextColumn("Observação", width="medium"),
                "Previsão na Pichau": st.column_config.TextColumn("Previsão na Pichau", width="small"),
                "Data do Embarque": st.column_config.TextColumn("Data do Embarque", width="small"),
                "ETA no Recinto": st.column_config.TextColumn("ETA no Recinto", width="small"),
                "Data de Registro": st.column_config.TextColumn("Data de Registro", width="small"),
                # ALTERADO: Usar NumberColumn para formatação de moeda
                "Imp. Totais (R$)": st.column_config.NumberColumn(
                    "Imp. Totais (R$)", 
                    format="R$ %.2f", # Formato de moeda brasileiro
                    help="Estimativa de Impostos Totais em Reais"
                ),
                "Nota feita": st.column_config.TextColumn("Nota feita", width="small"),
                "ID do DB": st.column_config.TextColumn("ID do DB", width="small"),
                "Status da Busca": st.column_config.TextColumn("Status da Busca", width="small"),
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

            # FORM 2: Aplicação de Alterações
            # Usa a key dinâmica para garantir que o formulário e seus widgets sejam resetados
            with st.form(key=f"apply_changes_form_page_{st.session_state.mass_edit_apply_changes_form_key_counter}"):
                # Inicializa os valores dos campos de entrada do formulário AQUI, fora do if de submissão
                # Isso garante que os widgets sempre comecem com esses valores no rerun
                st.session_state.setdefault("mass_edit_new_status_value_form2", "")
                st.session_state.setdefault("mass_edit_new_modal_value_form2", "")
                st.session_state.setdefault("mass_edit_new_navio_value_form2", "")
                st.session_state.setdefault("mass_edit_new_observacao_value_form2", "")
                st.session_state.setdefault("mass_edit_new_previsao_pichau_value_form2", None)
                st.session_state.setdefault("mass_edit_new_data_embarque_value_form2", None)
                st.session_state.setdefault("mass_edit_new_eta_recinto_value_form2", None)
                st.session_state.setdefault("mass_edit_new_data_registro_value_form2", None)


                new_status_geral = st.selectbox(
                    "Novo Status Geral:", 
                    options=[""] + db_manager.STATUS_OPTIONS, 
                    key=f"mass_edit_new_status_value_form2_{st.session_state.mass_edit_apply_changes_form_key_counter}" # Key dinâmica
                )
                # Define como None se a opção vazia for selecionada
                if new_status_geral == "": new_status_geral = None

                # Campo para novo Modal
                new_modal = st.selectbox(
                    "Novo Modal:", 
                    options=[""] + db_manager.MODAL_OPTIONS, 
                    key=f"mass_edit_new_modal_value_form2_{st.session_state.mass_edit_apply_changes_form_key_counter}" # Key dinâmica
                )
                if new_modal == "": new_modal = None

                # Campo para novo Navio
                new_navio = st.text_input(
                    "Novo Navio (deixe vazio para não alterar):",
                    value=st.session_state.mass_edit_new_navio_value_form2, # Usa o valor do session_state
                    key=f"mass_edit_new_navio_value_form2_{st.session_state.mass_edit_apply_changes_form_key_counter}" # Key dinâmica
                )
                if new_navio == "": new_navio = None


                # Controlar se o campo de observação foi "tocado"
                # Usar um input de texto padrão e verificar seu valor
                new_observacao_input = st.text_area(
                    "Nova Observação (deixe vazio para não alterar):",
                    value=st.session_state.mass_edit_new_observacao_value_form2, # Usa o valor do session_state
                    key=f"mass_edit_new_observacao_value_form2_{st.session_state.mass_edit_apply_changes_form_key_counter}" # Key dinâmica
                )
                
                new_previsao_pichau_date = st.date_input(
                    "Nova Previsão na Pichau (deixe vazio para não alterar):", 
                    value=st.session_state.mass_edit_new_previsao_pichau_value_form2, # Usa o valor do session_state
                    key=f"mass_edit_new_previsao_pichau_value_form2_{st.session_state.mass_edit_apply_changes_form_key_counter}", # Key dinâmica
                    format="DD/MM/YYYY"
                )
                new_previsao_pichau = new_previsao_pichau_date.strftime("%Y-%m-%d") if new_previsao_pichau_date else None

                new_data_embarque_date = st.date_input(
                    "Nova Data do Embarque (deixe vazio para não alterar):", 
                    value=st.session_state.mass_edit_new_data_embarque_value_form2, # Usa o valor do session_state
                    key=f"mass_edit_new_data_embarque_value_form2_{st.session_state.mass_edit_apply_changes_form_key_counter}", # Key dinâmica
                    format="DD/MM/YYYY"
                )
                new_data_embarque = new_data_embarque_date.strftime("%Y-%m-%d") if new_data_embarque_date else None

                new_eta_recinto_date = st.date_input(
                    "Nova ETA no Recinto (deixe vazio para não alterar):", 
                    value=st.session_state.mass_edit_new_eta_recinto_value_form2, # Usa o valor do session_state
                    key=f"mass_edit_new_eta_recinto_value_form2_{st.session_state.mass_edit_apply_changes_form_key_counter}", # Key dinâmica
                    format="DD/MM/YYYY"
                )
                new_eta_recinto = new_eta_recinto_date.strftime("%Y-%m-%d") if new_eta_recinto_date else None

                new_data_registro_date = st.date_input(
                    "Nova Data de Registro (deixe vazio para não alterar):", 
                    value=st.session_state.mass_edit_new_data_registro_value_form2, # Usa o valor do session_state
                    key=f"mass_edit_new_data_registro_value_form2_{st.session_state.mass_edit_apply_changes_form_key_counter}", # Key dinâmica
                    format="DD/MM/YYYY"
                )
                new_data_registro = new_data_registro_date.strftime("%Y-%m-%d") if new_data_registro_date else None

                col_save, col_cancel = st.columns(2)

                with col_save:
                    if st.form_submit_button("Aplicar Alterações", disabled=not st.session_state.mass_edit_can_proceed):
                        if not processes_to_edit_ids:
                            _display_message_box("Nenhum processo válido selecionado para edição.", "warning")
                        else:
                            user_info = st.session_state.get('user_info', {'username': 'Desconhecido'})
                            username = user_info.get('username')

                            successful_updates_count = 0
                            for p_id in processes_to_edit_ids:
                                original_process_data_row = db_manager.obter_processo_por_id(p_id)
                                if original_process_data_row:
                                    original_process_data = dict(original_process_data_row)
                                    
                                    changes_to_apply = {}
                                    if new_status_geral is not None: changes_to_apply["Status_Geral"] = new_status_geral
                                    if new_modal is not None: changes_to_apply["Modal"] = new_modal 
                                    if new_navio is not None: changes_to_apply["Navio"] = new_navio 
                                    
                                    # Lógica para Observação:
                                    # Se o usuário digitou algo (mesmo que seja uma string vazia)
                                    # ou se o valor original não era None e o novo valor é vazio,
                                    # então aplique a mudança.
                                    if new_observacao_input != "" or original_process_data.get("Observacao") is not None:
                                        changes_to_apply["Observacao"] = new_observacao_input if new_observacao_input != "" else None
                                    
                                    if new_previsao_pichau is not None: changes_to_apply["Previsao_Pichau"] = new_previsao_pichau
                                    if new_data_embarque is not None: changes_to_apply["Data_Embarque"] = new_data_embarque
                                    if new_eta_recinto is not None: changes_to_apply["ETA_Recinto"] = new_eta_recinto
                                    if new_data_registro is not None: changes_to_apply["Data_Registro"] = new_data_registro

                                    if not changes_to_apply:
                                        logger.info(f"Nenhuma alteração detectada para o processo {original_process_data.get('Processo_Novo', 'N/A')} (ID: {p_id}).")
                                        continue

                                    if db_manager.atualizar_processo(p_id, changes_to_apply):
                                        successful_updates_count += 1
                                        for field_name, new_val in changes_to_apply.items():
                                            db_manager.inserir_historico_processo(p_id, field_name, original_process_data.get(field_name), new_val, username, db_type="Firestore")
                                    else:
                                        _display_message_box(f"Falha ao atualizar processo ID {p_id}.", "error")
                                else:
                                    _display_message_box(f"Processo ID {p_id} não encontrado para atualização.", "error")

                            if successful_updates_count > 0:
                                _display_message_box(f"{successful_updates_count} processos atualizados com sucesso!", "success")
                                # Limpa os estados após sucesso, para o formulário de edição em massa
                                st.session_state.mass_edit_process_names_input = ""
                                st.session_state.mass_edit_found_processes = []
                                st.session_state.mass_edit_can_proceed = False
                                # NOVO: Incrementa o contador para forçar o reset do text_area de busca E do formulário de edição
                                st.session_state.mass_edit_search_form_key_counter += 1
                                st.session_state.mass_edit_apply_changes_form_key_counter += 1 
                                # Redefinição dos valores do session_state (opcional, mas boa prática)
                                # As chaves dinâmicas já garantem que os widgets "resetem" visualmente para o default no próximo rerun.
                                st.session_state.mass_edit_new_status_value_form2 = ""
                                st.session_state.mass_edit_new_modal_value_form2 = "" 
                                st.session_state.mass_edit_new_navio_value_form2 = "" 
                                st.session_state.mass_edit_new_observacao_value_form2 = ""
                                st.session_state.mass_edit_new_previsao_pichau_value_form2 = None
                                st.session_state.mass_edit_new_data_embarque_value_form2 = None
                                st.session_state.mass_edit_new_eta_recinto_value_form2 = None
                                st.session_state.mass_edit_new_data_registro_value_form2 = None

                                # Recarrega a página de Follow-up se o callback for fornecido
                                if st.session_state.get('mass_edit_processes_reload_callback'):
                                    st.session_state.mass_edit_processes_reload_callback()
                                st.rerun() # Força uma recarga completa para refletir as alterações
                            else:
                                _display_message_box("Nenhum processo foi atualizado ou nenhuma alteração foi detectada para aplicar.", "warning")

                with col_cancel:
                    # Este é um form_submit_button para que a ação de "Voltar" também redefina o formulário
                    if st.form_submit_button("Voltar para Follow-up Importação"): 
                        # Limpa os estados e volta para a página principal
                        st.session_state.mass_edit_process_names_input = ""
                        st.session_state.mass_edit_found_processes = []
                        st.session_state.mass_edit_can_proceed = False
                        # NOVO: Incrementa o contador para forçar o reset do text_area de busca E do formulário de edição
                        st.session_state.mass_edit_search_form_key_counter += 1
                        st.session_state.mass_edit_apply_changes_form_key_counter += 1
                        # Limpa os campos visíveis também para uma próxima visita
                        st.session_state.mass_edit_new_status_value_form2 = ""
                        st.session_state.mass_edit_new_modal_value_form2 = "" 
                        st.session_state.mass_edit_new_navio_value_form2 = "" 
                        st.session_state.mass_edit_new_observacao_value_form2 = ""
                        st.session_state.mass_edit_new_previsao_pichau_value_form2 = None
                        st.session_state.mass_edit_new_data_embarque_value_form2 = None
                        st.session_state.mass_edit_new_eta_recinto_value_form2 = None
                        st.session_state.mass_edit_new_data_registro_value_form2 = None

                        st.session_state.current_page = "Follow-up Importação"
                        if st.session_state.get('mass_edit_processes_reload_callback'):
                            st.session_state.mass_edit_processes_reload_callback()
                        st.rerun()

    else: # Quando não há processos encontrados ou a busca ainda não foi realizada
        # Este botão NÃO é um form_submit_button, mas um st.button comum
        if st.button("Voltar para Follow-up Importação", key="back_button_no_results_page_outside_form"):
            st.session_state.mass_edit_process_names_input = ""
            st.session_state.mass_edit_found_processes = []
            st.session_state.mass_edit_can_proceed = False
            # NOVO: Incrementa o contador para forçar o reset do text_area de busca E do formulário de edição
            st.session_state.mass_edit_search_form_key_counter += 1
            st.session_state.mass_edit_apply_changes_form_key_counter += 1
            st.session_state.current_page = "Follow-up Importação"
            if st.session_state.get('mass_edit_processes_reload_callback'):
                st.session_state.mass_edit_processes_reload_callback()
            st.rerun()
