import streamlit as st
import pandas as pd
from typing import List, Optional
import logging
from datetime import datetime

# Importar db_utils para interagir com o banco de dados
import app_logic.db_utils as db_utils
import app_logic.followup_db_manager as followup_db_manager # Importa para buscar processos existentes
from app_logic.utils import set_background_image # Para o background

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

def show_update_process_data_page():
    """
    Exibe a página para atualização em massa de dados de processo (Navio, Data ETD, ETA Recinto).
    """
    # Define a imagem de fundo para a página
    set_background_image(r"assets/logo_navio_atracado.png", opacity=0.5)

    st.title("Atualização de Dados de Processo")
    st.markdown("Use esta tela para atualizar o nome do navio, a data de embarque (ETD) e/ou a data de ETA no recinto para um ou múltiplos processos.")
    st.info("Para processos múltiplos, insira as referências separadas por vírgula (ex: REF-001, PROCESSO-2023-002).")

    # Inicia um formulário Streamlit para agrupar os inputs e o botão de submit
    with st.form("update_process_form", clear_on_submit=True):
        # Campo para Referência(s) do Processo
        # Permite múltiplas entradas separadas por vírgulas
        processo_novo_input = st.text_area(
            "Referência(s) do Processo (Processo_Novo)",
            help="Insira uma ou mais referências de processo, separadas por vírgulas.",
            placeholder="Ex: PROCESSO-2023-001, PROCESSO-2023-002",
            key="processo_novo_input_key" # Adiciona uma chave para o widget
        )

        st.markdown("---")
        st.subheader("Dados a serem Atualizados (Preencha apenas o que deseja mudar):")

        # Campo para Nome do Navio (string)
        navio = st.text_input("Nome do Navio (Navio)", placeholder="Ex: Evergreen Marine", key="navio_input_key")

        # Campo para Data de ETD (Data de Embarque)
        # O valor inicial é None para que o campo não venha preenchido por padrão
        data_embarque_str_input = st.date_input(
            "Data de ETD (Data_Embarque)",
            value=None, # Inicia vazio
            format="DD/MM/YYYY", # <-- FORMATO DA DATA ALTERADO
            help="Selecione a data de embarque (ETD). Deixe em branco para não alterar.",
            key="data_embarque_input_key" # Adiciona uma chave para o widget
        )
        # Converte o objeto datetime.date para uma string no formato 'YYYY-MM-DD' para o banco de dados
        data_embarque_formatted_db = data_embarque_str_input.strftime('%Y-%m-%d') if data_embarque_str_input else None

        # Campo para Data de ETA (ETA Recinto)
        # O valor inicial é None para que o campo não venha preenchido por padrão
        eta_recinto_str_input = st.date_input(
            "Data de ETA (ETA_Recinto)",
            value=None, # Inicia vazio
            format="DD/MM/YYYY", # <-- FORMATO DA DATA ALTERADO
            help="Selecione a data de ETA no recinto. Deixe em branco para não alterar.",
            key="eta_recinto_input_key" # Adiciona uma chave para o widget
        )
        # Converte o objeto datetime.date para uma string no formato 'YYYY-MM-DD' se uma data foi selecionada
        eta_recinto_formatted_db = eta_recinto_str_input.strftime('%Y-%m-%d') if eta_recinto_str_input else None

        # Botão para submeter o formulário
        submit_button = st.form_submit_button("Atualizar Processo(s)")

        if submit_button:
            # Processa a string de entrada das referências de processo
            # Divide por vírgula e remove espaços em branco de cada referência
            processo_novos_list = [ref.strip() for ref in processo_novo_input.split(',') if ref.strip()]

            # Validações
            if not processo_novos_list:
                st.error("Por favor, insira ao menos uma Referência do Processo.")
                return

            # Verifica se pelo menos um campo de atualização foi preenchido
            if not navio and not data_embarque_formatted_db and not eta_recinto_formatted_db:
                st.warning("Nenhum campo de atualização preenchido. Por favor, preencha o Nome do Navio, Data de ETD ou Data de ETA.")
                return

            # Chama a função de atualização no db_utils e recebe a mensagem de erro
            success, error_message = db_utils.update_process_shipping_info(
                processo_novos_list,
                navio if navio else None,
                data_embarque_formatted_db,
                eta_recinto_formatted_db
            )

            # Exibe mensagem de sucesso ou erro
            if success:
                st.success("Dados dos processos atualizados com sucesso!")
            else:
                if error_message:
                    st.error(f"Ocorreu um erro ao atualizar os dados dos processos: {error_message}")
                else:
                    st.error("Ocorreu um erro inesperado ao atualizar os dados dos processos. Verifique os logs para mais detalhes.")
                st.warning("Certifique-se de que as Referências do Processo estão corretas e o Firebase está conectado.")


   

    
    st.markdown("---")
    st.markdown("### Dicas:")
    st.markdown("- Se deixar um campo de data em branco, ele não será alterado no banco de dados.")
    st.markdown("- O campo de Nome do Navio é opcional. Se não for preenchido, o nome atual do navio não será alterado.")
    st.markdown("- Para múltiplos processos, separe as referências por vírgula.")
    st.markdown("---")
    