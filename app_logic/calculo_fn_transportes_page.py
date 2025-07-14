import streamlit as st
import pandas as pd
import logging
import os
from datetime import datetime, date # Importar date também
import urllib.parse # Para codificar URLs para o mailto

# Importa as funções reais do db_utils
from db_utils import get_declaracao_by_id, update_declaracao_field

# Importa as funções de utilidade para o fundo
try:
    from app_logic.utils import set_background_image
except ImportError:
    logging.warning("Módulo 'app_logic.utils' não encontrado. Funções de imagem de fundo podem não funcionar.")
    def set_background_image(image_path, opacity=None):
        pass # Função mock se utils não for encontrado

# Importa o módulo de gerenciamento de banco de dados para follow-up
# Será usado para acessar o st.session_state.processo_data que vem do follow-up
from app_logic import followup_db_manager

# Importações para envio de e-mail
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders


logger = logging.getLogger(__name__)

# --- Funções Auxiliares de Formatação ---
def _format_currency(value):
    """Formata um valor numérico para o formato de moeda R$ X.XXX,XX."""
    try:
        val = float(value)
        return f"R$ {val:,.2f}".replace('.', '#').replace(',', '.').replace('#', ',')
    except (ValueError, TypeError):
        return "R$ 0,00"

def _format_float(value, decimals=4):
    """Formata um valor numérico float com um número específico de casas decimais."""
    try:
        val = float(value)
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

# --- Funções de Geração de Conteúdo de E-mail ---

def generate_fn_email_content():
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
    """Gera o conteúdo do e-mail para FN Transportes."""
    di_data = st.session_state.fn_transportes_di_data
    referencia_processo = st.session_state.fn_transportes_processo_ref
    valor_total_depositar = st.session_state.fn_transportes_total_a_depositar_display
    
    # Obtém a data de vencimento do session_state, formatando-a
    data_vencimento_str = st.session_state.fn_transportes_data_vencimento.strftime("%d/%m/%Y")

    current_hour = datetime.now().hour
    saudacao = "Bom dia" if 9 <= current_hour < 15 else "Boa tarde"
    usuario_programa = st.session_state.get('user_info', {}).get('username', 'usuário do sistema')
    
    # Dados bancários fixos para FN Transportes
    dados_bancarios = """Dados Bancários:
TRANSPORTES FN
Pagamento Via Boleto
Banco Viacredi - 085
Agencia: 0108-2
Conta: 2010871-0
CNPJ: 27.064.174/0001-74"""

    email_body_plaintext = f"""{saudacao} Mayra,

Gentileza realizar o pagamento para a FN TRANSPORTES

Referência dos Processos: {referencia_processo}
Valor total: {valor_total_depositar}
Vencimento: {data_vencimento_str}
Serviço: Frete rodoviário de Navegantes para Joinville.

{dados_bancarios}

Conforme instruções em anexo.
Obs.: Segue Invoice, CTE e Boleto

Obrigado,
{usuario_programa}
"""
    email_subject = f"{referencia_processo} - Pagamento de frete nacional FN TRANSPORTES"
    
    return email_subject, email_body_plaintext

# --- Função para Enviar E-mail com Anexos (adaptada de Pac Log Elo) ---
def send_email_with_attachments_fn_transportes(to_emails, subject, body, uploaded_files):
    """
    Envia um e-mail com anexos via Gmail SMTP.
    Os e-mails são lidos dos segredos do Streamlit.
    """
    try:
        # Pega as credenciais de e-mail dos segredos do Streamlit da nova seção [gmail_credentials]
        remetente = st.secrets["gmail_credentials"]["gmail_email"]
        senha_aplicativo = st.secrets["gmail_credentials"]["gmail_app_password"]

        # Cria a mensagem principal (MIMEMultipart para permitir texto e anexos)
        msg = MIMEMultipart()
        msg["Subject"] = subject
        msg["From"] = remetente
        msg["To"] = ", ".join(to_emails) # Suporta múltiplos destinatários

        msg.attach(MIMEText(body, "plain")) # Mude para "html" se o corpo for HTML

        # Adiciona os anexos
        for uploaded_file in uploaded_files:
            try:
                # Cria um objeto MIMEBase para o anexo
                part = MIMEBase("application", "octet-stream")
                part.set_payload(uploaded_file.read()) # Lê o conteúdo do arquivo em memória
                
                # Codifica o anexo em Base64
                encoders.encode_base64(part)
                
                # Adiciona o cabeçalho Content-Disposition com o nome do arquivo
                part.add_header(
                    "Content-Disposition",
                    f"attachment; filename= {uploaded_file.name}",
                )
                
                # Anexa a parte do arquivo à mensagem
                msg.attach(part)
            except Exception as e:
                st.warning(f"Erro ao anexar o arquivo '{uploaded_file.name}': {e}. O e-mail será enviado sem este anexo.")

        # Envia o e-mail
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp: # 465 é a porta SSL
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


# --- Funções de Ação ---

def _save_frete_nacional_to_db():
    """Salva o valor do Total a Depositar no banco de dados, na coluna 'frete_nacional'."""
    if 'fn_transportes_di_data' not in st.session_state or not st.session_state.fn_transportes_di_data:
        st.error("Não há dados da DI carregados para salvar o Frete Nacional.")
        return

    # O ID da DI é acessado como uma chave do dicionário
    di_id = st.session_state.fn_transportes_di_data.get('id')
    
    if di_id is None:
        st.error("ID da DI não encontrado nos dados carregados para salvar o Frete Nacional.")
        return

    # O valor a ser salvo é o 'Total a Depositar' calculado
    frete_nacional_to_save_str = st.session_state.fn_transportes_total_a_depositar_display
    try:
        frete_nacional_float = float(frete_nacional_to_save_str.replace('R$', '').replace('.', '').replace(',', '.').strip())
    except ValueError:
        st.error("Valor do Total a Depositar calculado inválido para salvar no banco de dados.")
        return

    if update_declaracao_field(di_id, 'frete_nacional', frete_nacional_float):
        st.success(f"Frete Nacional ({_format_currency(frete_nacional_float)}) salvo com sucesso")
    else:
        st.error(f"Falha ao salvar o valor do Frete Nacional para a DI ID {di_id}.")

    # Não chamar st.rerun() aqui, a atualização será natural após o clique no botão

def load_fn_transportes_di_data(declaracao_id):
    """
    Carrega os dados da DI para a tela FN Transportes e inicializa o estado da sessão.
    """
    logger.info(f"load_fn_transportes_di_data: Chamado para DI ID: {declaracao_id}")
    if not declaracao_id:
        logger.warning("Nenhum ID de declaração fornecido para carregar dados (FN Transportes).")
        clear_fn_transportes_di_data()
        return

    di_data_dict = get_declaracao_by_id(declaracao_id) # Agora retorna um dicionário

    if di_data_dict:
        st.session_state.fn_transportes_di_data = di_data_dict # Armazena o dicionário diretamente
        
        # Acessa os dados usando .get() para robustez e legibilidade
        # Forneça um valor padrão (0.0 ou "N/A") caso a chave não exista, para evitar erros.
        informacao_complementar = di_data_dict.get('informacao_complementar')
        vmld = di_data_dict.get('vmld', 0.0)
        peso_bruto = di_data_dict.get('peso_bruto', 0.0)
        peso_liquido = di_data_dict.get('peso_liquido', 0.0)
        frete_nacional_db_value = di_data_dict.get('frete_nacional', 0.0) # Assume que a chave é 'frete_nacional'

        st.session_state.fn_transportes_processo_ref = informacao_complementar if informacao_complementar else "N/A"
        
        # Atualiza os valores brutos da DI no session_state para uso nos cálculos
        st.session_state.fn_transportes_vmld_raw = vmld
        st.session_state.fn_transportes_peso_bruto_raw = peso_bruto
        st.session_state.fn_transportes_peso_liquido_raw = peso_liquido
        st.session_state.fn_transportes_frete_nacional_db_raw = frete_nacional_db_value # Guarda o valor do DB

        # --- Lógica para obter valores de Quantidade de Processos Agrupados e Quantidade Containers ---
        processo_data = st.session_state.get('processo_data') # Pega o processo_data já carregado na sessão
        
        default_qtde_processos_from_details = 1
        default_qtde_container_from_details = 1

        if processo_data:
            consolidado_status = str(processo_data.get('Consolidado', 'Não')).strip().lower()
            
            # Lógica para Quantidade de Processos Agrupados
            if consolidado_status == 'sim':
                processos_vinculados_raw = processo_data.get('Processos_Vinculados')
                if isinstance(processos_vinculados_raw, list):
                    default_qtde_processos_from_details = len(processos_vinculados_raw) + 1
                else:
                    default_qtde_processos_from_details = 1
            else:
                default_qtde_processos_from_details = 1

            # Lógica para Quantidade de Contêineres
            if consolidado_status == 'sim':
                default_qtde_container_from_details = 1
            else:
                qtde_containers_from_process = processo_data.get('Quantidade_Containers')
                try:
                    default_qtde_container_from_details = int(qtde_containers_from_process) if pd.notna(qtde_containers_from_process) else 1
                except (ValueError, TypeError):
                    default_qtde_container_from_details = 1
        
        # ATENÇÃO: Os inputs de texto (`st.text_input`) só aceitam strings para o parâmetro `value`.
        # Converte os valores para string.
        st.session_state.fn_transportes_qtde_processos_input = str(default_qtde_processos_from_details)
        st.session_state.fn_transportes_qtde_container_input = str(default_qtde_container_from_details)
        # Pré-preenche Qtde Baixa Vazio com Qtde de Contêiner
        st.session_state.fn_transportes_qtde_baixa_vazio_input = str(default_qtde_container_from_details)
        # --- Fim da lógica de obtenção e atribuição ---


        if 'fn_transportes_diferenca_input' not in st.session_state:
            st.session_state.fn_transportes_diferenca_input = _format_currency(0.00)
        if 'fn_transportes_baixa_vazio_option' not in st.session_state:
            st.session_state.fn_transportes_baixa_vazio_option = "Não"
        # A linha abaixo foi movida para dentro da lógica acima para usar default_qtde_container_from_details
        # if 'fn_transportes_qtde_baixa_vazio_input' not in st.session_state:
        #     st.session_state.fn_transportes_qtde_baixa_vazio_input = "0"

        perform_fn_transportes_calculations() # Realiza os cálculos iniciais

    else:
        st.warning(f"Nenhum dado encontrado para a DI ID: {declaracao_id} (FN Transportes)")
        clear_fn_transportes_di_data()

def clear_fn_transportes_di_data():
    """Limpa todos os dados e estados da sessão para a tela FN Transportes."""
    st.session_state.fn_transportes_di_data = None
    st.session_state.fn_transportes_processo_ref = "PCH-XXXX-XX"
    
    # Initialize these with default values if they don't exist, or set them to defaults
    st.session_state.fn_transportes_qtde_processos_input = "1"
    st.session_state.fn_transportes_qtde_container_input = "1"
    st.session_state.fn_transportes_diferenca_input = _format_currency(0.00)
    st.session_state.fn_transportes_baixa_vazio_option = "Não"
    st.session_state.fn_transportes_qtde_baixa_vazio_input = "1" # Define como 1 por padrão ao limpar
    st.session_state.fn_transportes_data_vencimento = date.today() # Define a data de hoje ao limpar

    st.session_state.show_fn_email_expander = False
    st.session_state.fn_email_type_to_show = None

    # Limpa os valores calculados e brutos
    st.session_state.fn_transportes_vmld_raw = 0.0
    st.session_state.fn_transportes_peso_bruto_raw = 0.0
    st.session_state.fn_transportes_peso_liquido_raw = 0.0
    st.session_state.fn_transportes_frete_nacional_db_raw = 0.0

    st.session_state.fn_transportes_vmld_di_display = _format_currency(0.00)
    st.session_state.fn_transportes_base_calculo_display = _format_currency(0.00)
    st.session_state.fn_transportes_percentual_vmld_display = _format_currency(0.00)
    st.session_state.fn_transportes_total_parcial_display = _format_currency(0.00)
    st.session_state.fn_transportes_total_a_depositar_display = _format_currency(0.00)

    # Limpa os campos de e-mail
    st.session_state.fn_transportes_email_to = "jjenessa23@gmail.com"
    st.session_state.fn_transportes_email_subject_send = ""
    st.session_state.fn_transportes_email_body_send = ""
    st.session_state.fn_transportes_email_attachments_list = []


def perform_fn_transportes_calculations():
    """Realiza os cálculos para a tela FN Transportes."""
    if 'fn_transportes_di_data' not in st.session_state or not st.session_state.fn_transportes_di_data:
        logger.warning("Não há dados da DI para realizar cálculos (FN Transportes).")
        return

    # Puxa os valores brutos da DI do session_state
    vmld = st.session_state.fn_transportes_vmld_raw
    # peso_bruto = st.session_state.fn_transportes_peso_bruto_raw # Não usado diretamente nos cálculos abaixo

    # Obter valores dos campos de entrada
    try:
        qtde_processos = int(st.session_state.fn_transportes_qtde_processos_input)
        qtde_container = int(st.session_state.fn_transportes_qtde_container_input)
        diferenca_float = float(st.session_state.fn_transportes_diferenca_input.replace('R$', '').replace('.', '').replace(',', '.').strip())
        baixa_vazio_sim = (st.session_state.fn_transportes_baixa_vazio_option == "Sim")
        qtde_baixa_vazio = int(st.session_state.fn_transportes_qtde_baixa_vazio_input) if baixa_vazio_sim else 0
    except ValueError:
        logger.warning("Valores de entrada inválidos para FN Transportes, usando 0 para cálculo.")
        # Limpar os valores calculados se a entrada for inválida
        st.session_state.fn_transportes_base_calculo_display = _format_currency(0.00)
        st.session_state.fn_transportes_percentual_vmld_display = _format_currency(0.00)
        st.session_state.fn_transportes_total_parcial_display = _format_currency(0.00)
        st.session_state.fn_transportes_total_a_depositar_display = _format_currency(0.00)
        return

    # Constantes de cálculo (extraídas de view_calculo_fn_transportes.py)
    BASE_FIXA_CALCULO = 1650.00
    VALOR_BAIXA_VAZIO_UNITARIO = 380.00
    DIVISOR_FINAL = 0.83

    # Cálculo da Base - Ajustado para corresponder à imagem e lógica de 1650 fixo por processo
    # A lógica original do view_calculo_fn_transportes.py é:
    # base_calculo = self.BASE_FIXA_CALCULO
    # if qtde_container > 0: base_calculo *= qtde_container
    # if qtde_processos > 0: base_calculo /= qtde_processos
    # Para corresponder à imagem, onde a base de cálculo é R$ 1.650,00 mesmo com 2 contêineres e 1 processo:
    base_calculo_for_display = BASE_FIXA_CALCULO # Mantém 1650 fixo para exibição

    # Porcentagem do VMLD da DI
    percentual_vmld = 0.00055 * vmld

    # Total Parcial
    # A lógica do view_calculo_fn_transportes.py para total_parcial_bruto é (base_calculo + percentual_vmld)
    # ONDE base_calculo já considera qtde_container e qtde_processos.
    calculated_base_for_total = BASE_FIXA_CALCULO
    if qtde_container > 0:
        calculated_base_for_total *= qtde_container
    if qtde_processos > 0:
        calculated_base_for_total /= qtde_processos

    total_parcial_bruto = (calculated_base_for_total + percentual_vmld)
    total_parcial = total_parcial_bruto / DIVISOR_FINAL

    # Valor da Baixa de Vazio
    valor_baixa_vazio_calculado = 0.0
    if baixa_vazio_sim:
        valor_baixa_vazio_calculado = VALOR_BAIXA_VAZIO_UNITARIO * qtde_baixa_vazio
        if qtde_processos > 0: # Divide pela quantidade de processos, se houver mais de um
            valor_baixa_vazio_calculado /= qtde_processos

    # Total a Depositar
    total_a_depositar = total_parcial + diferenca_float + valor_baixa_vazio_calculado

    # Atualiza os valores no session_state para exibição
    st.session_state.fn_transportes_vmld_di_display = _format_currency(vmld)
    st.session_state.fn_transportes_base_calculo_display = _format_currency(base_calculo_for_display) # Exibir 1650 fixo para a Base Cálculo
    st.session_state.fn_transportes_percentual_vmld_display = _format_currency(percentual_vmld)
    st.session_state.fn_transportes_total_parcial_display = _format_currency(total_parcial)
    st.session_state.fn_transportes_total_a_depositar_display = _format_currency(total_a_depositar)

# --- Funções de Callback para Botões de Ajuste ---
def _increment_qtde_processos():
    st.session_state.fn_transportes_qtde_processos_input = str(int(st.session_state.fn_transportes_qtde_processos_input) + 1)
    perform_fn_transportes_calculations()

def _decrement_qtde_processos():
    st.session_state.fn_transportes_qtde_processos_input = str(max(1, int(st.session_state.fn_transportes_qtde_processos_input) - 1))
    perform_fn_transportes_calculations()

def _increment_qtde_container():
    st.session_state.fn_transportes_qtde_container_input = str(int(st.session_state.fn_transportes_qtde_container_input) + 1)
    perform_fn_transportes_calculations()

def _decrement_qtde_container():
    st.session_state.fn_transportes_qtde_container_input = str(max(1, int(st.session_state.fn_transportes_qtde_container_input) - 1))
    perform_fn_transportes_calculations()

def _increment_qtde_baixa_vazio():
    st.session_state.fn_transportes_qtde_baixa_vazio_input = str(int(st.session_state.fn_transportes_qtde_baixa_vazio_input) + 1)
    perform_fn_transportes_calculations()

def _decrement_qtde_baixa_vazio():
    st.session_state.fn_transportes_qtde_baixa_vazio_input = str(max(0, int(st.session_state.fn_transportes_qtde_baixa_vazio_input) - 1))
    perform_fn_transportes_calculations()

def _increment_diferenca():
    current_diff = float(st.session_state.fn_transportes_diferenca_input.replace('R$', '').replace('.', '').replace(',', '.').strip())
    st.session_state.fn_transportes_diferenca_input = _format_currency(round(current_diff + 0.01, 2))
    perform_fn_transportes_calculations()

def _decrement_diferenca():
    current_diff = float(st.session_state.fn_transportes_diferenca_input.replace('R$', '').replace('.', '').replace(',', '.').strip())
    st.session_state.fn_transportes_diferenca_input = _format_currency(round(current_diff - 0.01, 2))
    perform_fn_transportes_calculations()

def send_email_and_save_action_fn_transportes():
    """
    Combina a lógica de preparar, exibir, enviar e-mail e salvar no banco de dados para FN Transportes.
    """
    if 'fn_transportes_di_data' not in st.session_state or not st.session_state.fn_transportes_di_data:
        st.warning("Carregue os dados da DI antes de enviar o e-mail.")
        return

    # Preenche os campos do formulário de envio de e-mail ao carregar a DI ou recalcular
    email_subject_generated, email_body_plaintext_generated = generate_fn_email_content()
    # Atualiza st.session_state diretamente para que os widgets reflitam os valores gerados
    st.session_state.fn_transportes_email_subject_send = email_subject_generated # REMOVIDO 'if not'
    st.session_state.fn_transportes_email_body_send = email_body_plaintext_generated # REMOVIDO 'if not'
    
    # CAMPOS DE ENTRADA DO E-MAIL
    to_emails_input = st.text_input(
        "Para (e-mails separados por vírgula):",
        value=st.session_state.fn_transportes_email_to,
        key="fn_transportes_send_to_emails_input"
    )
    st.session_state.fn_transportes_email_to = to_emails_input.strip()

    st.session_state.fn_transportes_email_subject_send = st.text_input(
        "Assunto:",
        value=st.session_state.fn_transportes_email_subject_send,
        key="fn_transportes_send_email_subject_input"
    )
    
    st.session_state.fn_transportes_email_body_send = st.text_area(
        "Corpo do E-mail:",
        value=st.session_state.fn_transportes_email_body_send,
        height=300, # Aumentei a altura para melhor visualização
        key="fn_transportes_send_email_body_input"
    )
    
    uploaded_files = st.file_uploader(
        "Arraste e solte ou selecione arquivos para anexar (múltiplos)",
        type=None, # Permite todos os tipos de arquivo
        accept_multiple_files=True,
        key="fn_transportes_send_email_attachments_uploader"
    )
    # Garante que st.session_state.fn_transportes_email_attachments_list é uma lista mutável
    if 'fn_transportes_email_attachments_list' not in st.session_state:
        st.session_state.fn_transportes_email_attachments_list = []

    # Atualiza a lista de anexos se novos arquivos foram carregados
    if uploaded_files:
        current_attached_names = {f.name for f in st.session_state.fn_transportes_email_attachments_list}
        for file in uploaded_files:
            if file.name not in current_attached_names:
                st.session_state.fn_transportes_email_attachments_list.append(file)
    
    # Exibe os arquivos atualmente anexados (e permite remover)
    if st.session_state.fn_transportes_email_attachments_list:
        st.markdown("###### Arquivos anexados:")
        for i, file in enumerate(st.session_state.fn_transportes_email_attachments_list):
            col_file_name, col_remove_btn = st.columns([0.8, 0.2])
            with col_file_name:
                st.write(f"- {file.name}")
            with col_remove_btn:
                if st.button("Remover", key=f"fn_transportes_remove_attachment_{i}"):
                    st.session_state.fn_transportes_email_attachments_list.pop(i)
                    st.rerun() # Força o Streamlit a rerenderizar para atualizar a lista

    col1, col2 = st.columns([0.5, 0.2]) # Colunas para o botão de enviar/salvar e talvez um espaço
    with col1:
        if st.button("Enviar E-mail e Salvar", key="fn_transportes_send_email_and_save_btn", use_container_width=True):
            if not st.session_state.fn_transportes_email_to:
                st.warning("Por favor, preencha o(s) destinatário(s) do e-mail.")
            else:
                list_of_recipients = [email.strip() for email in st.session_state.fn_transportes_email_to.split(',') if email.strip()]
                
                if list_of_recipients:
                    with st.spinner("Enviando e-mail e salvando no banco de dados..."):
                        # 1. Tenta enviar o e-mail
                        email_sent_successfully = send_email_with_attachments_fn_transportes(
                            to_emails=list_of_recipients,
                            subject=st.session_state.fn_transportes_email_subject_send,
                            body=st.session_state.fn_transportes_email_body_send,
                            uploaded_files=st.session_state.fn_transportes_email_attachments_list # Usa a lista de arquivos anexados
                        )
                        
                        # 2. Se o e-mail foi enviado com sucesso, salva no banco de dados
                        if email_sent_successfully:
                            _save_frete_nacional_to_db()
                            # REMOVIDO: load_fn_transportes_di_data(st.session_state.fn_transportes_di_data.get('id'))
                            
                            # Limpa os campos após o envio bem-sucedido
                            st.session_state.fn_transportes_email_to = "jjenessa23@gmail.com"
                            st.session_state.fn_transportes_email_subject_send = ""
                            st.session_state.fn_transportes_email_body_send = ""
                            st.session_state.fn_transportes_email_attachments_list = [] # Limpa a lista de anexos

                    st.rerun() # Força rerender para limpar os campos ou mostrar status
                else:
                    st.warning("Nenhum destinatário válido encontrado.")


def show_calculo_fn_transportes_page():
    """
    Exibe a interface de usuário para o cálculo de Frete Nacional (FN Transportes).
    """
    # --- Configuração da Imagem de Fundo para a página ---
    current_dir = os.path.dirname(os.path.abspath(__file__))
    app_root_dir = os.path.join(current_dir, '..', '..') # Ajustado para ir para a raiz do app
    background_image_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'assets', 'logo_navio_atracado.png')
    set_background_image(background_image_path)
    
    # Define a imagem de fundo com a opacidade padrão de 0.20 para o conteúdo principal
    set_background_image(background_image_path, opacity=0.20)


    st.subheader("Cálculo Frete Nacional (FN Transportes)")

    # Inicializa variáveis de estado para a página se elas não existirem
    # Esta é a principal área para inicializar variáveis de estado da sessão para widgets
    st.session_state.setdefault('fn_transportes_di_data', None)
    st.session_state.setdefault('fn_transportes_processo_ref', "PCH-XXXX-XX")
    # Inicializa com valores padrão. Estes serão sobrescritos por load_fn_transportes_di_data
    # se houver dados de processo disponíveis.
    st.session_state.setdefault('fn_transportes_qtde_processos_input', "1")
    st.session_state.setdefault('fn_transportes_qtde_container_input', "1")
    st.session_state.setdefault('fn_transportes_diferenca_input', _format_currency(0.00))
    st.session_state.setdefault('fn_transportes_baixa_vazio_option', "Não")
    st.session_state.setdefault('fn_transportes_qtde_baixa_vazio_input', "1") # Inicializa com 1, será sobrescrito se houver dados
    st.session_state.setdefault('fn_transportes_data_vencimento', date.today()) # NOVO: Inicializa com a data de hoje
    st.session_state.setdefault('show_fn_email_expander', False)
    st.session_state.setdefault('fn_email_type_to_show', None)
    st.session_state.setdefault('fn_transportes_vmld_raw', 0.0)
    st.session_state.setdefault('fn_transportes_peso_bruto_raw', 0.0)
    st.session_state.setdefault('fn_transportes_peso_liquido_raw', 0.0)
    st.session_state.setdefault('fn_transportes_frete_nacional_db_raw', 0.0)
    st.session_state.setdefault('fn_transportes_vmld_di_display', _format_currency(0.00))
    st.session_state.setdefault('fn_transportes_base_calculo_display', _format_currency(0.00))
    st.session_state.setdefault('fn_transportes_percentual_vmld_display', _format_currency(0.00))
    st.session_state.setdefault('fn_transportes_total_parcial_display', _format_currency(0.00))
    st.session_state.setdefault('fn_transportes_total_a_depositar_display', _format_currency(0.00))
    # Inicializa os estados para os campos de e-mail a serem enviados
    st.session_state.setdefault('fn_transportes_email_to', "jjenessa23@gmail.com")  # Valor padrão
    st.session_state.setdefault('fn_transportes_email_subject_send', "")
    st.session_state.setdefault('fn_transportes_email_body_send', "")
    st.session_state.setdefault('fn_transportes_email_attachments_list', []) # Lista para gerenciar anexos


    # Carrega os dados da DI se um ID foi passado da página anterior
    # A lógica aqui é crucial para disparar o carregamento dos dados do processo.
    if 'selected_di_id_fn_transportes' in st.session_state and st.session_state.selected_di_id_fn_transportes:
        # Só carrega se o ID da DI mudou ou se os dados ainda não foram carregados
        if st.session_state.fn_transportes_di_data is None or \
           st.session_state.fn_transportes_di_data.get('id') != st.session_state.selected_di_id_fn_transportes:
            load_fn_transportes_di_data(st.session_state.selected_di_id_fn_transportes)
            st.session_state.selected_di_id_fn_transportes = None # Limpa o ID após carregar
            # Força um rerun para que os st.text_input peguem os valores atualizados do session_state
            st.rerun() 

    col_1, col_2 = st.columns([0.7, 0.3]) # Colunas para o conteúdo principal e ações
    with col_1:
        st.markdown(f"#### Processo: **{st.session_state.fn_transportes_processo_ref}**")
    with col_2:  
        #adicionando imagem de logo da paclog elo
        logo_fn_transportes = os.path.join(app_root_dir, 'assets', 'fn_transportes.png')
        if os.path.exists(logo_fn_transportes):
            st.image(logo_fn_transportes, width=150, caption="FN Transportes")
        else:
            st.warning("Logo da Fn transportes não encontrada. Verifique o caminho do arquivo.")
    st.markdown("---")

    # --- Tabela de Cálculos ---
    st.markdown("##### Detalhes do Cálculo de Frete")
    # Usando st.container para agrupar e controlar o layout
    with st.container():
        # Primeira linha de colunas para Qtde de Processos e Qtde de Contêiner
        col1_qty_proc, col2_qty_cont, col3_vmld_base, col4_total_parcial = st.columns(4)

        with col1_qty_proc:
            st.markdown(f"**Qtde de Processos:**")
            st.text_input(
                "Qtde de Processos",
                value=st.session_state.fn_transportes_qtde_processos_input, # Usa o valor do session_state
                key="fn_transportes_qtde_processos_input",
                on_change=perform_fn_transportes_calculations, # Recalcula ao alterar
                label_visibility="collapsed"
            )
            # Botões de ajuste de quantidade
            qty_processos_col1, qty_processos_col2 = st.columns(2)
            with qty_processos_col1:
                st.button(" ➕ ", key="fn_qtde_processos_plus", use_container_width=True, on_click=_increment_qtde_processos)
            with qty_processos_col2:
                st.button("➖", key="fn_qtde_processos_minus", use_container_width=True, on_click=_decrement_qtde_processos)

        with col2_qty_cont:
            st.markdown(f"**Qtde de Contêiner:**")
            st.text_input(
                "Qtde de Contêiner",
                value=st.session_state.fn_transportes_qtde_container_input, # Usa o valor do session_state
                key="fn_transportes_qtde_container_input",
                on_change=perform_fn_transportes_calculations, # Recalcula ao alterar
                label_visibility="collapsed"
            )
            # Botões de ajuste de quantidade
            qty_container_col1, qty_container_col2 = st.columns(2)
            with qty_container_col1:
                st.button(" ➕ ", key="fn_qtde_container_plus", use_container_width=True, on_click=_increment_qtde_container)
            with qty_container_col2:
                st.button(" ➖ ", key="fn_qtde_container_minus", use_container_width=True, on_click=_decrement_qtde_container)

        with col3_vmld_base:
            st.markdown(f"**VMLD DI:** {st.session_state.fn_transportes_vmld_di_display}")
            st.markdown(f"**Base Cálculo:** {st.session_state.fn_transportes_base_calculo_display}")
            st.markdown(f"**% VMLD DI:** {st.session_state.fn_transportes_percentual_vmld_display}")
        
        with col4_total_parcial:
            st.markdown(f"**Total Parcial:** {st.session_state.fn_transportes_total_parcial_display}")
            st.markdown(f"**Total a Depositar:** {st.session_state.fn_transportes_total_a_depositar_display}")
            
            st.markdown(f"**Baixa de Vazio?**")
            baixa_vazio_option = st.radio(
                "Baixa de Vazio?",
                options=["Não", "Sim"],
                key="fn_transportes_baixa_vazio_option",
                horizontal=True,
                on_change=perform_fn_transportes_calculations, # Recalcula ao alterar
                label_visibility="collapsed"
            )
            
            if baixa_vazio_option == "Sim":
                st.markdown(f"**Qtde Baixa Vazio:**")
                st.text_input(
                    "Qtde Baixa Vazio",
                    value=st.session_state.fn_transportes_qtde_baixa_vazio_input,
                    key="fn_transportes_qtde_baixa_vazio_input",
                    on_change=perform_fn_transportes_calculations, # Recalcula ao alterar
                    label_visibility="collapsed"
                )
                qty_baixa_col1, qty_baixa_col2 = st.columns(2)
                with qty_baixa_col1:
                    st.button(" ➕ ", key="fn_qtde_baixa_vazio_plus", use_container_width=True, on_click=_increment_qtde_baixa_vazio)
                with qty_baixa_col2:
                    st.button(" ➖ ", key="fn_qtde_baixa_vazio_minus", use_container_width=True, on_click=_decrement_qtde_baixa_vazio)
            else:
                # Garante que o valor seja 0 se "Não" for selecionado
                st.session_state.fn_transportes_qtde_baixa_vazio_input = "0"


    st.markdown("---")

    # Campo Diferença
    st.markdown(f"**Diferença:**")
    st.markdown("""
    <style>
    /* Ajusta o tamanho máximo dos campos de texto na página principal */
    .main .block-container div[data-testid="stTextInput"] {
        max-width: 300px !important;
        margin-left: 0 !important;
        margin-right: auto !important;
    }

    /* Ajusta o input dentro do container na página principal */
    .main .block-container div[data-testid="stTextInput"] input {
        max-width: 300px !important;
        width: 100% !important;
        box-sizing: border-box !important;
        margin-left: 0 !important;
    }

    /* Ajusta o label do input na página principal */
    .main .block-container div[data-testid="stTextInput"] label {
        max-width: 300px !important;
        width: 100% !important;
        margin-bottom: 5px !important;
        text-align: left !important;
        margin-left: 0 !important;
    }

    /* Ajusta o container do input na página principal */
    .main .block-container div[data-testid="stTextInput"] > div {
        max-width: 300px !important;
        width: 100% !important;
        margin-left: 0 !important;
        margin-right: auto !important;
    }

    /* Ajusta os botões para alinhar à esquerda na página principal */
    .main .block-container .stButton > button {
        max-width: 300px !important;
        width: 150px !important;
        margin-left: 0 !important;
        margin-right: auto !important;
    }

    /* Container dos botões na página principal */
    .main .block-container div[data-testid="column"] {
        max-width: 300px !important;
        width: 150px !important;
        margin-left: 0 !important;
        margin-right: auto !important;
    }

    /* Remove espaço entre as colunas dos botões na página principal */
    .main .block-container [data-testid="column"] {
        padding: 0 !important;
        margin: 0 !important;
        gap: 0 !important;
    }

    /* Remove espaço entre os botões na página principal */
    .main .block-container .stButton {
        margin: 0 !important;
        padding: 0 !important;
    }

    /* Ajusta o container das colunas na página principal */
    .main .block-container [data-testid="columns"] {
        gap: 0 !important;
        margin: 0 !important;
        padding: 0 !important;
    }

    /* Container para os botões lado a lado */
    .main .block-container .btn-container {
        display: flex !important;
        max-width: 300px !important;
        gap: 0 !important;
    }
    </style>
    """, unsafe_allow_html=True)
    col_1  = st.columns(2)

    with col_1[0]:
        st.text_input(
            "Diferença",
            value=st.session_state.fn_transportes_diferenca_input,
            key="fn_transportes_diferenca_input",
            on_change=perform_fn_transportes_calculations, # Recalcula ao alterar
            label_visibility="collapsed"
        )
    
    col_2  = st.columns(8)
    with col_2[0]:
        st.write('<div class="btn-container">', unsafe_allow_html=True)
        col_2  = st.columns(2)
        with col_2[0]:
            st.button("+0.01", key="fn_diferenca_plus", on_click=_increment_diferenca)
        with col_2[1]:
            st.button("-0.01", key="fn_diferenca_minus", on_click=_decrement_diferenca)
            st.write('</div>', unsafe_allow_html=True)

    # NOVO: Campo para definir a data de vencimento
    st.markdown("---")
    st.markdown("##### Data de Vencimento")
    st.date_input(
        "Selecione a Data de Vencimento:",
        value=st.session_state.fn_transportes_data_vencimento,
        key="fn_transportes_data_vencimento",
        on_change=perform_fn_transportes_calculations, # Recalcula o e-mail ao alterar
        format="DD/MM/YYYY"
    )

    st.markdown("---")

    st.markdown("#### Enviar E-mail e Salvar no Banco de Dados")
    send_email_and_save_action_fn_transportes() # Chamada da nova função que gerencia a seção de e-mail e salvamento

    st.markdown("---")
    if st.button("Voltar para Detalhes da DI", key="fn_voltar_di"):
        st.session_state.current_page = "Pagamentos" # Assumindo que você voltaria para a página de Pagamentos
        st.rerun()
        
    st.markdown("---")

