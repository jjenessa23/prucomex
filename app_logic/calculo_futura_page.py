import streamlit as st
import pandas as pd
import logging
import os
from datetime import datetime
import urllib.parse # Importa para codificar URLs para o mailto
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from time import sleep # Para pausas curtas na UI

# Importa as funções reais do db_utils
try:
    from db_utils import get_declaracao_by_id, update_declaracao
except ImportError:
    st.error("Erro: db_utils não encontrado. Certifique-se de que o arquivo está acessível.")
    get_declaracao_by_id = None
    update_declaracao = None

logger = logging.getLogger(__name__)

# --- Funções Auxiliares de Formatação ---
def _format_currency(value):
    """Formata um valor numérico para o formato de moeda R$ X.XXX,XX."""
    try:
        val = float(value)
        return f"R$ {val:,.2f}".replace('.', '#').replace(',', '.').replace('#', ',')
    except (ValueError, TypeError):
        return "R$ 0,00"

def _unformat_currency(text):
    """Converte uma string de moeda formatada para float."""
    try:
        # Remove R$, . (milhares) e substitui , por . (decimal)
        return float(text.replace('R$', '').replace('.', '').replace(',', '.').strip())
    except (ValueError, TypeError):
        return 0.0

def _format_float(value, decimals=4):
    """Formata um valor numérico float com um número específico de casas decimais."""
    try:
        val = float(value)
        # Garante que a formatação de milhares e decimais esteja correta
        return f"{val:,.{decimals}f}".replace('.', '#').replace(',', '.').replace('#', ',')
    except (ValueError, TypeError):
        return "N/A"

def _format_weight_no_kg(value):
    """Formata um valor numérico para peso com 3 casas decimais e 'KG'."""
    try:
        val = float(value)
        return f"{val:,.3f} KG".replace('.', '#').replace(',', '.').replace('#', ',')
    except (ValueError, TypeError):
        return "N/A"

def _format_int(value):
    """Formata um valor para inteiro."""
    try:
        val = int(value)
        return str(val)
    except (ValueError, TypeError):
        return "N/A"

# --- Constantes de Cálculo ---
ASSESSORIA_LOGISTICA = 1000.00
TAXA_MERCANTE_FIXA = 20.00
AFRMM_PERCENTUAL_CALC = 0.08

def perform_futura_calculations():
    """
    Realiza os cálculos para a tela Futura e atualiza o estado da sessão.
    """
    if 'futura_di_data' not in st.session_state or not st.session_state.futura_di_data:
        logger.warning("Não há dados da DI para realizar cálculos (Futura).")
        # Define valores padrão para os cálculos se não há DI data
        st.session_state.futura_imposto_importacao_display = "R$ 0,00"
        st.session_state.futura_ipi_display = "R$ 0,00"
        st.session_state.futura_pis_pasep_display = "R$ 0,00"
        st.session_state.futura_cofins_display = "R$ 0,00"
        st.session_state.futura_taxa_siscomex_display = "R$ 0,00"
        st.session_state.futura_icms_sc_display = "N/A"
        st.session_state.futura_total_debito_importador = "R$ 0,00"
        st.session_state.futura_assessoria_logistica_display = _format_currency(ASSESSORIA_LOGISTICA)
        st.session_state.futura_afrmm_comissaria_display = "R$ 0,00"
        st.session_state.futura_remessa_documentos_display = _format_currency(0.00)
        st.session_state.futura_total_debito_comissaria = _format_currency(ASSESSORIA_LOGISTICA + _unformat_currency(st.session_state.futura_diferenca_value))
        st.session_state.futura_taxa_ptax_display = "R$ 0,00"
        st.session_state.futura_taxa_mercante_afrmm_display = "R$ 0,00"
        st.session_state.futura_total_afrmm_calc_display = "R$ 0,00"
        return

    di_data = st.session_state.futura_di_data

    # Acessa os dados usando .get() para robustez
    # Garante que os nomes das chaves correspondem aos campos no DB
    # e fornece um valor padrão (0.0 ou "N/A") se a chave não existir.
    frete = di_data.get('frete', 0.0)
    acrescimo_xml = di_data.get('acrescimo', 0.0)
    ipi = di_data.get('ipi', 0.0)
    pis_pasep = di_data.get('pis_pasep', 0.0)
    cofins = di_data.get('cofins', 0.0)
    taxa_siscomex = di_data.get('taxa_siscomex', 0.0)
    imposto_importacao_xml = di_data.get('imposto_importacao', 0.0)
    icms_sc = di_data.get('icms_sc')
    taxa_cambial_usd = di_data.get('taxa_cambial_usd', 0.0)

    # Obter valores editáveis
    diferenca_atual_float = _unformat_currency(st.session_state.futura_diferenca_value)
    
    # Frete DI (Reais) e Acréscimo AFRMM agora são puxados diretamente do DB (di_data)
    frete_di_reais_float = float(frete)
    acrescimo_afrmm_float = float(acrescimo_xml)

    capatazias_afrmm_float = _unformat_currency(st.session_state.futura_capatazias_afrmm_value)
    tarifa_afrmm_float = _unformat_currency(st.session_state.futura_tarifa_afrmm_value)

    # --- Cálculos para VALORES ESTIMADOS PARA PAGAMENTO E/OU DÉBITO PELO IMPORTADOR ---
    imposto_importacao_calc = imposto_importacao_xml

    total_importador = imposto_importacao_calc + ipi + pis_pasep + cofins + taxa_siscomex
    # Verifica se icms_sc é um valor numérico antes de tentar somar
    if icms_sc and isinstance(icms_sc, str):
        try:
            total_importador += float(icms_sc.replace('R$', '').replace('.', '').replace(',', '.').strip())
        except ValueError:
            pass # Não adiciona se não for um número válido
    elif isinstance(icms_sc, (int, float)):
        total_importador += icms_sc


    st.session_state.futura_imposto_importacao_display = _format_currency(imposto_importacao_calc)
    st.session_state.futura_ipi_display = _format_currency(ipi)
    st.session_state.futura_pis_pasep_display = _format_currency(pis_pasep)
    st.session_state.futura_cofins_display = _format_currency(cofins)
    st.session_state.futura_taxa_siscomex_display = _format_currency(taxa_siscomex)
    st.session_state.futura_icms_sc_display = icms_sc if icms_sc else "N/A"
    st.session_state.futura_total_debito_importador = _format_currency(total_importador)

    # --- Cálculos para VALORES ESTIMADOS PARA DEPÓSITOS E PAGAMENTOS PELA COMISSÁRIA DE DESPACHOS ---
    total_afrmm_calc = 0.0
    if st.session_state.futura_tipo_transporte == "Marítimo":
        # Fórmula AFRMM: (Frete(BRL) + Acrescimo(BRL) + capatazia(BRL) ) x 0,08 + Tarifa + Taxa do Mercante
        total_afrmm_calc = (frete_di_reais_float + acrescimo_afrmm_float + capatazias_afrmm_float) * AFRMM_PERCENTUAL_CALC + tarifa_afrmm_float + TAXA_MERCANTE_FIXA
        st.session_state.futura_afrmm_comissaria_display = _format_currency(total_afrmm_calc)
        st.session_state.futura_total_afrmm_calc_display = _format_currency(total_afrmm_calc)
        st.session_state.futura_taxa_ptax_display = _format_float(taxa_cambial_usd, decimals=4) # Taxa PTAX é a Taxa Cambial (USD)
        st.session_state.futura_taxa_mercante_afrmm_display = _format_currency(TAXA_MERCANTE_FIXA)
    else:
        st.session_state.futura_afrmm_comissaria_display = _format_currency(0.00)
        st.session_state.futura_total_afrmm_calc_display = _format_currency(0.00)
        st.session_state.futura_taxa_ptax_display = "R$ 0,00" # Não aplica para Aéreo
        st.session_state.futura_taxa_mercante_afrmm_display = "R$ 0,00" # Não aplica para Aéreo

    st.session_state.futura_assessoria_logistica_display = _format_currency(ASSESSORIA_LOGISTICA)
    st.session_state.futura_remessa_documentos_display = _format_currency(0.00)

    total_comissaria = ASSESSORIA_LOGISTICA + total_afrmm_calc + 0.00 # Remessa de documentos (assumindo 0.00)
    st.session_state.futura_total_debito_comissaria = _format_currency(total_comissaria + diferenca_atual_float)


def load_futura_di_data(declaracao_id):
    """
    Carrega os dados da DI para a tela Futura e inicializa o estado da sessão.
    """
    if not declaracao_id:
        logger.warning("Nenhum ID de declaração fornecido para carregar dados (Futura).")
        clear_futura_di_data()
        return

    logger.info(f"Carregando dados para DI ID (Futura): {declaracao_id}")
    di_data_dict = get_declaracao_by_id(declaracao_id) # Agora retorna um dicionário

    if di_data_dict: # Verifica se o dicionário não é None
        st.session_state.futura_di_data = di_data_dict # Armazena o dicionário diretamente
        
        # Acessa os dados usando .get() para robustez e legibilidade
        informacao_complementar = di_data_dict.get('informacao_complementar')
        frete = di_data_dict.get('frete', 0.0)
        acrescimo = di_data_dict.get('acrescimo', 0.0) 

        st.session_state.futura_processo_ref = informacao_complementar if informacao_complementar else "N/A"
        
        # Inicializa os campos editáveis com valores da DI ou padrão
        st.session_state.futura_diferenca_value = _format_currency(0.00)
        # Frete DI (Reais) e Acréscimo AFRMM agora são exibidos, não editáveis
        st.session_state.futura_frete_di_reais_display = _format_currency(frete)
        st.session_state.futura_acrescimo_afrmm_display = _format_currency(acrescimo)

        st.session_state.futura_capatazias_afrmm_value = _format_currency(0.00)
        st.session_state.futura_tarifa_afrmm_value = _format_currency(0.00)
        # Define o tipo de transporte com base nos dados da DI, se disponível
        st.session_state.futura_tipo_transporte = di_data_dict.get('Modal', 'Aéreo') # Assumindo que a DI tem campo 'Modal'


        perform_futura_calculations() # Realiza os cálculos iniciais
    else:
        st.warning(f"Nenhum dado encontrado para a DI ID: {declaracao_id} (Futura)")
        clear_futura_di_data()

def clear_futura_di_data():
    """Limpa todos os dados e estados da sessão para a tela Futura."""
    st.session_state.futura_di_data = None
    st.session_state.futura_processo_ref = "PCH-XXXX-XX"

    st.session_state.futura_diferenca_value = _format_currency(0.00)
    st.session_state.futura_frete_di_reais_display = _format_currency(0.00)
    st.session_state.futura_acrescimo_afrmm_display = _format_currency(0.00)

    st.session_state.futura_capatazias_afrmm_value = _format_currency(0.00)
    st.session_state.futura_tarifa_afrmm_value = _format_currency(0.00)
    st.session_state.futura_tipo_transporte = "Aéreo"

    st.session_state.futura_imposto_importacao_display = "R$ 0,00"
    st.session_state.futura_ipi_display = "R$ 0,00"
    st.session_state.futura_pis_pasep_display = "R$ 0,00"
    st.session_state.futura_cofins_display = "R$ 0,00"
    st.session_state.futura_taxa_siscomex_display = "R$ 0,00"
    st.session_state.futura_icms_sc_display = "N/A"
    st.session_state.futura_total_debito_importador = "R$ 0,00"

    st.session_state.futura_assessoria_logistica_display = "R$ 0,00"
    st.session_state.futura_afrmm_comissaria_display = "R$ 0,00"
    st.session_state.futura_remessa_documentos_display = "R$ 0,00"
    st.session_state.futura_total_debito_comissaria = "R$ 0,00"

    st.session_state.futura_taxa_ptax_display = "R$ 0,00"
    st.session_state.futura_taxa_mercante_afrmm_display = "R$ 0,00"
    st.session_state.futura_total_afrmm_calc_display = "R$ 0,00"

    # Limpa os campos de e-mail também para garantir um estado limpo
    st.session_state.futura_email_to = "jjenessa23@gmail.com"
    st.session_state.futura_email_subject_send = ""
    st.session_state.futura_email_body_send = ""
    st.session_state.futura_email_attachments_list = []


# --- Funções de Envio e Salvamento de E-mail para Futura ---
def send_email_with_attachments_futura(to_emails, subject, body, uploaded_files):
    """
    Envia um e-mail com anexos via Gmail SMTP.
    Os e-mails são lidos dos segredos do Streamlit.
    """
    try:
        remetente = st.secrets["gmail_credentials"]["gmail_email"]
        senha_aplicativo = st.secrets["gmail_credentials"]["gmail_app_password"]

        msg = MIMEMultipart()
        msg["Subject"] = subject
        msg["From"] = remetente
        msg["To"] = ", ".join(to_emails)

        msg.attach(MIMEText(body, "plain"))

        for uploaded_file in uploaded_files:
            try:
                part = MIMEBase("application", "octet-stream")
                part.set_payload(uploaded_file.read())
                encoders.encode_base64(part)
                part.add_header("Content-Disposition", f"attachment; filename= {uploaded_file.name}")
                msg.attach(part)
            except Exception as e:
                st.warning(f"Erro ao anexar o arquivo '{uploaded_file.name}': {e}. O e-mail será enviado sem este anexo.")

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(remetente, senha_aplicativo)
            smtp.send_message(msg)
        st.success("E-mail enviado com sucesso!")
        return True
    except KeyError as e:
        st.error(f"Credenciais de e-mail não configuradas nos segredos do Streamlit. Verifique a seção [gmail_credentials] e as chaves 'gmail_email' e 'gmail_app_password'. Erro: {e}")
        return False
    except Exception as e:
        st.error(f"Erro ao enviar o e-mail: {e}. Verifique se a 'senha de aplicativo' do Gmail está correta e se o acesso SMTP está liberado.")
        return False

def save_futura_calculations_to_db():
    """
    Salva os valores calculados (Honorarios_Despachante e AFRMM) no banco de dados da DI.
    """
    if 'futura_di_data' not in st.session_state or st.session_state.futura_di_data is None:
        st.warning("Dados da DI não carregados para salvar cálculos.")
        return False

    if update_declaracao is None:
        st.error("A função 'update_declaracao' não está disponível. Verifique a importação de db_utils.")
        return False

    declaracao_id = st.session_state.futura_di_data.get('id')
    
    # Valores a serem salvos
    honorarios_despachante = _unformat_currency(st.session_state.futura_assessoria_logistica_display)
    # AFRMM só é salvo se o transporte for Marítimo
    valor_afrmm_calculado = _unformat_currency(st.session_state.futura_total_afrmm_calc_display) \
                            if st.session_state.futura_tipo_transporte == "Marítimo" else 0.0

    updates = {
        "Honorarios_Despachante": honorarios_despachante,
        "Valor_AFRMM_Calculado": valor_afrmm_calculado
    }

    try:
        # Pega a DI atualizada do session_state, faz uma cópia e aplica os updates
        current_di_data = dict(st.session_state.futura_di_data)
        current_di_data.update(updates)

        success = update_declaracao(declaracao_id, current_di_data)
        if success:
            st.success("Valores de Honorários e AFRMM salvos no banco de dados da DI!")
            # Atualiza o di_data no session_state para refletir os valores salvos
            st.session_state.futura_di_data = current_di_data
            return True
        else:
            st.error("Falha ao salvar os valores de Honorários e AFRMM no banco de dados.")
            return False
    except Exception as e:
        st.error(f"Ocorreu um erro inesperado ao salvar cálculos Futura: {e}")
        logger.exception("Erro inesperado ao salvar cálculos Futura no DB.")
        return False


def handle_futura_email_and_save(email_type: str):
    """
    Gerencia a lógica de exibir o formulário de e-mail, enviar e salvar no DB.
    """
    if not st.session_state.get('futura_di_data'):
        st.warning("Carregue os dados da DI antes de enviar o e-mail.")
        return

    # Gera o conteúdo do e-mail de acordo com o tipo
    if email_type == "Pagamento de Honorários":
        email_subject_generated, email_body_plaintext_generated = generate_payment_email_content()
    elif email_type == "Débito em Conta":
        email_subject_generated, email_body_plaintext_generated = generate_debit_email_content()
    else: # Fallback para conferência se for o caso
        email_subject_generated, email_body_plaintext_generated = generate_email_content_futura()

    # Preenche os campos do formulário de envio de e-mail
    # Força a atualização dos campos de assunto e corpo para refletir o tipo de e-mail selecionado
    st.session_state.futura_email_subject_send = email_subject_generated
    st.session_state.futura_email_body_send = email_body_plaintext_generated
    
    # Usa um formulário para encapsular os inputs do e-mail e o botão de envio
    with st.form(key=f"email_form_{email_type.replace(' ', '_')}"):
        st.markdown(f"##### Enviar E-mail: {email_type}")

        to_emails_input = st.text_input(
            "Para (e-mails separados por vírgula):",
            value=st.session_state.futura_email_to,
            key=f"futura_send_to_emails_input_{email_type}"
        )
        st.session_state.futura_email_to = to_emails_input.strip()

        st.session_state.futura_email_subject_send = st.text_input(
            "Assunto:",
            value=st.session_state.futura_email_subject_send,
            key=f"futura_send_email_subject_input_{email_type}"
        )
        
        st.session_state.futura_email_body_send = st.text_area(
            "Corpo do E-mail:",
            value=st.session_state.futura_email_body_send,
            height=300,
            key=f"futura_send_email_body_input_{email_type}"
        )
        
        uploaded_files = st.file_uploader(
            "Arraste e solte ou selecione arquivos para anexar (múltiplos)",
            type=None,
            accept_multiple_files=True,
            key=f"futura_send_email_attachments_uploader_{email_type}"
        )
        if uploaded_files:
            current_attached_names = {f.name for f in st.session_state.futura_email_attachments_list}
            for file in uploaded_files:
                if file.name not in current_attached_names:
                    st.session_state.futura_email_attachments_list.append(file)
        
        if st.session_state.futura_email_attachments_list:
            st.markdown("###### Arquivos anexados:")
            for i, file in enumerate(st.session_state.futura_email_attachments_list):
                col_file_name, col_remove_btn = st.columns([0.8, 0.2])
                with col_file_name:
                    st.write(f"- {file.name}")
                with col_remove_btn:
                    # Removido o key do form_submit_button
                    if st.form_submit_button("Remover", key=f"futura_remove_attachment_{email_type}_{i}"):
                        st.session_state.futura_email_attachments_list.pop(i)
                        st.rerun()

        col_send, col_cancel = st.columns(2)
        with col_send:
            # Removido o key do form_submit_button
            if st.form_submit_button("Enviar E-mail e Salvar"):
                if not st.session_state.futura_email_to:
                    st.warning("Por favor, preencha o(s) destinatário(s) do e-mail.")
                else:
                    list_of_recipients = [email.strip() for email in st.session_state.futura_email_to.split(',') if email.strip()]
                    if list_of_recipients:
                        with st.spinner("Enviando e-mail e salvando no banco de dados..."):
                            email_sent_successfully = send_email_with_attachments_futura(
                                to_emails=list_of_recipients,
                                subject=st.session_state.futura_email_subject_send,
                                body=st.session_state.futura_email_body_send,
                                uploaded_files=st.session_state.futura_email_attachments_list
                            )
                            if email_sent_successfully:
                                if save_futura_calculations_to_db():
                                    st.toast(f"✅ E-mail '{email_type}' enviado e dados salvos com sucesso!", icon="✅")
                                    # Limpa os campos após o envio bem-sucedido
                                    st.session_state.futura_email_to = "jjenessa23@gmail.com" # Reset para valor padrão
                                    st.session_state.futura_email_subject_send = ""
                                    st.session_state.futura_email_body_send = ""
                                    st.session_state.futura_email_attachments_list = []
                                else:
                                    st.error(f"E-mail '{email_type}' enviado, mas falha ao salvar dados no banco de dados.")
                            sleep(3) # Pausa para o usuário ver a mensagem
                        st.session_state.show_futura_email_expander = False # Fecha o expander
                        st.session_state.email_type_to_show = None
                        st.rerun()
                    else:
                        st.warning("Nenhum destinatário válido encontrado.")
        with col_cancel:
            # Removido o key do form_submit_button
            if st.form_submit_button("Cancelar"):
                st.session_state.show_futura_email_expander = False
                st.session_state.email_type_to_show = None
                st.rerun()


def show_calculo_futura_page():
    """
    Exibe a interface de usuário para o cálculo Futura.
    """
    # --- Configuração da Imagem de Fundo para a página ---
    try:
        from app_logic.utils import set_background_image, set_sidebar_background_image
    except ImportError:
        logging.warning("Módulo 'app_logic.utils' não encontrado. Funções de imagem de fundo podem não funcionar.")
        def set_background_image(image_path, opacity=None):
            pass # Função mock se utils não for encontrado
        def set_sidebar_background_image(image_path, opacity=None):
            pass # Função mock se utils não for encontrado
    background_image_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'assets', 'logo_navio_atracado.png')
    set_background_image(background_image_path)

    st.subheader("Cálculo Futura - Honorários e Impostos")

    # Inicializa o estado da sessão para esta página
    st.session_state.setdefault('futura_di_data', None)
    st.session_state.setdefault('futura_processo_ref', "PCH-XXXX-XX")
    st.session_state.setdefault('futura_diferenca_value', _format_currency(0.00))
    st.session_state.setdefault('futura_frete_di_reais_display', _format_currency(0.00))
    st.session_state.setdefault('futura_acrescimo_afrmm_display', _format_currency(0.00))
    st.session_state.setdefault('futura_capatazias_afrmm_value', _format_currency(0.00))
    st.session_state.setdefault('futura_tarifa_afrmm_value', _format_currency(0.00))
    st.session_state.setdefault('futura_tipo_transporte', "Aéreo")

    st.session_state.setdefault('futura_imposto_importacao_display', "R$ 0,00")
    st.session_state.setdefault('futura_ipi_display', "R$ 0,00")
    st.session_state.setdefault('futura_pis_pasep_display', "R$ 0,00")
    st.session_state.setdefault('futura_cofins_display', "R$ 0,00")
    st.session_state.setdefault('futura_taxa_siscomex_display', "R$ 0,00")
    st.session_state.setdefault('futura_icms_sc_display', "N/A")
    st.session_state.setdefault('futura_total_debito_importador', "R$ 0,00")

    st.session_state.setdefault('futura_assessoria_logistica_display', _format_currency(ASSESSORIA_LOGISTICA)) # Inicializado com valor da constante
    st.session_state.setdefault('futura_afrmm_comissaria_display', "R$ 0,00")
    st.session_state.setdefault('futura_remessa_documentos_display', "R$ 0,00")
    st.session_state.setdefault('futura_total_debito_comissaria', _format_currency(ASSESSORIA_LOGISTICA)) # Inicializado com assessoria

    st.session_state.setdefault('futura_taxa_ptax_display', "R$ 0,00")
    st.session_state.setdefault('futura_taxa_mercante_afrmm_display', "R$ 0,00")
    st.session_state.setdefault('futura_total_afrmm_calc_display', "R$ 0,00")
    
    st.session_state.setdefault('futura_email_to', "jjenessa23@gmail.com")
    st.session_state.setdefault('futura_email_subject_send', "")
    st.session_state.setdefault('futura_email_body_send', "")
    st.session_state.setdefault('futura_email_attachments_list', [])

    st.session_state.setdefault('show_futura_email_expander', False)
    st.session_state.setdefault('email_type_to_show', None)

    # Carrega os dados da DI se um ID foi passado da página anterior
    if 'selected_di_id_futura' in st.session_state and st.session_state.selected_di_id_futura is not None:
        if st.session_state.futura_di_data is None or st.session_state.futura_di_data.get('id') != st.session_state.selected_di_id_futura:
            load_futura_di_data(st.session_state.selected_di_id_futura)
            st.session_state.selected_di_id_futura = None # Limpa o ID após carregar
            st.rerun() # Força rerun para refletir os dados carregados nos inputs

    st.markdown(f"#### Processo: **{st.session_state.futura_processo_ref}**")
    st.markdown("---")

    # Seletor Tipo de Transporte
    st.session_state.futura_tipo_transporte = st.selectbox(
        "Tipo de Transporte:",
        ["Aéreo", "Marítimo"],
        key="futura_tipo_transporte_select",
        index=0 if st.session_state.futura_tipo_transporte == "Aéreo" else 1, # Define o índice padrão
        on_change=perform_futura_calculations # Recalcula ao alterar
    )
    # perform_futura_calculations() # Removido daqui, pois o on_change já cuida

    st.markdown("##### Cálculo Futura - Impostos e Taxas")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("###### VALORES ESTIMADOS PARA PAGAMENTO E/OU DÉBITO PELO IMPORTADOR")
        
        with st.expander("Detalhes dos Impostos do Importador", expanded=True):
            c1_imp, c2_imp = st.columns([0.7, 0.3])
            with c1_imp: st.markdown("- Imposto de Importação (e-DARF - código 0086):")
            with c2_imp: st.markdown(f"**{st.session_state.futura_imposto_importacao_display}**")

            c1_imp, c2_imp = st.columns([0.7, 0.3])
            with c1_imp: st.markdown("- Imposto s/Produtos Industrializados (e-DARF - código 1038):")
            with c2_imp: st.markdown(f"**{st.session_state.futura_ipi_display}**")

            c1_imp, c2_imp = st.columns([0.7, 0.3])
            with c1_imp: st.markdown("- PIS/PASEP na Importação (e-DARF - código 5602):")
            with c2_imp: st.markdown(f"**{st.session_state.futura_pis_pasep_display}**")

            c1_imp, c2_imp = st.columns([0.7, 0.3])
            with c1_imp: st.markdown("- COFINS na Importação (e-DARF - código 5629):")
            with c2_imp: st.markdown(f"**{st.session_state.futura_cofins_display}**")

            c1_imp, c2_imp = st.columns([0.7, 0.3])
            with c1_imp: st.markdown("- Taxa de Utilização do SISCOMEX (e-DARF - código 7811):")
            with c2_imp: st.markdown(f"**{st.session_state.futura_taxa_siscomex_display}**")

            c1_imp, c2_imp = st.columns([0.7, 0.3])
            with c1_imp: st.markdown("- ICMS-SC :")
            with c2_imp: st.markdown(f"**{st.session_state.futura_icms_sc_display}**")

            st.markdown("---")
            c1_imp, c2_imp = st.columns([0.7, 0.3])
            with c1_imp: st.markdown("**TOTAL DO DÉBITO (BRL):**")
            with c2_imp: st.markdown(f"**{st.session_state.futura_total_debito_importador}**")


    with col2:
        st.markdown("###### VALORES ESTIMADOS PARA DEPÓSITOS E PAGAMENTOS PELA COMISSÁRIA DE DESPACHOS")
        
        with st.expander("Detalhes dos Pagamentos da Comissária", expanded=True):
            c1_com, c2_com = st.columns([0.7, 0.3])
            with c1_com: st.markdown("- 1 - Assessoria do Processo Logístico Internacional:")
            with c2_com: st.markdown(f"**{st.session_state.futura_assessoria_logistica_display}**")

            if st.session_state.futura_tipo_transporte == "Marítimo":
                c1_com, c2_com = st.columns([0.7, 0.3])
                with c1_com: st.markdown("- 2 - AFRMM - Adicional de Frete p/Renovação da Marinha Mercante:")
                with c2_com: st.markdown(f"**{st.session_state.futura_afrmm_comissaria_display}**")

                c1_com, c2_com = st.columns([0.7, 0.3])
                with c1_com: st.markdown("- 3 - Remessa de Documentos para Liberação B/L/HAWB/CRT:")
                with c2_com: st.markdown(f"**{st.session_state.futura_remessa_documentos_display}**")
            
            st.markdown("---")
            c1_com, c2_com = st.columns([0.7, 0.3])
            with c1_com: st.markdown("**TOTAL DO DÉBITO (BRL):**")
            with c2_com: st.markdown(f"**{st.session_state.futura_total_debito_comissaria}**")
        
        st.markdown("---")
        st.markdown("###### Diferença")
        
        # Input de texto para Diferença
        diferenca_input = st.text_input(
            "Diferença",
            value=st.session_state.futura_diferenca_value,
            key="futura_diferenca_input",
            on_change=perform_futura_calculations, # Recalcula ao alterar
            label_visibility="collapsed" # Oculta o label padrão para melhor alinhamento
        )
        # Atualiza o valor no session_state após o input
        st.session_state.futura_diferenca_value = diferenca_input

        # Botões +0.01 e -0.01 em uma nova linha, centralizados ou alinhados
        col_diff_btn1, col_diff_btn2 = st.columns(2) # Duas colunas para os botões

        with col_diff_btn1:
            # Botão +0.01
            if st.button("+0.01", key="futura_diferenca_plus", use_container_width=True):
                try:
                    current_value = _unformat_currency(st.session_state.futura_diferenca_value)
                    st.session_state.futura_diferenca_value = _format_currency(round(current_value + 0.01, 2))
                    perform_futura_calculations()
                    st.rerun() # Força a atualização da tela
                except ValueError:
                    st.error("Valor inválido para Diferença.")
        with col_diff_btn2:
            # Botão -0.01
            if st.button("-0.01", key="futura_diferenca_minus", use_container_width=True):
                try:
                    current_value = _unformat_currency(st.session_state.futura_diferenca_value)
                    st.session_state.futura_diferenca_value = _format_currency(round(current_value - 0.01, 2))
                    perform_futura_calculations()
                    st.rerun() # Força a atualização da tela
                except ValueError:
                    st.error("Valor inválido para Diferença.")


    if st.session_state.futura_tipo_transporte == "Marítimo":
        st.markdown("---")
        st.markdown("###### Cálculo AFRMM")
        col_afrmm_input, col_afrmm_display = st.columns(2) # Removida a coluna de botões extra
        with col_afrmm_input:
            # Campos editáveis que permanecem inputs
            capatazias_afrmm_input = st.text_input(
                "Capatazias (R$)",
                value=st.session_state.futura_capatazias_afrmm_value,
                key="futura_capatazias_afrmm_input",
                on_change=perform_futura_calculations # Recalcula ao alterar
            )
            st.session_state.futura_capatazias_afrmm_value = capatazias_afrmm_input

            tarifa_afrmm_input = st.text_input(
                "Tarifa (R$)",
                value=st.session_state.futura_tarifa_afrmm_value,
                key="futura_tarifa_afrmm_input",
                on_change=perform_futura_calculations # Recalcula ao alterar
            )
            st.session_state.futura_tarifa_afrmm_value = tarifa_afrmm_input
            
        # Exibição dos resultados do cálculo AFRMM
        with col_afrmm_display:
            # Frete DI (Reais) - Agora apenas exibição
            st.markdown("**:blue[Detalhes AFRMM:]**")
            c1_afrmm, c2_afrmm = st.columns([0.7, 0.3])
            with c1_afrmm: st.markdown("- Frete DI (Reais):")
            with c2_afrmm: st.markdown(f"**{st.session_state.futura_frete_di_reais_display}**")

            # Acréscimo - Agora apenas exibição
            c1_afrmm, c2_afrmm = st.columns([0.7, 0.3])
            with c1_afrmm: st.markdown("- Acréscimo:")
            with c2_afrmm: st.markdown(f"**{st.session_state.futura_acrescimo_afrmm_display}**")

            # Taxa PTAX - Já era exibição
            c1_afrmm, c2_afrmm = st.columns([0.7, 0.3])
            with c1_afrmm: st.markdown("- Taxa PTAX: (USD)")
            with c2_afrmm: st.markdown(f"**{st.session_state.futura_taxa_ptax_display}**")

            # Taxa do Mercante - Já era exibição
            c1_afrmm, c2_afrmm = st.columns([0.7, 0.3])
            with c1_afrmm: st.markdown("- Taxa do Mercante:")
            with c2_afrmm: st.markdown(f"**{st.session_state.futura_taxa_mercante_afrmm_display}**")
            
            st.markdown("---")
            c1_afrmm, c2_afrmm = st.columns([0.7, 0.3])
            with c1_afrmm: st.markdown("**Total AFRMM:**")
            with c2_afrmm: st.markdown(f"**{st.session_state.futura_total_afrmm_calc_display}**")


    st.markdown("---")
    # Botões para abrir os expanders de e-mail
    st.markdown("###### Enviar E-mail")
    col_email_buttons = st.columns(2)
    with col_email_buttons[0]:
        if st.button("Pagamento de Honorários", key="futura_show_email_honorarios", use_container_width=True):
            st.session_state.email_type_to_show = "Pagamento de Honorários"
            st.session_state.show_futura_email_expander = True
            st.rerun()
    with col_email_buttons[1]:
        if st.button("Débito em Conta", key="futura_show_email_debito", use_container_width=True):
            st.session_state.email_type_to_show = "Débito em Conta"
            st.session_state.show_futura_email_expander = True
            st.rerun()

    # Expander para exibir o conteúdo do e-mail (agora com lógica de envio e salvamento)
    if st.session_state.get('show_futura_email_expander', False):
        email_type = st.session_state.get('email_type_to_show', "Conferência Futura") # Default para segurança
        
        # Chama a função que lida com a exibição do formulário de e-mail, envio e salvamento
        handle_futura_email_and_save(email_type)

    st.markdown("---")
    if st.button("Voltar para Detalhes da DI", key="futura_voltar_di"):
        st.session_state.current_page = "Pagamentos"
        st.rerun()

# --- Funções para Geração de Conteúdo de E-mail (mantidas, mas agora chamadas por handle_futura_email_and_save) ---
def generate_email_content_futura():
    """Gera o conteúdo do e-mail para exibição na tela Futura (Conferência)."""
    di_data = st.session_state.futura_di_data
    referencia_processo = di_data.get('informacao_complementar', 'N/A')
    
    total_debito_importador = st.session_state.futura_total_debito_importador
    total_debito_comissaria = st.session_state.futura_total_debito_comissaria
    diferenca = st.session_state.futura_diferenca_value

    current_hour = datetime.now().hour
    saudacao = "Bom dia" if 6 <= current_hour < 12 else "Boa tarde"
    usuario_programa = st.session_state.get('user_info', {}).get('username', 'usuário do sistema')
    data_atual_formatada = datetime.now().strftime("%d/%m/%Y")

    email_body_plaintext = f"""{saudacao},

Segue a conferência do processo: {referencia_processo}

VALORES ESTIMADOS PARA PAGAMENTO E/OU DÉBITO PELO IMPORTADOR
- Imposto de Importação (e-DARF - código 0086): {st.session_state.futura_imposto_importacao_display}
- Imposto s/Produtos Industrializados (e-DARF - código 1038): {st.session_state.futura_ipi_display}
- PIS/PASEP na Importação (e-DARF - código 5602): {st.session_state.futura_pis_pasep_display}
- COFINS na Importação (e-DARF - código 5629): {st.session_state.futura_cofins_display}
- Taxa de Utilização do SISCOMEX (e-DARF - código 7811): {st.session_state.futura_taxa_siscomex_display}
- ICMS-SC (se houver): {st.session_state.futura_icms_sc_display}
TOTAL DO DÉBITO (BRL): {total_debito_importador}

VALORES ESTIMADOS PARA DEPÓSITOS E PAGAMENTOS PELA COMISSÁRIA DE DESPACHOS
1 - Assessoria do Processo Logístico Internacional: {st.session_state.futura_assessoria_logistica_display}
"""
    if st.session_state.futura_tipo_transporte == "Marítimo":
        email_body_plaintext += f"""2 - AFRMM - Adicional de Frete p/Renovação da Marinha Mercante: {st.session_state.futura_afrmm_comissaria_display}
3 - Remessa de Documentos para Liberação B/L/HAWB/CRT: {st.session_state.futura_remessa_documentos_display}
"""
    email_body_plaintext += f"""TOTAL DO DÉBITO (BRL): {total_debito_comissaria}

Diferença: {diferenca}

Data da conferência: {data_atual_formatada}

Obrigado,
{usuario_programa}
"""
    email_subject = f"{referencia_processo} - Conferência Futura"
    
    return email_subject, email_body_plaintext

def generate_payment_email_content():
    st.markdown("""
    <style>
        /* Campo de texto normal */
        .stTextInput > div > div > input {
            width: 100% !important;
            min-width: 100% !important;
            max-width: 100% !important;
            box-sizing: border-box !important;
        }
        
        /* Para área de texto também */
        .stTextArea > div > div > textarea {
            width: 100% !important;
            min-width: 100% !important;
            max-width: 100% !important;
            box-sizing: border-box !important;
        }
    </style>
    """, unsafe_allow_html=True)
    """Gera o conteúdo do e-mail para Pagamento de Honorários."""
    di_data = st.session_state.futura_di_data
    referencia_processo = di_data.get('informacao_complementar', 'N/A')
    valor_total = st.session_state.futura_total_debito_comissaria # Usando o total da comissaria para o valor total

    current_hour = datetime.now().hour
    saudacao = "Bom dia" if 9 <= current_hour < 15 else "Boa tarde"
    usuario_programa = st.session_state.get('user_info', {}).get('username', 'usuário do sistema')

    email_body_plaintext = f"""{saudacao} Mayra,

Gentileza realizar depósito para a Futura:
Processo: {referencia_processo}
Valor total: {valor_total}

Serviço: honorários de despacho aduaneiro de importação.

Chave PIX: +55 47 999720387
Favorecido: Futura Despachos Aduaneiros Ltda
Banco: ITAÚ UNIBANCO S/A - 341
Agência: 0154
Conta Corrente: 20907-6
CNPJ: 15.010.021/0001-65

Conforme instruções em anexo.
Obs.: Invoice e DI da importação em anexo.

Obrigado(a),
{usuario_programa}
"""
    email_subject = f"{referencia_processo} - Pagamento de honorários Futura"
    return email_subject, email_body_plaintext

def generate_debit_email_content():
    st.markdown("""
    <style>
        /* Campo de texto normal */
        .stTextInput > div > div > input {
            width: 100% !important;
            min-width: 100% !important;
            max-width: 100% !important;
            box-sizing: border-box !important;
        }
        
        /* Para área de texto também */
        .stTextArea > div > div > textarea {
            width: 100% !important;
            min-width: 100% !important;
            max-width: 100% !important;
            box-sizing: border-box !important;
        }
    </style>
    """, unsafe_allow_html=True)
    """Gera o conteúdo do e-mail para Débito em Conta Impostos."""
    di_data = st.session_state.futura_di_data
    referencia_processo = di_data.get('informacao_complementar', 'N/A')
    total_debito_importador = st.session_state.futura_total_debito_importador

    current_hour = datetime.now().hour
    saudacao = "Bom dia" if 9 <= current_hour < 15 else "Boa tarde"
    usuario_programa = st.session_state.get('user_info', {}).get('username', 'usuário do sistema')

    email_body_plaintext = f"""{saudacao} Mayra,

Aviso de débito em conta de impostos de importação:
Valor total: {total_debito_importador}
Processo: {referencia_processo}

Conforme instruções em anexo.
Obs.: Invoice e DI da importação em anexo.

Obrigado(a),
{usuario_programa}
"""
    email_subject = f"{referencia_processo} - Débito em conta impostos"
    return email_subject, email_body_plaintext
