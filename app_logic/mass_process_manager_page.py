import streamlit as st
import pandas as pd
import os
import io
import base64
from datetime import datetime, date
import re
from typing import Any, Dict, List, Optional, Union

import followup_db_manager as db_manager # Importa o módulo de gerenciamento de banco de dados

# Configuração do logger
import logging
logger = logging.getLogger(__name__)

# --- Funções Auxiliares (Copiadas e Adaptadas de process_form_page.py e followup_importacao_page.py) ---

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

def _generate_process_excel_template():
    """Gera um arquivo Excel padrão para inserção de dados gerais do processo."""
    template_columns = [
        "Process Reference", "Supplier", "Items", "PI / Invoice", "QTY", "Invoice Value USD",
        "PAY?", "OC", "Purchase Date", "DI Estimated R$", "Freight USD Est.",
        "Shipping Date", "AGENTE", "Status", "ETA Pichau", "Status para e-mail",
        "AIR or SEA", "Containers QTY", "Origin", "Dest.", "Terms", "Buyer", "Modal",
        "Consolidado?", "Quantos processos - LCL"
    ]
    example_row = {
        "Process Reference": "PR-2024-EXEMPLO",
        "Supplier": "Exemplo Fornecedor Ltda.",
        "Items": "Eletrônicos;Componentes",
        "PI / Invoice": "INV-2024-001",
        "QTY": 100,
        "Invoice Value USD": 15000.00,
        "PAY?": "Não",
        "OC": "OC-XYZ-001",
        "Purchase Date": "2024-01-10",
        "DI Estimated R$": 5000.00,
        "Freight USD Est.": 300.00,
        "Shipping Date": "2024-02-15",
        "AGENTE": "Agente ABC",
        "Status": "Desembaraço Aduaneiro",
        "ETA Pichau": "2024-03-05",
        "Status para e-mail": "Em Andamento",
        "AIR or SEA": "AIR",
        "Containers QTY": 0,
        "Origin": "Shenzhen",
        "Dest.": "São Paulo",
        "Terms": "FOB",
        "Buyer": "João Silva",
        "Modal": "Aéreo",
        "Consolidado?": "Não",
        "Quantos processos - LCL": 0
    }
    df_template = pd.DataFrame([example_row], columns=template_columns)

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df_template.to_excel(writer, index=False, sheet_name='Template Dados Gerais')
    writer.close()
    output.seek(0)
    return output

def _preprocess_dataframe_for_db(df: pd.DataFrame) -> Optional[List[Dict[str, Any]]]:
    """
    Realiza o pré-processamento e padronização dos dados do DataFrame
    para o formato esperado pelo banco de dados.
    Esta função foi adaptada de `followup_importacao_page.py`.
    """
    df_processed = df.copy()

    # Mapeamento de colunas do Excel para as colunas do DB
    column_mapping_to_db = {
        "Process Reference": "Processo_Novo", "Supplier": "Fornecedor", "Items": "Tipos_de_item",
        "PI / Invoice": "N_Invoice", "QTY": "Quantidade", "Invoice Value USD": "Valor_USD",
        "PAY?": "Pago", "OC": "N_Ordem_Compra", "Purchase Date": "Data_Compra",
        "DI Estimated R$": "Estimativa_Impostos_BR", "Freight USD Est.": "Estimativa_Frete_USD",
        "Shipping Date": "Data_Embarque", "AGENTE": "Agente_de_Carga_Novo",
        "Status": "Observacao", # O campo "Status" do Excel vai para Observacao no DB
        "ETA Pichau": "Previsao_Pichau",
        "Status para e-mail": "Status_Geral", # O campo "Status para e-mail" do Excel vai para Status_Geral no DB
        "AIR or SEA": "Modal_Air_Sea_Temp", # Campo temporário para lógica de modal
        "Containers QTY": "Quantidade_Containers", "Origin": "Origem",
        "Dest.": "Destino", "Terms": "INCOTERM", "Buyer": "Comprador",
        "Modal": "Modal", # Pode estar presente, mas "AIR or SEA" tem prioridade
        "Consolidado?": "Consolidado",
        "Quantos processos - LCL": "LCL_Processos_Quantidade",
    }
    df_processed = df_processed.rename(columns=column_mapping_to_db, errors='ignore')

    if "Processo_Novo" not in df_processed.columns:
        _display_message_box("Coluna 'Processo_Novo' (ou 'Process Reference') não encontrada no arquivo importado após renomeação. Verifique o cabeçalho.", "error")
        return None

    df_processed["Processo_Novo"] = df_processed["Processo_Novo"].fillna("").astype(str).str.strip()
    df_processed = df_processed[df_processed["Processo_Novo"] != ""].copy()

    if df_processed.empty:
        _display_message_box("Nenhum processo válido encontrado no arquivo após o pré-processamento (coluna 'Processo_Novo' está vazia ou ausente).", "warning")
        return None

    records = df_processed.to_dict(orient='records')

    final_processed_records = []
    for record in records:
        cleaned_record = {}
        for key, value in record.items():
            if key in ["Quantidade", "DI_ID_Vinculada", "Quantidade_Containers", "LCL_Processos_Quantidade"]:
                numeric_value = pd.to_numeric(value, errors='coerce')
                # CORREÇÃO: Verifica se é NaN antes de converter para int
                cleaned_record[key] = int(numeric_value) if pd.notna(numeric_value) else 0
            elif key in ["Valor_USD", "Estimativa_Impostos_BR", "Estimativa_Frete_USD",
                          "Estimativa_Impostos_Total", "Estimativa_Dolar_BRL", "Estimativa_Seguro_BRL",
                          "Estimativa_II_BR", "Estimativa_IPI_BR", "Estimativa_PIS_BR",
                          "Estimativa_COFINS_BR", "Estimativa_ICMS_BR"]:
                if isinstance(value, str):
                    value = value.replace('.', '').replace(',', '.') # Lida com formato de moeda BR
                numeric_value = pd.to_numeric(value, errors='coerce')
                # CORREÇÃO: Verifica se é NaN antes de converter para float
                cleaned_record[key] = float(numeric_value) if pd.notna(numeric_value) else 0.0
            elif key in ["Data_Compra", "Data_Embarque", "Previsao_Pichau", "ETA_Recinto", "Data_Registro"]:
                try:
                    # Tenta converter para datetime, suporta vários formatos, e depois para stringYYYY-MM-DD
                    date_obj = pd.to_datetime(value, errors='coerce', dayfirst=True)
                    cleaned_record[key] = date_obj.strftime('%Y-%m-%d') if pd.notna(date_obj) else None
                except Exception:
                    cleaned_record[key] = None
            elif key in ["Pago", "Documentos_Revisados", "Conhecimento_Embarque",
                          "Descricao_Feita", "Descricao_Enviada", "Nota_feita", "Conferido", "Consolidado"]:
                str_value = str(value).strip().lower()
                if str_value in ["sim", "s", "true", "1"]:
                    cleaned_record[key] = "Sim"
                elif str_value in ["nao", "não", "n", "false", "0"]:
                    cleaned_record[key] = "Não"
                else:
                    cleaned_record[key] = None
            elif key == "Modal_Air_Sea_Temp": # Lógica para o campo temporário "AIR or SEA"
                str_value = str(value).strip().lower()
                if str_value == "air":
                    cleaned_record["Modal"] = "Aéreo"
                elif str_value == "sea":
                    cleaned_record["Modal"] = "Maritimo"
                else:
                    cleaned_record["Modal"] = None # Ou um valor padrão se preferir
            else:
                if pd.isna(value) or str(value).strip().lower() == 'nan' or str(value).strip() == '':
                    cleaned_record[key] = None
                else:
                    cleaned_record[key] = str(value)
        final_processed_records.append(cleaned_record)
    return final_processed_records

def _import_processes_from_excel_action(uploaded_file: Any) -> bool:
    """Importa processos de um arquivo Excel/CSV e os salva no banco de dados."""
    if uploaded_file is None:
        _display_message_box("Nenhum arquivo selecionado para importação.", "warning")
        return False

    file_extension = os.path.splitext(uploaded_file.name)[1]
    df = None

    try:
        if file_extension.lower() == '.csv':
            try: df = pd.read_csv(uploaded_file, encoding='utf-8')
            except UnicodeDecodeError: df = pd.read_csv(uploaded_file, encoding='latin-1')
            except Exception: df = pd.read_csv(uploaded_file, sep=';')
        elif file_extension.lower() in ('.xlsx', '.xls'):
            df = pd.read_excel(uploaded_file)
        else:
            _display_message_box("Formato de arquivo não suportado. Por favor, use .csv, .xls ou .xlsx.", "error")
            return False

        if df.empty:
            _display_message_box("O arquivo importado está vazio ou não contém dados.", "warning")
            return False

        processed_records = _preprocess_dataframe_for_db(df)

        if processed_records is None or not processed_records:
            _display_message_box("Falha no pré-processamento dos dados do arquivo ou nenhum dado válido restante após o processamento.", "error")
            return False

        import_success_count = 0
        total_rows = len(processed_records)

        st.info(f"Iniciando importação/atualização de {total_rows} processos...")
        progress_bar = st.progress(0)

        user_info = st.session_state.get('user_info', {'username': 'Desconhecido'})
        current_username = user_info.get('username', 'Desconhecido')

        for index, row_dict in enumerate(processed_records):
            process_name = row_dict.get("Processo_Novo")
            if not process_name:
                logger.warning(f"Linha {index+2} ignorada: 'Processo_Novo' está vazio ou inválido.")
                continue

            # Adiciona/Atualiza informações de auditoria
            row_dict['Ultima_Alteracao_Por'] = current_username
            row_dict['Ultima_Alteracao_Em'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # Garante que 'Status_Arquivado' seja 'Não Arquivado' para novos processos
            if db_manager._USE_FIRESTORE_AS_PRIMARY:
                # Firestore usa Processo_Novo como ID, então tentar obter pelo ID diretamente
                existing_process = db_manager.obter_processo_by_processo_novo(process_name)
            else: # SQLite
                existing_process = db_manager.obter_processo_by_processo_novo(process_name) # Assuming this also works for SQLite by name

            if not existing_process:
                row_dict['Status_Arquivado'] = 'Não Arquivado'
            else:
                # Se existe, mantém o status de arquivamento existente
                row_dict['Status_Arquivado'] = existing_process.get('Status_Arquivado', 'Não Arquivado')


            if db_manager.upsert_processo(row_dict):
                import_success_count += 1
                logger.info(f"Processo '{process_name}' upserted (inserido/atualizado) via importação em massa.")
            else:
                st.error(f"Falha ao fazer upsert do processo '{process_name}' na linha {index+2}. Verifique os dados.")

            progress_bar.progress((index + 1) / total_rows)

        progress_bar.empty()

        if import_success_count == total_rows:
            _display_message_box("Dados do arquivo local importados/atualizados com sucesso!", "success")
            return True
        elif import_success_count > 0:
            _display_message_box(f"Importação/atualização concluída com {import_success_count} de {total_rows} processos bem-sucedidos. Verifique os erros acima para os processos que falharam.", "warning")
            return True
        else:
            _display_message_box("Falha total ao importar/atualizar dados do arquivo local para o banco de dados.", "error")
            return False

    except Exception as e:
        _display_message_box(f"Erro ao processar o arquivo local: {e}", "error")
        logger.exception("Erro durante a importação do arquivo local.")
        return False

def _export_processes_to_excel(df_data: pd.DataFrame):
    """Exporta os dados do DataFrame para um arquivo Excel em memória."""
    output = io.BytesIO()
    writer = pd.ExcelWriter(output, engine='xlsxwriter')

    column_display_names = {
        "Processo_Novo": "Process Reference", "Fornecedor": "Supplier", "Tipos_de_item": "Items",
        "N_Invoice": "PI / Invoice", "Quantidade": "QTY", "Valor_USD": "Invoice Value USD",
        "Pago": "PAY?", "N_Ordem_Compra": "OC", "Data_Compra": "Purchase Date",
        "Estimativa_Impostos_BR": "DI Estimated R$", "Estimativa_Frete_USD": "Freight USD Est.",
        "Shipping Date": "Shipping Date", "Agente_de_Carga_Novo": "AGENTE",
        "Observacao": "Status", # Observacao do DB vira "Status" no Excel
        "Previsao_Pichau": "ETA Pichau", "Status_Geral": "Status para e-mail",
        "Modal": "Modal", # Se Modal já é "Aéreo" ou "Maritimo", 'AIR or SEA' será derivado
        "Quantidade_Containers": "Containers QTY", "Origem": "Origin",
        "Destino": "Dest.", "INCOTERM": "Terms", "Comprador": "Buyer",
        "Consolidado": "Consolidado?",
        "LCL_Processos_Quantidade": "Quantos processos - LCL",
        # Incluir os campos calculados para exportação, mas podem ser removidos na importação
        "Estimativa_Impostos_Total": "Imp. Totais (R$)",
        "Estimativa_Dolar_BRL": "Câmbio Estimado (R$)",
        "Estimativa_Seguro_BRL": "Estimativa Seguro (R$)",
        "Estimativa_II_BR": "Estimativa II (R$)",
        "Estimativa_IPI_BR": "Estimativa IPI (R$)",
        "Estimativa_PIS_BR": "Estimativa PIS (R$)",
        "Estimativa_COFINS_BR": "Estimativa COFINS (R$)",
        "Estimativa_ICMS_BR": "Estimativa ICMS (R$)",
        "Status_Arquivado": "Status Arquivado", # Adicionado para exportação
    }

    # Criar uma cópia do DataFrame para não modificar o original
    df_export = df_data.copy()

    # Adicionar a coluna "AIR or SEA" baseada na coluna "Modal"
    df_export['AIR or SEA'] = df_export['Modal'].apply(
        lambda x: 'AIR' if x == 'Aéreo' else ('SEA' if x == 'Maritimo' else None)
    )
    # Reordenar colunas para que "AIR or SEA" apareça antes de "Modal" se ambos forem exportados, ou apenas um
    # E para que Process Reference esteja no início
    cols_order = [
        "Process Reference", "Supplier", "Items", "PI / Invoice", "QTY", "Invoice Value USD",
        "PAY?", "OC", "Purchase Date", "DI Estimated R$", "Freight USD Est.",
        "Shipping Date", "AGENTE", "Status", "ETA Pichau", "Status para e-mail",
        "AIR or SEA", "Containers QTY", "Origin", "Dest.", "Terms", "Buyer", "Modal",
        "Consolidado?", "Quantos processos - LCL",
        "Imp. Totais (R$)", "Câmbio Estimado (R$)", "Estimativa Seguro (R$)",
        "Estimativa II (R$)", "Estimativa IPI (R$)", "Estimativa PIS (R$)",
        "Estimativa COFINS (R$)", "Estimativa ICMS (R$)", "Status Arquivado"
    ]

    # Renomear as colunas existentes para os nomes de exibição/template
    df_export = df_export.rename(columns=column_display_names, errors='ignore')

    # Reordenar o DataFrame final
    final_cols_to_export = [col for col in cols_order if col in df_export.columns]
    df_export = df_export[final_cols_to_export]

    # Formatação de datas
    date_cols = ["Purchase Date", "Shipping Date", "ETA Pichau"]
    for col in date_cols:
        if col in df_export.columns:
            df_export[col] = df_export[col].apply(lambda x: pd.to_datetime(x).strftime("%Y-%m-%d") if pd.notna(x) else None)

    writer = pd.ExcelWriter(output, engine='xlsxwriter')
    df_export.to_excel(writer, index=False, sheet_name='Processos em Massa')
    writer.close()
    output.seek(0)
    return output


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

def show_mass_process_manager_page(reload_processes_callback: Optional[callable] = None):
    """
    Exibe a página para gerenciamento em massa de processos (importação/exclusão).
    """
    background_image_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'assets', 'logo_navio_atracado.png')
    set_background_image(background_image_path)

    st.subheader("Gerenciar Processos em Massa")

    # Inicializa os estados da sessão
    st.session_state.setdefault('mass_import_last_processed_file_hash', None)
    st.session_state.setdefault('mass_manage_processes_data', pd.DataFrame())
    st.session_state.setdefault('selected_processes_for_action', []) # IDs dos processos selecionados

    if reload_processes_callback:
        st.session_state.mass_process_manager_reload_callback = reload_processes_callback

    # --- Seção de Importação em Massa ---
    st.markdown("---")
    st.markdown("#### Importar Processos (Excel/CSV)")
    st.info("Utilize o template para garantir o formato correto. Os processos serão inseridos ou atualizados com base na 'Process Reference'.")

    col_download_template, col_upload_file = st.columns([0.3, 0.7])
    with col_download_template:
        excel_template_data = _generate_process_excel_template()
        st.download_button(
            label="Baixar Template de Importação",
            data=excel_template_data,
            file_name="template_importacao_processos.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="download_mass_process_template"
        )

    with col_upload_file:
        uploaded_file = st.file_uploader("Upload de Arquivo (Excel/CSV)", type=["csv", "xls", "xlsx"], key="mass_process_uploader")

        # Verifica se um novo arquivo foi enviado para evitar reprocessamento desnecessário
        current_file_hash = None
        if uploaded_file is not None:
            # CORREÇÃO DO ERRO: Removido .hash, usando apenas nome e tamanho para o hash do arquivo
            current_file_hash = uploaded_file.name + str(uploaded_file.size)

        if uploaded_file is not None and current_file_hash != st.session_state.mass_import_last_processed_file_hash:
            if _import_processes_from_excel_action(uploaded_file):
                st.session_state.mass_import_last_processed_file_hash = current_file_hash
                # Força o recarregamento da lista para refletir as importações
                if hasattr(st.session_state, 'mass_process_manager_reload_callback'):
                    st.session_state.mass_process_manager_reload_callback()
                st.rerun() # Necessário para atualizar a tabela de gerenciamento
            else:
                st.session_state.mass_import_last_processed_file_hash = None # Reseta o hash em caso de falha

    # --- Seção de Gerenciamento de Processos Existentes ---
    st.markdown("---")
    st.markdown("#### Gerenciar Processos Existentes")

    # Recarrega a lista de processos para o data_editor
    # Isso deve ser feito sempre que a página é carregada ou após uma ação de importação/arquivamento
    if st.session_state.get('firebase_ready', False):
        try:
            processes_raw = db_manager.obter_processos_filtrados('Todos', {}) # Obtém todos os processos
            df_all_processes = pd.DataFrame([dict(row) for row in processes_raw])
            # Garante que as colunas essenciais existam
            df_all_processes['Status_Arquivado'] = df_all_processes.get('Status_Arquivado', pd.Series('Não Arquivado', index=df_all_processes.index)).fillna('Não Arquivado')
            df_all_processes['Processo_Novo'] = df_all_processes.get('Processo_Novo', pd.Series('UNKNOWN', index=df_all_processes.index))
            # Adiciona o ID para referência interna
            df_all_processes['ID do DB'] = df_all_processes.get('id', pd.Series(range(len(df_all_processes)), index=df_all_processes.index))
            st.session_state.mass_manage_processes_data = df_all_processes
        except Exception as e:
            st.error(f"Erro ao carregar processos do banco de dados: {e}")
            logger.exception("Erro ao carregar processos para gerenciamento em massa.")
            st.session_state.mass_manage_processes_data = pd.DataFrame()
    else:
        st.warning("Conexão com Firestore não estabelecida. Não é possível gerenciar processos em massa.")
        st.session_state.mass_manage_processes_data = pd.DataFrame()

    if not st.session_state.mass_manage_processes_data.empty:
        df_display = st.session_state.mass_manage_processes_data.copy()
        df_display['Selecionar'] = False # Adiciona coluna de seleção

        # Formatação de colunas para exibição
        df_display['Data_Embarque_Display'] = df_display['Data_Embarque'].apply(_format_date_display)
        df_display['ETA_Recinto_Display'] = df_display['ETA_Recinto'].apply(_format_date_display)
        df_display['Previsao_Pichau_Display'] = df_display['Previsao_Pichau'].apply(_format_date_display)
        df_display['Valor_USD_Display'] = df_display['Valor_USD'].apply(_format_usd_display)

        # Colunas a serem exibidas no data_editor
        display_columns = [
            'Selecionar', 'Processo_Novo', 'Fornecedor', 'Status_Geral', 'Modal',
            'Data_Embarque_Display', 'ETA_Recinto_Display', 'Previsao_Pichau_Display',
            'Valor_USD_Display', 'Status_Arquivado', 'ID do DB'
        ]
        # Renomear para cabeçalhos amigáveis
        df_display = df_display.rename(columns={
            'Processo_Novo': 'Processo',
            'Status_Geral': 'Status Geral',
            'Data_Embarque_Display': 'Data Embarque',
            'ETA_Recinto_Display': 'ETA Recinto',
            'Previsao_Pichau_Display': 'Previsão Pichau',
            'Valor_USD_Display': 'Valor (USD)',
            'Status_Arquivado': 'Arquivado'
        })

        # Filtra as colunas para garantir que apenas as presentes sejam usadas
        final_display_columns = [col for col in display_columns if col in df_display.columns]

        edited_df = st.data_editor(
            df_display[final_display_columns],
            column_config={
                "Selecionar": st.column_config.CheckboxColumn("Selecionar", default=False),
                "Processo": st.column_config.TextColumn("Processo", width="medium"),
                "Fornecedor": st.column_config.TextColumn("Fornecedor", width="medium"),
                "Status Geral": st.column_config.TextColumn("Status Geral", width="small"),
                "Modal": st.column_config.TextColumn("Modal", width="small"),
                "Data Embarque": st.column_config.TextColumn("Data Embarque", width="small"),
                "ETA Recinto": st.column_config.TextColumn("ETA Recinto", width="small"),
                "Previsão Pichau": st.column_config.TextColumn("Previsão Pichau", width="small"),
                "Valor (USD)": st.column_config.TextColumn("Valor (USD)", width="small"),
                "Arquivado": st.column_config.TextColumn("Arquivado", width="small"),
                "ID do DB": st.column_config.TextColumn("ID do DB", width="small", disabled=True), # Exibe o ID mas desabilita edição
            },
            hide_index=True,
            use_container_width=True,
            num_rows="dynamic", # Permite adicionar/deletar linhas diretamente no editor (não usaremos para adicionar aqui)
            key="mass_process_data_editor"
        )

        st.session_state.selected_processes_for_action = [
            edited_df.loc[idx, 'ID do DB'] for idx, selected in edited_df['Selecionar'].items() if selected
        ]

        if st.session_state.selected_processes_for_action:
            st.markdown("---")
            st.markdown("#### Ações em Massa")
            col_archive, col_unarchive, col_delete_permanent = st.columns(3) # Adicionado mais uma coluna

            with col_archive:
                if st.button(f"Arquivar {len(st.session_state.selected_processes_for_action)} Processos Selecionados", key="archive_selected_processes_btn"):
                    for process_id in st.session_state.selected_processes_for_action:
                        if db_manager.arquivar_processo(process_id):
                            st.success(f"Processo ID {process_id} arquivado.")
                        else:
                            st.error(f"Falha ao arquivar processo ID {process_id}.")
                    st.session_state.selected_processes_for_action = [] # Limpa a seleção
                    if hasattr(st.session_state, 'mass_process_manager_reload_callback'):
                        st.session_state.mass_process_manager_reload_callback()
                    st.rerun()

            with col_unarchive:
                if st.button(f"Desarquivar {len(st.session_state.selected_processes_for_action)} Processos Selecionados", key="unarchive_selected_processes_btn"):
                    for process_id in st.session_state.selected_processes_for_action:
                        if db_manager.desarquivar_processo(process_id):
                            st.success(f"Processo ID {process_id} desarquivado.")
                        else:
                            st.error(f"Falha ao desarquivar processo ID {process_id}.")
                    st.session_state.selected_processes_for_action = [] # Limpa a seleção
                    if hasattr(st.session_state, 'mass_process_manager_reload_callback'):
                        st.session_state.mass_process_manager_reload_callback()
                    st.rerun()

            with col_delete_permanent:
                if st.button(f"Excluir {len(st.session_state.selected_processes_for_action)} Processos PERMANENTEMENTE", key="delete_selected_processes_permanent_btn"):
                    # Adicionar uma confirmação extra, pois esta é uma ação destrutiva
                    confirm_permanent_delete = st.checkbox("Confirmar exclusão PERMANENTE", key="confirm_perm_delete_checkbox")
                    if confirm_permanent_delete:
                        for process_id in st.session_state.selected_processes_for_action:
                            if db_manager.deletar_processo(process_id): # Usar a função de exclusão real
                                st.success(f"Processo ID {process_id} excluído PERMANENTEMENTE.")
                            else:
                                st.error(f"Falha ao excluir processo ID {process_id}.")
                        st.session_state.selected_processes_for_action = [] # Limpa a seleção
                        # Limpar cache do db_manager para garantir que a lista seja recarregada do DB
                        db_manager.obter_processos_filtrados.clear()
                        db_manager.obter_todos_processos.clear()
                        if hasattr(st.session_state, 'mass_process_manager_reload_callback'):
                            st.session_state.mass_process_manager_reload_callback()
                        st.rerun()
                    else:
                        st.warning("Marque a caixa de confirmação para excluir processos permanentemente.")

        else:
            st.info("Selecione processos na tabela acima para realizar ações em massa (arquivar/desarquivar/excluir).")
    else:
        st.info("Nenhum processo encontrado no banco de dados para gerenciar.")

    st.markdown("---")
    if st.button("Voltar para Follow-up Importação"):
        st.session_state.current_page = "Follow-up Importação"
        if hasattr(st.session_state, 'mass_process_manager_reload_callback'):
            st.session_state.mass_process_manager_reload_callback()
        st.rerun()

