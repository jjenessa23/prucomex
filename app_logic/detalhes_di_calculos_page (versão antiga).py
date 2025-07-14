import streamlit as st
import pandas as pd
from datetime import datetime
import logging
import os
import base64

# Importar funções do módulo de utilitários de banco de dados
from db_utils import (
    get_declaracao_by_id,
    get_declaracao_by_referencia,
    get_all_declaracoes,
    get_frete_internacional_by_referencia
)
# Importar a função _clean_reference_string do db_utils
try:
    from db_utils import _clean_reference_string
except ImportError:
    def _clean_reference_string(s: str) -> str:
        if not isinstance(s, str):
            return str(s) if s is not None else ""
        return s.strip().upper()

# Importar as páginas de cálculo Streamlit (mantidas como estão)
from app_logic import calculo_portonave_page
from app_logic import calculo_futura_page
from app_logic import calculo_paclog_elo_page
from app_logic import calculo_fechamento_page
from app_logic import calculo_fn_transportes_page
from app_logic import calculo_frete_internacional_page

logger = logging.getLogger(__name__)

# --- Função para definir imagem de fundo com opacidade ---
def set_background_image(image_path):
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
            /* Estilo para contêineres tipo "card" */
            .stContainer {{
                border-radius: 10px;
                box-shadow: 0 4px 8px rgba(0, 0, 0, 0.1);
                padding: 20px;
                margin-bottom: 20px;
                background-color: rgba(255, 255, 255, 0.05); /* Levemente transparente para o fundo escuro */
                border: 1px solid rgba(255, 255, 255, 0.1);
            }}
            /* Ajustes para texto em dark mode */
            .stMarkdown, .stText, .stTextInput > label > div, .stSelectbox > label > div {{
                color: #e0e0e0; /* Cor mais clara para texto */
            }}
            h1, h2, h3, h4, h5, h6 {{
                color: #f0f0f0; /* Cor mais clara para títulos */
            }}
            /* Estilo dos botões */
            .stButton > button {{
                border-radius: 8px;
                border: 1px solid #4CAF50; /* Cor de borda para destacar */
                color: #FFFFFF;
                background-color: #4CAF50; /* Cor de fundo */
                padding: 10px 15px;
                font-size: 16px;
                transition: all 0.3s ease;
            }}
            .stButton > button:hover:not(:disabled) {{
                background-color: #45a049;
                border-color: #45a049;
                box-shadow: 0 2px 4px rgba(0,0,0,0.2);
            }}
            .stButton > button:disabled {{
                opacity: 0.6;
                cursor: not-allowed;
            }}
            /* Estilo para st.metric */
            div[data-testid="stMetric"] {{
                background-color: rgba(255, 255, 255, 0.05);
                border-radius: 8px;
                padding: 15px;
                box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
                border: 1px solid rgba(255, 255, 255, 0.1);
                color: #e0e0e0;
            }}
            div[data-testid="stMetricValue"] {{
                color: #f0f0f0 !important; /* Valor mais destacado */
            }}
            div[data-testid="stMetricLabel"] {{
                color: #a0a0a0 !important; /* Rótulo mais sutil */
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

# --- Função auxiliar para criar botões com ícones (ajustada para o novo estilo) ---
def icon_button(label, emoji_icon, key, disabled=False, use_container_width=True):
    """Cria um botão com um emoji como ícone, adaptado para o novo estilo."""
    # A maioria dos estilos de botão agora é global via st.markdown no set_background_image
    # Apenas garantimos o uso do use_container_width=False para controle de tamanho aqui
    return st.button(
        f"{emoji_icon} {label}",
        key=key,
        disabled=disabled,
        use_container_width=False
    )

# --- Funções de Ação ---

def _perform_di_loading(input_value):
    """
    Função auxiliar que contém a lógica de carregamento da DI.
    Atualiza st.session_state diretamente, não contém st.rerun().
    """
    st.session_state.detalhes_di_data = None # Limpa dados anteriores
    st.session_state.frete_internacional_calculado = 0.0 # Limpa o frete internacional calculado

    if not input_value:
        st.info("Digite uma Referência ou ID da DI para carregar os detalhes.")
        return False # Indica que nenhum dado foi carregado

    if get_declaracao_by_id is None or get_declaracao_by_referencia is None:
        st.error("Serviço de banco de dados não disponível.")
        return False

    di_data_row = None
    
    # Tenta carregar por ID (se for numérico)
    try:
        declaracao_id = int(input_value)
        logger.info(f"Tentando carregar DI por ID: {declaracao_id}")
        di_data_row = get_declaracao_by_id(declaracao_id)
    except ValueError:
        # Se não for um ID numérico, tenta carregar por Referência
        cleaned_input_value = _clean_reference_string(input_value)
        logger.info(f"Valor '{input_value}' não é um ID numérico. Tentando buscar por Referência (normalizada): '{cleaned_input_value}'.")
        di_data_row = get_declaracao_by_referencia(cleaned_input_value)
    
    if di_data_row:
        st.session_state.detalhes_di_data = dict(di_data_row)
        st.success(f"DI {_format_di_number(st.session_state.detalhes_di_data.get('numero_di', ''))} carregada com sucesso!")
        logging.info(f"Detalhes da DI '{input_value}' carregados.")
        
        # Tenta carregar o frete internacional associado
        referencia_processo = st.session_state.detalhes_di_data.get('informacao_complementar')
        if referencia_processo:
            frete_internacional_data = get_frete_internacional_by_referencia(referencia_processo)
            if frete_internacional_data:
                if frete_internacional_data['tipo_frete'] == 'Aéreo':
                    st.session_state.frete_internacional_calculado = frete_internacional_data.get('total_aereo_brl', 0.0)
                elif frete_internacional_data['tipo_frete'] == 'Marítimo':
                    st.session_state.frete_internacional_calculado = frete_internacional_data.get('total_maritimo_brl', 0.0)
                logger.info(f"Frete internacional de R$ {st.session_state.frete_internacional_calculado:.2f} carregado para referência '{referencia_processo}'.")
            else:
                logger.info(f"Nenhum frete internacional encontrado para a referência '{referencia_processo}'.")
        return True
    else:
        st.error(f"Nenhum dado encontrado para a DI: '{input_value}'. Verifique o ID ou a Referência.")
        logging.warning(f"Tentativa de carregar DI '{input_value}' falhou: não encontrada por ID ou Referência.")
        return False


def load_di_details_manual(input_value):
    _perform_di_loading(input_value)


def load_di_details():
    if _perform_di_loading(st.session_state.detalhes_di_input_text):
        st.rerun()


def navigate_to_calc_page(page_name, di_id_session_key):
    if 'detalhes_di_data' in st.session_state and st.session_state.detalhes_di_data:
        # Limpa os dados da DI da página de cálculo específica para forçar um refresh
        if page_name == "Cálculo Futura":
            st.session_state.futura_di_data = None
        elif page_name == "Cálculo Pac Log - Elo":
            st.session_state.elo_di_data = None
        elif page_name == "Cálculo Fechamento":
            st.session_state.fechamento_di_data = None
        elif page_name == "Cálculo FN Transportes":
            st.session_state.fn_transportes_di_data = None
        elif page_name == "Cálculo Frete Internacional":
            st.session_state.frete_internacional_di_data = None


        st.session_state.current_page = page_name
        st.session_state[di_id_session_key] = st.session_state.detalhes_di_data['id']
        st.rerun()
    else:
        st.warning("Por favor, carregue uma DI antes de ir para o cálculo.")


# --- Tela Principal do Streamlit para Detalhes DI e Cálculos ---
def show_page():
    background_image_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'assets', 'logo_navio_atracado.png')
    set_background_image(background_image_path)

    if st.button("Voltar para Follow-up Importação"):
        st.session_state.current_page = "Follow-up Importação"
        st.rerun()

    if 'detalhes_di_data' not in st.session_state:
        st.session_state.detalhes_di_data = None
    if 'detalhes_di_input_text' not in st.session_state: 
        st.session_state.detalhes_di_input_text = "" 
    if 'frete_internacional_calculado' not in st.session_state: 
        st.session_state.frete_internacional_calculado = 0.0

    if 'last_processed_di_reference' not in st.session_state:
        st.session_state.last_processed_di_reference = None
    
    current_input_ref = st.session_state.detalhes_di_input_text
    current_loaded_di_ref = st.session_state.detalhes_di_data.get('informacao_complementar') if st.session_state.detalhes_di_data else None

    if current_input_ref and (
        current_input_ref != st.session_state.last_processed_di_reference or
        current_loaded_di_ref is None or
        _clean_reference_string(current_input_ref) != _clean_reference_string(current_loaded_di_ref)
    ):
        logger.info(f"Detectada nova referência '{current_input_ref}'. Tentando carregamento inicial da DI.")
        if _perform_di_loading(current_input_ref):
            st.session_state.last_processed_di_reference = current_input_ref


    # --- SEÇÃO: Carregar Declaração de Importação (SEM ALTERAÇÕES VISUAIS AQUI) ---
    st.markdown("### Carregar Declaração de Importação")
    # O campo de texto foi movido para um container para melhor espaçamento, mas sem alteração no widget
    with st.container(): # Novo contêiner para a seção de input
        st.text_input(
            "Referência para Carregar (ID ou Processo)",
            value=st.session_state.detalhes_di_input_text,
            key="detalhes_di_input_text",
            on_change=load_di_details
        )
    st.markdown("---") # Linha separadora

    # --- SEÇÃO: Exibir detalhes da DI carregada ---
    if st.session_state.detalhes_di_data:
        di_data = st.session_state.detalhes_di_data
        
        # Novo layout com cards/contêineres
        st.markdown(f"## Processo: **{di_data.get('informacao_complementar', 'N/A')}**")
        st.write("") # Espaçamento

        # Contêiner para as métricas chave
        with st.container():
            st.markdown("#### Resumo da DI")
            col_vmle, col_vmld, col_frete, col_frete_int = st.columns(4)
            with col_vmle:
                st.metric("VMLE", _format_currency(di_data.get('vmle', 0.0)))
            with col_vmld:
                st.metric("VMLD", _format_currency(di_data.get('vmld', 0.0)))
            with col_frete:
                st.metric("Frete (DI)", _format_currency(di_data.get('frete', 0.0)))
            with col_frete_int:
                st.metric("Frete Intl. (Calc)", _format_currency(st.session_state.frete_internacional_calculado))
        
        st.write("") # Espaçamento
        
        # Contêiner principal para detalhes e cálculos
        main_layout_cols = st.columns([2, 1]) # Proporção ajustada para mais detalhes

        with main_layout_cols[0]: # Coluna da esquerda para detalhes
            with st.expander("##### Detalhes Completos da Declaração de Importação", expanded=False): # Agora em um expander
                details_to_display = {
                    "REFERENCIA": di_data.get('informacao_complementar'),
                    "Data do Registro": _format_date(di_data.get('data_registro')),
                    "VMLE": _format_currency(di_data.get('vmle')),
                    "Frete (DI)": _format_currency(di_data.get('frete')),
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
                    "Armazenagem (DB)": _format_currency(di_data.get('armazenagem')),
                    "Frete Nacional (DB)": _format_currency(di_data.get('frete_nacional')),
                    "Frete Internacional (Calculado)": _format_currency(st.session_state.frete_internacional_calculado),
                    "Arquivo Origem": di_data.get('arquivo_origem'),
                    "Data Importação": _format_date(di_data.get('data_importacao', '').split(' ')[0])
                }
                
                df_details = pd.DataFrame.from_dict(details_to_display, orient='index', columns=['Valor'])
                st.dataframe(
                    df_details, 
                    use_container_width=True,
                    height=min(len(details_to_display) * 35 + 38, 700) # Altura ajustável, mas com limite
                )

        with main_layout_cols[1]: # Coluna da direita para botões de cálculo
            with st.container(): # Contêiner para agrupar os botões de cálculo
                with st.popover("##### Acessar Cálculos", use_container_width=True): # Título do popover alterado
                    st.markdown("###### Despachantes")
                    if icon_button("Futura", "📝", "calc_futura_button"):
                        navigate_to_calc_page("Cálculo Futura", "selected_di_id_futura")
                    st.markdown("---")

                    st.markdown("###### Portos")
                    if icon_button("Portonave", "🚢", "calc_portonave_button"):
                        navigate_to_calc_page("Cálculo Portonave", "portonave_selected_di_id")
                    icon_button("Itapoá", "🚢", "calc_itapoa_button", disabled=True)
                    st.markdown("---")

                    st.markdown("###### Aeroportos")
                    if icon_button("Pac Log - Elo", "✈️", "calc_paclog_button"):
                        navigate_to_calc_page("Cálculo Pac Log - Elo", "selected_di_id_paclog")
                    icon_button("Ponta Negra", "✈️", "calc_pontanegra_button", disabled=True)
                    icon_button("Floripa Air", "✈️", "calc_floripaair_button", disabled=True)
                    st.markdown("---")

                    st.markdown("###### Fretes")
                    if icon_button("FN Transportes", "🚚", "calc_fntransportes_button", disabled=False):
                        navigate_to_calc_page("Cálculo FN Transportes", "selected_di_id_fn_transportes")
                    if icon_button("Frete Internacional", "🌍", "calc_frete_internacional_button", disabled=False):
                        navigate_to_calc_page("Cálculo Frete Internacional", "selected_di_id_frete_internacional")
                    st.markdown("---")

                    st.markdown("###### Seguro")
                    icon_button("Ação", "🛡️", "calc_acao_button", disabled=True)
                    st.markdown("---")

                    st.markdown("###### Conferências")
                    icon_button("Seguro", "✅", "calc_seguro_button", disabled=True)
                    if icon_button("Fechamento", "📊", "calc_fechamento_button"):
                        navigate_to_calc_page("Cálculo Fechamento", "selected_di_id_fechamento")
                    st.markdown("---")

    else:
        st.info("Nenhuma Declaração de Importação carregada. Por favor, digite uma Referência ou ID para começar.")

    st.markdown("---")
    st.write("Esta tela permite visualizar os detalhes de uma Declaração de Importação e navegar para telas de cálculo específicas.")