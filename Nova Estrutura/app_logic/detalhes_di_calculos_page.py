import streamlit as st
import pandas as pd
from datetime import datetime
import logging

# Importar funções do módulo de utilitários de banco de dados
from db_utils import (
    get_declaracao_by_id,
    get_declaracao_by_referencia, # NOVO: Importa a função para buscar por referência
    get_db_path # Para verificar o caminho do DB, se necessário
)

# Importar a página de cálculo Portonave
from app_logic import calculo_portonave_page

logger = logging.getLogger(__name__)

# --- Funções Auxiliares de Formatação ---
def _format_di_number(di_number):
    """Formata o número da DI para o padrão **/*******-*."""
    if di_number and isinstance(di_number, str) and len(di_number) == 10:
        return f"{di_number[0:2]}/{di_number[2:9]}-{di_number[9]}"
    return di_number

def _format_currency(value):
    """Formata um valor numérico para o formato de moeda R$ X.XXX,XX."""
    try:
        val = float(value)
        return f"R$ {val:,.2f}".replace('.', '#').replace(',', '.').replace('#', ',')
    except (ValueError, TypeError):
        return "R$ 0,00"

def _format_date(date_str):
    """Formata uma string de data AAAA-MM-DD para DD/MM/AAAA."""
    if date_str:
        try:
            return datetime.strptime(date_str, "%Y-%m-%d").strftime("%d/%m/%Y")
        except ValueError:
            return date_str # Retorna original se formato for diferente
    return "N/A"

# --- Funções de Ação ---
def load_di_details(input_value):
    """
    Carrega os detalhes de uma DI do banco de dados, aceitando ID ou Referência.
    """
    st.session_state.detalhes_di_data = None # Limpa dados anteriores

    if not input_value:
        st.warning("Por favor, insira um ID ou Referência da DI para carregar.")
        return

    di_data_raw = None
    try:
        # Tenta carregar por ID (se for numérico)
        declaracao_id = int(input_value)
        di_data_raw = get_declaracao_by_id(declaracao_id)
        if di_data_raw:
            st.session_state.detalhes_di_data = dict(di_data_raw)
            st.success(f"DI {_format_di_number(st.session_state.detalhes_di_data.get('numero_di', ''))} carregada por ID com sucesso!")
            logging.info(f"Detalhes da DI {declaracao_id} carregados por ID.")
            return

    except ValueError:
        # Se não for um ID numérico, tenta carregar por Referência
        logging.info(f"Valor '{input_value}' não é um ID numérico, tentando buscar por Referência.")
        di_data_raw = get_declaracao_by_referencia(str(input_value).strip())
        if di_data_raw:
            st.session_state.detalhes_di_data = dict(di_data_raw)
            st.success(f"DI {_format_di_number(st.session_state.detalhes_di_data.get('numero_di', ''))} carregada por Referência com sucesso!")
            logging.info(f"Detalhes da DI '{input_value}' carregados por Referência.")
            return

    # Se chegou aqui, não encontrou por ID nem por Referência
    st.error(f"Nenhum dado encontrado para a DI: '{input_value}'. Verifique o ID ou a Referência.")
    logging.warning(f"Tentativa de carregar DI '{input_value}' falhou: não encontrada por ID ou Referência.")


def navigate_to_portonave_calc():
    """
    Navega para a tela de cálculo da Portonave, passando o ID da DI carregada.
    """
    if 'detalhes_di_data' in st.session_state and st.session_state.detalhes_di_data:
        st.session_state.current_page = "Cálculo Portonave"
        # Armazena o ID da DI selecionada para que a tela de cálculo possa carregá-la
        st.session_state.portonave_selected_di_id = st.session_state.detalhes_di_data['id']
        st.rerun()
    else:
        st.warning("Por favor, carregue uma DI antes de ir para o cálculo Portonave.")

# --- Tela Principal do Streamlit para Detalhes DI e Cálculos ---
def show_page():
    st.subheader("Pagamentos") # ALTERADO: Nome da tela para "Pagamentos"

    # Inicializa o estado da sessão para esta página
    if 'detalhes_di_data' not in st.session_state:
        st.session_state.detalhes_di_data = None
    if 'detalhes_di_input_value' not in st.session_state: # Alterado para 'input_value'
        st.session_state.detalhes_di_input_value = ""

    # Seção para carregar DI
    st.markdown("---")
    st.markdown("#### Carregar Declaração de Importação")
    
    # Usar st.columns para alinhar o input e os botões na mesma linha
    # Ajustar as proporções para que o input seja maior e os botões menores
    col_input_field, col_buttons = st.columns([0.7, 0.3]) 
    
    with col_input_field:
        di_input_value = st.text_input(
            "ID da DI ou Referência para Carregar",
            key="detalhes_di_load_input",
            value=st.session_state.detalhes_di_input_value
        )
        st.session_state.detalhes_di_input_value = di_input_value
        
    with col_buttons:
        # Usar um sub-colunas para agrupar os botões na mesma linha
        # Adicionar um espaçador para alinhar os botões com o input de texto
        st.markdown("##") # Espaçador para alinhar os botões
        btn_load, btn_clear = st.columns(2)
        with btn_load:
            if st.button("Carregar DI", key="load_di_details_button", use_container_width=True):
                load_di_details(di_input_value)
        with btn_clear:
            if st.button("Limpar Campos", key="clear_di_details_button", use_container_width=True):
                st.session_state.detalhes_di_input_value = ""
                st.session_state.detalhes_di_data = None
                st.rerun() # Força rerun para limpar a UI

    # Inicializa df_details como um DataFrame vazio para evitar NameError
    df_details = pd.DataFrame()

    # Exibir detalhes da DI carregada
    if st.session_state.detalhes_di_data:
        di_data = st.session_state.detalhes_di_data
        st.markdown(f"#### Processo: **{di_data.get('informacao_complementar', 'N/A')}**")

        st.markdown("---")
        # Usar st.container para envolver as colunas e controlar a altura
        main_content_container = st.container()
        with main_content_container:
            col_details, col_calculations = st.columns(2)

            with col_details:
                st.markdown("##### Detalhes da Declaração de Importação")
                # Exibir detalhes em um formato de tabela ou lista
                details_to_display = {
                    "REFERENCIA": di_data.get('informacao_complementar'),
                    "Data do Registro": _format_date(di_data.get('data_registro')),
                    "VMLE": _format_currency(di_data.get('vmle')),
                    "Frete": _format_currency(di_data.get('frete')),
                    "Seguro": _format_currency(di_data.get('seguro')),
                    "VMLD": _format_currency(di_data.get('vmld')),
                    "II": _format_currency(di_data.get('imposto_importacao')),
                    "IPI": _format_currency(di_data.get('ipi')),
                    "Pis/Pasep": _format_currency(di_data.get('pis_pasep')),
                    "Cofins": _format_currency(di_data.get('cofins')),
                    "ICMS-SC": di_data.get('icms_sc'),
                    "Taxa Cambial (USD)": di_data.get('taxa_cambial_usd'),
                    "Taxa SISCOMEX": _format_currency(di_data.get('taxa_siscomex')),
                    "Nº Invoice": di_data.get('numero_invoice'),
                    "Peso Bruto (KG)": di_data.get('peso_bruto'),
                    "Peso Líquido (KG)": di_data.get('peso_liquido'),
                    "CNPJ Importador": di_data.get('cnpj_importador'),
                    "Importador Nome": di_data.get('importador_nome'),
                    "Recinto": di_data.get('recinto'),
                    "Embalagem": di_data.get('embalagem'),
                    "Quantidade Volumes": di_data.get('quantidade_volumes'),
                    "Acréscimo": _format_currency(di_data.get('acrescimo')),
                    "Armazenagem (DB)": _format_currency(di_data.get('armazenagem')), # Valor salvo no DB
                    "Frete Nacional (DB)": _format_currency(di_data.get('frete_nacional')), # Valor salvo no DB
                    "Arquivo Origem": di_data.get('arquivo_origem'),
                    "Data Importação": _format_date(di_data.get('data_importacao', '').split(' ')[0]) # Apenas a data
                }
                
                # Exibir como DataFrame transposto para melhor visualização de muitos campos
                # Aumentar a altura para 700 pixels
                df_details = pd.DataFrame.from_dict(details_to_display, orient='index', columns=['Valor'])
                st.dataframe(df_details, use_container_width=True, height=700) # Ajuste a altura conforme necessário

            with col_calculations:
                st.markdown("##### Cálculos Específicos")
                
                # --- Categoria: Despachantes ---
                st.markdown("###### Despachantes")
                st.button("Futura", key="calc_futura_button", disabled=True)
                st.markdown("---")

                # --- Categoria: Portos ---
                st.markdown("###### Portos")
                if st.button("Portonave", key="calc_portonave_button"):
                    navigate_to_portonave_calc()
                st.button("Itapoá", key="calc_itapoa_button", disabled=True)
                st.markdown("---")

                # --- Categoria: Aeroportos ---
                st.markdown("###### Aeroportos")
                st.button("Pac Log - Elo", key="calc_paclog_button", disabled=True)
                st.button("Ponta Negra", key="calc_pontanegra_button", disabled=True)
                st.button("Floripa Air", key="calc_floripaair_button", disabled=True)
                st.markdown("---")

                # --- Categoria: Frete Nacional ---
                st.markdown("###### Frete Nacional")
                st.button("FN Transportes", key="calc_fntransportes_button", disabled=True)
                st.markdown("---")

                # --- Categoria: Seguro ---
                st.markdown("###### Seguro")
                st.button("Ação", key="calc_acao_button", disabled=True)
                st.markdown("---")

                # --- Categoria: Conferências ---
                st.markdown("###### Conferências")
                st.button("Seguro", key="calc_seguro_button", disabled=True)
                st.button("Fechamento", key="calc_fechamento_button", disabled=True)
                st.markdown("---")

                # Removendo o st.info aqui, pois o usuário pediu para removê-lo
                # st.info("Clicar nestes botões simularia a navegação para a respectiva tela de cálculo, passando o ID da DI.")

    else:
        st.info("Nenhuma Declaração de Importação carregada. Por favor, insira um ID ou Referência e clique em 'Carregar DI'.")

    st.markdown("---")
    st.write("Esta tela permite visualizar os detalhes de uma Declaração de Importação e navegar para telas de cálculo específicas.")

