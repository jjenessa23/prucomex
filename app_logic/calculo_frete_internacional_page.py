from time import sleep
import pytz
import streamlit as st
import os
import base64
from datetime import datetime
import logging
import streamlit.components.v1 as components # Importar components para HTML/JS

# Importações para envio de e-mail
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders

# Importar funções de utilidade do módulo utils
# NOTE: Assumindo que estas funções estão definidas em 'app_logic.utils'
# A função set_background_image e get_dolar_cotacao são assumidas
# como existentes no ambiente de execução.
try:
    from app_logic.utils import set_background_image, get_dolar_cotacao
except ImportError:
    # Placeholder para funções de utilidade se o módulo não for encontrado
    def set_background_image(img_path):
        st.sidebar.markdown("<!-- Imagem de fundo não carregada em ambiente de teste -->", unsafe_allow_html=True)
    def get_dolar_cotacao():
        return 5.5000 # Valor de placeholder

# NOVO: Importar funções do db_utils para salvar e carregar frete internacional
# NOTE: Assumindo que estas funções estão definidas em 'app_logic.db_utils'
# As funções inserir_ou_atualizar_frete_internacional e get_frete_internacional_by_referencia
# são assumidas como existentes no ambiente de execução.
try:
    from app_logic.db_utils import (
        inserir_ou_atualizar_frete_internacional,
        get_frete_internacional_by_referencia
    )
except ImportError:
    # Placeholder para funções de DB se o módulo não for encontrado
    def inserir_ou_atualizar_frete_internacional(dados):
        st.session_state.db_response = f"Simulação salva (Placeholder): {dados.get('referencia')}"
        logging.info(f"DB placeholder: Salvo {dados}")
    def get_frete_internacional_by_referencia(ref):
        return None

logger = logging.getLogger(__name__)

# --- Função para formatar moeda ---
def _format_currency(value, prefix="R$ "):
    """
    Formata um valor numérico para o formato de moeda, trocando '.' por ','.
    Adiciona 4 casas decimais para valores monetários e um prefixo padrão.
    """
    try:
        # Tenta converter para float. Se 'N/A' ou similar, tratar como 0.0
        val = float(str(value).replace(',', '.')) if isinstance(value, str) else float(value)
        # Formata com 4 casas decimais, troca ponto por vírgula e separa milhar
        formatted = f"{prefix}{val:,.4f}".replace('.', '#').replace(',', '.').replace('#', ',')
        return formatted
    except (ValueError, TypeError):
        return "N/A"

# --- Funções de Callback (Limpar campos) ---
def _clear_maritimo_fields():
    """Reseta os campos e o estado de sessão da seção Marítimo."""
    st.session_state.taxa_agenciamento_maritimo = 0.0
    st.session_state.iof_maritimo = 0.0
    st.session_state.agency_fee_maritimo = 0.0
    st.session_state.referencia_maritimo = ""
    st.session_state.custo_frete_usd_maritimo = 0.0
    st.session_state.email_recipient_maritimo = ""
    st.session_state.email_subject_maritimo = f"Cálculo de Frete Marítimo - Ref: {datetime.now().strftime('%Y%m%d%H%M%S')}"
    st.session_state.email_body_maritimo = "Detalhes do cálculo:"
    if 'db_response' in st.session_state:
        del st.session_state.db_response
    st.success("Campos Marítimo limpos!")

def _clear_aereo_fields():
    """Reseta os campos e o estado de sessão da seção Aéreo."""
    st.session_state.taxa_agenciamento_aereo = 0.0
    st.session_state.iof_aereo = 0.0
    st.session_state.agency_fee_aereo = 0.0
    st.session_state.referencia_aereo = ""
    st.session_state.custo_frete_usd_aereo = 0.0
    st.session_state.email_recipient_aereo = ""
    st.session_state.email_subject_aereo = f"Cálculo de Frete Aéreo - Ref: {datetime.now().strftime('%Y%m%d%H%M%S')}"
    st.session_state.email_body_aereo = "Detalhes do cálculo:"
    if 'db_response' in st.session_state:
        del st.session_state.db_response
    st.success("Campos Aéreo limpos!")

# --- Função de Salvar no Banco de Dados (Chamada unificada) ---
def _save_frete_internacional(frete_type, total_brl, iof_usd, dolar_cotacao):
    """Salva os dados de frete internacional no Firestore."""
    referencia = st.session_state[f'referencia_{frete_type.lower()}']
    custo_frete_usd = st.session_state[f'custo_frete_usd_{frete_type.lower()}']
    
    if not referencia:
        st.error("ERRO: O campo 'Referência' é obrigatório para salvar.")
        return False
        
    dados = {
        "referencia": referencia,
        "tipo_frete": frete_type,
        "custo_frete_usd": custo_frete_usd,
        "iof_usd": iof_usd,
        "taxa_agenciamento": st.session_state[f'taxa_agenciamento_{frete_type.lower()}'],
        "agency_fee": st.session_state[f'agency_fee_{frete_type.lower()}'],
        "dolar_cotacao": dolar_cotacao,
        "total_brl": total_brl,
        "data_simulacao": datetime.now(pytz.timezone('America/Sao_Paulo')).isoformat(),
    }
    
    # Chama a função do db_utils
    inserir_ou_atualizar_frete_internacional(dados)
    
    st.success(f"Cálculo de Frete {frete_type} salvo com sucesso no banco de dados com a Referência: **{referencia}**.")
    
    # Atualiza o estado da sessão com a resposta do DB (se houver)
    if 'db_response' in st.session_state:
        st.info(st.session_state.db_response)
        
    return True

# --- Funções de Envio de E-mail ---
def _send_email(recipient, subject, body, frete_type, total_brl, anexo_base64=None):
    """
    Função genérica para enviar e-mail.
    Corrigida para garantir o envio.
    """
    # Credenciais do e-mail (obtidas de variáveis de ambiente)
    SENDER_EMAIL = os.environ.get("EMAIL_ADDRESS")
    SENDER_PASSWORD = os.environ.get("EMAIL_PASSWORD")
    SMTP_SERVER = os.environ.get("SMTP_SERVER", "smtp.gmail.com")
    SMTP_PORT = int(os.environ.get("SMTP_PORT", 587))
    
    if not all([SENDER_EMAIL, SENDER_PASSWORD]):
        st.error("ERRO: Credenciais de e-mail (EMAIL_ADDRESS/EMAIL_PASSWORD) não configuradas nas variáveis de ambiente.")
        return

    # 1. Configurar a mensagem
    msg = MIMEMultipart()
    msg['From'] = SENDER_EMAIL
    msg['To'] = recipient
    msg['Subject'] = subject

    # 2. Corpo do e-mail (adicionando o total calculado)
    total_formatado = _format_currency(total_brl, prefix="R$ ")
    full_body = (
        f"Prezado(a),\n\n"
        f"Segue a simulação do Frete {frete_type}.\n\n"
        f"{body}\n\n"
        f"**VALOR TOTAL (R$): {total_formatado}**\n\n"
        f"Atenciosamente,\n[Seu Nome/Empresa]"
    )
    
    msg.attach(MIMEText(full_body, 'plain'))

    # 3. Enviar
    try:
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()  # Habilitar segurança
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        text = msg.as_string()
        server.sendmail(SENDER_EMAIL, recipient, text)
        server.quit()
        st.success(f"E-mail de Frete {frete_type} enviado com sucesso para: **{recipient}**")
    except Exception as e:
        st.error(f"ERRO ao enviar e-mail: Verifique as credenciais ou o destinatário. Detalhes: {e}")
        logger.error(f"Erro no envio de e-mail: {e}")

def _send_email_maritimo(recipient, subject, body, total_brl):
    """Wrapper para enviar e-mail Marítimo."""
    _send_email(recipient, subject, body, "Marítimo", total_brl)

def _send_email_aereo(recipient, subject, body, total_brl):
    """Wrapper para enviar e-mail Aéreo."""
    _send_email(recipient, subject, body, "Aéreo", total_brl)

# --- Seção de Configuração de Estado e Layout ---
def _init_session_state():
    """Inicializa as variáveis de estado de sessão necessárias."""
    
    if 'page_title' not in st.session_state:
        st.session_state.page_title = "Cálculo de Frete Internacional"
        st.session_state.dolar_venda_abertura = get_dolar_cotacao()
        st.session_state.dolar_venda_abertura_editable = st.session_state.dolar_venda_abertura
        
    # Variáveis Marítimo
    if 'taxa_agenciamento_maritimo' not in st.session_state:
        st.session_state.taxa_agenciamento_maritimo = 0.0
        st.session_state.iof_maritimo = 0.0
        st.session_state.agency_fee_maritimo = 0.0
        st.session_state.referencia_maritimo = ""
        st.session_state.custo_frete_usd_maritimo = 0.0
        st.session_state.email_recipient_maritimo = ""
        st.session_state.email_subject_maritimo = f"Cálculo de Frete Marítimo - Ref: {datetime.now().strftime('%Y%m%d%H%M%S')}"
        st.session_state.email_body_maritimo = "Detalhes do cálculo:"

    # Variáveis Aéreo
    if 'taxa_agenciamento_aereo' not in st.session_state:
        st.session_state.taxa_agenciamento_aereo = 0.0
        st.session_state.iof_aereo = 0.0
        st.session_state.agency_fee_aereo = 0.0
        st.session_state.referencia_aereo = ""
        st.session_state.custo_frete_usd_aereo = 0.0
        st.session_state.email_recipient_aereo = ""
        st.session_state.email_subject_aereo = f"Cálculo de Frete Aéreo - Ref: {datetime.now().strftime('%Y%m%d%H%M%S')}"
        st.session_state.email_body_aereo = "Detalhes do cálculo:"

def _display_header():
    """Exibe o cabeçalho e as configurações globais (cotação)."""
    st.set_page_config(layout="wide")
    set_background_image('image_45aa0d.png')
    
    st.title(st.session_state.page_title)
    st.markdown("---")
    
    with st.expander("Configurações Gerais (Cotação do Dólar)"):
        st.info(f"Cotação do Dólar de Venda na Abertura (API): {_format_currency(st.session_state.dolar_venda_abertura, prefix='R$ ')}")
        
        # Campo para edição da cotação
        st.session_state.dolar_venda_abertura_editable = st.number_input(
            "Cotação do Dólar (Editable)", 
            min_value=0.0000, 
            value=st.session_state.dolar_venda_abertura_editable, 
            step=0.0001, 
            format="%.4f",
            key="dolar_editable_input"
        )
        st.markdown(f"**Cotação Usada no Cálculo:** {_format_currency(st.session_state.dolar_venda_abertura_editable, prefix='R$ ')}")
        
        # Botão para carregar cotação salva (referência)
        ref_to_load = st.text_input("Carregar cálculo pela Referência:", key="load_ref_input")
        if st.button("Carregar Referência", key="load_ref_button"):
            if ref_to_load:
                loaded_data = get_frete_internacional_by_referencia(ref_to_load)
                if loaded_data:
                    frete_type = loaded_data.get('tipo_frete', 'Marítimo')
                    tipo_lower = frete_type.lower()
                    
                    # Atualiza os campos relevantes
                    st.session_state[f'referencia_{tipo_lower}'] = loaded_data.get('referencia', '')
                    st.session_state[f'custo_frete_usd_{tipo_lower}'] = loaded_data.get('custo_frete_usd', 0.0)
                    st.session_state[f'taxa_agenciamento_{tipo_lower}'] = loaded_data.get('taxa_agenciamento', 0.0)
                    st.session_state[f'iof_{tipo_lower}'] = loaded_data.get('iof_usd', 0.0)
                    st.session_state[f'agency_fee_{tipo_lower}'] = loaded_data.get('agency_fee', 0.0)
                    st.session_state.dolar_venda_abertura_editable = loaded_data.get('dolar_cotacao', st.session_state.dolar_venda_abertura)
                    
                    st.success(f"Dados de Frete {frete_type} carregados com sucesso!")
                else:
                    st.warning(f"Nenhum cálculo encontrado para a Referência: {ref_to_load}")
            else:
                st.warning("Por favor, insira uma Referência para carregar.")

# --- Seções de Cálculo ---
def _display_maritimo_calculation():
    """Exibe a seção de cálculo Marítimo."""
    frete_type = "Marítimo"
    tipo_lower = frete_type.lower()
    
    st.header("🚢 Frete Marítimo")
    
    # Colunas para campos de entrada
    col1, col2 = st.columns(2)
    
    with col1:
        st.session_state.referencia_maritimo = st.text_input(
            "Referência",
            key="referencia_maritimo_input",
            value=st.session_state.referencia_maritimo
        )
        
        st.session_state.custo_frete_usd_maritimo = st.number_input(
            "Custo do Frete ($ USD)",
            min_value=0.00,
            value=st.session_state.custo_frete_usd_maritimo,
            step=1.00,
            format="%.2f",
            key="custo_frete_usd_maritimo_input"
        )
        
        st.session_state.taxa_agenciamento_maritimo = st.number_input(
            "Taxa de Agenciamento (% sobre Frete USD)",
            min_value=0.00,
            max_value=100.00,
            value=st.session_state.taxa_agenciamento_maritimo,
            step=0.01,
            format="%.2f",
            key="taxa_agenciamento_maritimo_input"
        )
        
    with col2:
        st.session_state.iof_maritimo = st.number_input(
            "IOF (% sobre Frete USD)",
            min_value=0.00,
            max_value=100.00,
            value=st.session_state.iof_maritimo,
            step=0.01,
            format="%.2f",
            key="iof_maritimo_input"
        )
        
        st.session_state.agency_fee_maritimo = st.number_input(
            "Agency Fee (R$)",
            min_value=0.00,
            value=st.session_state.agency_fee_maritimo,
            step=0.01,
            format="%.2f",
            key="agency_fee_maritimo_input"
        )
        
    # --- Cálculos ---
    custo_frete_usd = st.session_state.custo_frete_usd_maritimo
    dolar_cotacao = st.session_state.dolar_venda_abertura_editable
    
    # 1. IOF
    iof_maritimo_calculated_usd = custo_frete_usd * (st.session_state.iof_maritimo / 100.0)
    iof_maritimo_brl = iof_maritimo_calculated_usd * dolar_cotacao
    
    # 2. Taxa de Agenciamento
    taxa_agenciamento_calculated_usd = custo_frete_usd * (st.session_state.taxa_agenciamento_maritimo / 100.0)
    taxa_agenciamento_brl = taxa_agenciamento_calculated_usd * dolar_cotacao
    
    # 3. Conversão do Frete Original
    custo_frete_brl = custo_frete_usd * dolar_cotacao
    
    # 4. Total
    total_maritimo_brl_calculated = (
        custo_frete_brl + 
        iof_maritimo_brl + 
        taxa_agenciamento_brl + 
        st.session_state.agency_fee_maritimo
    )
    
    # --- Resultados ---
    st.markdown("### Resultados Detalhados")
    col_res1, col_res2, col_res3 = st.columns(3)

    # Coluna 1: Custo do Frete
    with col_res1:
        st.markdown("**CUSTO DO FRETE**")
        st.write(_format_currency(custo_frete_usd, prefix="$ "))
        st.write(_format_currency(custo_frete_brl, prefix="R$ "))
        st.write(" ") # Espaçador

    # Coluna 2: Taxa de Agenciamento e IOF
    with col_res2:
        st.markdown("**TAXAS (Agenciamento + IOF)**")
        st.write(_format_currency(taxa_agenciamento_calculated_usd, prefix="$ "))
        st.write(_format_currency(taxa_agenciamento_brl, prefix="R$ "))
        st.write(_format_currency(iof_maritimo_calculated_usd, prefix="$ "))
        st.write(_format_currency(iof_maritimo_brl, prefix="R$ "))

    # Coluna 3: Agency Fee
    with col_res3:
        st.markdown("**AGENCY FEE**")
        st.write("N/A") # Agency Fee não tem USD direto
        st.write("N/A") # Agency Fee não tem USD direto
        st.write(" ") # Espaçador
        st.write(_format_currency(st.session_state.agency_fee_maritimo, prefix="R$ "))
    
    st.markdown("---")
    st.metric(label="TOTAL (R$)", value=_format_currency(total_maritimo_brl_calculated, prefix="R$ "))

    # --- Seção de Configuração de E-mail (Visível, mas em expander para organização) ---
    with st.expander("📝 Configurar Envio de E-mail"):
        st.session_state.email_recipient_maritimo = st.text_input(
            "Destinatário do E-mail (separar por vírgula se múltiplos)",
            key="email_recipient_maritimo_input",
            value=st.session_state.email_recipient_maritimo
        )
        st.session_state.email_subject_maritimo = st.text_input(
            "Assunto do E-mail",
            key="email_subject_maritimo_input",
            value=st.session_state.email_subject_maritimo
        )
        st.session_state.email_body_maritimo = st.text_area(
            "Corpo do E-mail (Texto será anexado ao total final)",
            key="email_body_maritimo_input",
            value=st.session_state.email_body_maritimo,
            height=150
        )
        st.info("O **VALOR TOTAL (R$)** será automaticamente incluído no corpo do e-mail.")

    # --- Botões (Layout Correto e Funcionalidade Unificada) ---
    col_buttons_maritimo = st.columns(2)
    
    with col_buttons_maritimo[0]:
        # Botão LIMPAR
        st.button("LIMPAR Marítimo", key="clear_maritimo", on_click=_clear_maritimo_fields)
    
    with col_buttons_maritimo[1]:
        # NOVO: Botão ÚNICO para Salvar e Enviar E-mail (Atende ao requisito do usuário)
        if st.button("ENVIAR E-MAIL", key="save_and_send_maritimo", help="Salva os dados no banco e envia o e-mail"):
            if not st.session_state.email_recipient_maritimo:
                st.error("Por favor, preencha o campo 'Destinatário do E-mail' antes de enviar.")
            else:
                # 1. SALVAR NO BANCO
                is_saved = _save_frete_internacional(
                    frete_type, 
                    total_maritimo_brl_calculated, 
                    iof_maritimo_calculated_usd,
                    st.session_state.dolar_venda_abertura_editable
                )
                
                # 2. ENVIAR E-MAIL (SOMENTE se SALVO e se tiver Destinatário)
                if is_saved:
                    _send_email_maritimo(
                        st.session_state.email_recipient_maritimo, 
                        st.session_state.email_subject_maritimo, 
                        st.session_state.email_body_maritimo, 
                        total_maritimo_brl_calculated
                    )


def _display_aereo_calculation():
    """Exibe a seção de cálculo Aéreo."""
    frete_type = "Aéreo"
    tipo_lower = frete_type.lower()
    
    st.header("✈️ Frete Aéreo")
    
    # Colunas para campos de entrada
    col1, col2 = st.columns(2)
    
    with col1:
        st.session_state.referencia_aereo = st.text_input(
            "Referência",
            key="referencia_aereo_input",
            value=st.session_state.referencia_aereo
        )
        
        st.session_state.custo_frete_usd_aereo = st.number_input(
            "Custo do Frete ($ USD)",
            min_value=0.00,
            value=st.session_state.custo_frete_usd_aereo,
            step=1.00,
            format="%.2f",
            key="custo_frete_usd_aereo_input"
        )
        
        st.session_state.taxa_agenciamento_aereo = st.number_input(
            "Taxa de Agenciamento (% sobre Frete USD)",
            min_value=0.00,
            max_value=100.00,
            value=st.session_state.taxa_agenciamento_aereo,
            step=0.01,
            format="%.2f",
            key="taxa_agenciamento_aereo_input"
        )
        
    with col2:
        st.session_state.iof_aereo = st.number_input(
            "IOF (% sobre Frete USD)",
            min_value=0.00,
            max_value=100.00,
            value=st.session_state.iof_aereo,
            step=0.01,
            format="%.2f",
            key="iof_aereo_input"
        )
        
        st.session_state.agency_fee_aereo = st.number_input(
            "Agency Fee (R$)",
            min_value=0.00,
            value=st.session_state.agency_fee_aereo,
            step=0.01,
            format="%.2f",
            key="agency_fee_aereo_input"
        )
        
    # --- Cálculos ---
    custo_frete_usd = st.session_state.custo_frete_usd_aereo
    dolar_cotacao = st.session_state.dolar_venda_abertura_editable
    
    # 1. IOF
    iof_aereo_calculated_usd = custo_frete_usd * (st.session_state.iof_aereo / 100.0)
    iof_aereo_brl = iof_aereo_calculated_usd * dolar_cotacao
    
    # 2. Taxa de Agenciamento
    taxa_agenciamento_calculated_usd = custo_frete_usd * (st.session_state.taxa_agenciamento_aereo / 100.0)
    taxa_agenciamento_brl = taxa_agenciamento_calculated_usd * dolar_cotacao
    
    # 3. Conversão do Frete Original
    custo_frete_brl = custo_frete_usd * dolar_cotacao
    
    # 4. Total
    total_aereo_brl_calculated = (
        custo_frete_brl + 
        iof_aereo_brl + 
        taxa_agenciamento_brl + 
        st.session_state.agency_fee_aereo
    )
    
    # --- Resultados ---
    st.markdown("### Resultados Detalhados")
    col_res1, col_res2, col_res3 = st.columns(3)

    # Coluna 1: Custo do Frete
    with col_res1:
        st.markdown("**CUSTO DO FRETE**")
        st.write(_format_currency(custo_frete_usd, prefix="$ "))
        st.write(_format_currency(custo_frete_brl, prefix="R$ "))
        st.write(" ") # Espaçador

    # Coluna 2: Taxa de Agenciamento e IOF
    with col_res2:
        st.markdown("**TAXAS (Agenciamento + IOF)**")
        st.write(_format_currency(taxa_agenciamento_calculated_usd, prefix="$ "))
        st.write(_format_currency(taxa_agenciamento_brl, prefix="R$ "))
        st.write(_format_currency(iof_aereo_calculated_usd, prefix="$ "))
        st.write(_format_currency(iof_aereo_brl, prefix="R$ "))

    # Coluna 3: Agency Fee
    with col_res3:
        st.markdown("**AGENCY FEE**")
        st.write("N/A") # Agency Fee não tem USD direto
        st.write("N/A") # Agency Fee não tem USD direto
        st.write(" ") # Espaçador
        st.write(_format_currency(st.session_state.agency_fee_aereo, prefix="R$ "))
    
    st.markdown("---")
    st.metric(label="TOTAL (R$)", value=_format_currency(total_aereo_brl_calculated, prefix="R$ "))

    # --- Seção de Configuração de E-mail (Visível, mas em expander para organização) ---
    with st.expander("📝 Configurar Envio de E-mail"):
        st.session_state.email_recipient_aereo = st.text_input(
            "Destinatário do E-mail (separar por vírgula se múltiplos)",
            key="email_recipient_aereo_input",
            value=st.session_state.email_recipient_aereo
        )
        st.session_state.email_subject_aereo = st.text_input(
            "Assunto do E-mail",
            key="email_subject_aereo_input",
            value=st.session_state.email_subject_aereo
        )
        st.session_state.email_body_aereo = st.text_area(
            "Corpo do E-mail (Texto será anexado ao total final)",
            key="email_body_aereo_input",
            value=st.session_state.email_body_aereo,
            height=150
        )
        st.info("O **VALOR TOTAL (R$)** será automaticamente incluído no corpo do e-mail.")
        
    # --- Botões (Layout Correto e Funcionalidade Unificada) ---
    col_buttons_aereo = st.columns(2)
    
    with col_buttons_aereo[0]:
        # Botão LIMPAR
        st.button("LIMPAR Aéreo", key="clear_aereo", on_click=_clear_aereo_fields)
    
    with col_buttons_aereo[1]:
        # NOVO: Botão ÚNICO para Salvar e Enviar E-mail (Atende ao requisito do usuário)
        if st.button("ENVIAR E-MAIL", key="save_and_send_aereo", help="Salva os dados no banco e envia o e-mail"):
            if not st.session_state.email_recipient_aereo:
                st.error("Por favor, preencha o campo 'Destinatário do E-mail' antes de enviar.")
            else:
                # 1. SALVAR NO BANCO
                is_saved = _save_frete_internacional(
                    frete_type, 
                    total_aereo_brl_calculated, 
                    iof_aereo_calculated_usd,
                    st.session_state.dolar_venda_abertura_editable
                )
                
                # 2. ENVIAR E-MAIL (SOMENTE se SALVO e se tiver Destinatário)
                if is_saved:
                    _send_email_aereo(
                        st.session_state.email_recipient_aereo, 
                        st.session_state.email_subject_aereo, 
                        st.session_state.email_body_aereo, 
                        total_aereo_brl_calculated
                    )

# --- Função Principal ---
def app_main():
    """Função principal que monta a página."""
    _init_session_state()
    _display_header()
    
    # Estrutura com Tabs (para separar Marítimo e Aéreo)
    tab_maritimo, tab_aereo = st.tabs(["Cálculo Marítimo", "Cálculo Aéreo"])
    
    with tab_maritimo:
        _display_maritimo_calculation()
        
    with tab_aereo:
        _display_aereo_calculation()

if __name__ == "__main__":
    app_main()
