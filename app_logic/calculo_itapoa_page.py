import os
from time import sleep
import streamlit as st
import pandas as pd
from datetime import datetime
import logging
import urllib.parse # Para codificar URLs de e-mail

# Importa as funções de utilidade para o fundo
try:
    from app_logic.utils import set_background_image, set_sidebar_background_image
except ImportError:
    logging.warning("Módulo 'app_logic.utils' não encontrado. Funções de imagem de fundo podem não funcionar.")
    def set_background_image(image_path, opacity=None):
        pass # Função mock se utils não for encontrado
    def set_sidebar_background_image(image_path, opacity=None):
        pass # Função mock se utils não for encontrado

# Importa as funções reais do db_utils
# ADIÇÃO: Importa get_declaracao_by_id e update_declaracao
from db_utils import get_declaracao_by_id, update_declaracao_field, update_declaracao

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

# Constantes da Tabela Itapoá (baseado na imagem fornecida para a lógica de armazenagem)
TABELA_ITAPOA = {
    "1": {"percent": 0.00656, "dias_min_total": 1, "dias_max_total": 5, "minimo": 1197.00}, # 0,656% sobre CIF, min 1197.00 (até 6 dias)
    "2": {"percent": 0.00348, "dias_min_total": 6, "dias_max_total": 10, "minimo": 264.00}, # 0,348% ao dia, min 264.00 (para dias 6-10)
    "3": {"percent": 0.00440, "dias_min_total": 11, "dias_max_total": 29, "minimo": 372.00}, # 0,440% ao dia, min 372.00 (para dias 11-29)
    "4": {"percent": 0.00473, "dias_min_total": 30, "dias_max_total": float('inf'), "minimo": 479.00} # 0,473% ao dia, min 479.00 (para dias 30 em diante)
}
LEVANTE_FIXO = 424.00
PESAGEM_FIXA = 105.00

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
        return float(text.replace('R$', '').replace('.', '').replace(',', '.').strip())
    except (ValueError, TypeError):
        return 0.0

# --- Lógica de Cálculo (Adaptada do Tkinter) ---
def perform_calculations():
    """
    Realiza os cálculos para a tela Itapoá e armazena os resultados no session_state.
    Esta função é chamada sempre que um valor de entrada muda.
    """
    logger.info(f"perform_calculations: Iniciado. Current itapoa_di_data: {st.session_state.get('itapoa_di_data', 'None')}")

    if 'itapoa_di_data' not in st.session_state or not st.session_state.itapoa_di_data:
        st.session_state.itapoa_calculated_data = {
            'vmld_di': 0.0,
            'armazenagem': 0.0,
            'levante': 0.0,
            'pesagem': 0.0,
            'total_a_depositar': 0.0
        }
        logger.info("perform_calculations: No DI data found, setting calculated data to 0.")
        return

    di_data = st.session_state.itapoa_di_data

    # Obter valores editáveis do session_state
    try:
        # Garantir que os valores são numéricos
        qtde_processos = int(st.session_state.itapoa_qtde_processos)
        qtde_container = int(st.session_state.itapoa_qtde_container)
        periodo_selecionado = int(st.session_state.itapoa_periodo)
        dias_no_periodo = int(st.session_state.itapoa_dias)
        diferenca = float(st.session_state.itapoa_diferenca) # Já é float, mas garantir
        taxas_extras = float(st.session_state.itapoa_taxas_extras) # Já é float, mas garantir
        logger.info(f"perform_calculations: Inputs read - Processos: {qtde_processos}, Containers: {qtde_container}, Periodo: {periodo_selecionado}, Dias: {dias_no_periodo}")
    except ValueError as e:
        logging.warning(f"perform_calculations: Valores de entrada inválidos para Itapoá, usando 0 para cálculo. Error: {e}")
        st.session_state.itapoa_calculated_data = {
            'vmld_di': 0.0,
            'armazenagem': 0.0,
            'levante': 0.0,
            'pesagem': 0.0,
            'total_a_depositar': 0.0
        }
        return

    # Desempacota os dados da DI
    vmld_di_original = di_data['vmld'] if 'vmld' in di_data and di_data['vmld'] is not None else 0.0
    logger.info(f"perform_calculations: VMLD DI original: {vmld_di_original}")

    # --- Cálculo do Dia Total para a Armazenagem ---
    dia_total_para_calculo = 0
    if periodo_selecionado == 1:
        dia_total_para_calculo = dias_no_periodo
    elif periodo_selecionado == 2:
        dia_total_para_calculo = TABELA_ITAPOA["1"]["dias_max_total"] + dias_no_periodo
    elif periodo_selecionado == 3:
        dia_total_para_calculo = TABELA_ITAPOA["2"]["dias_max_total"] + dias_no_periodo
    elif periodo_selecionado == 4:
        dia_total_para_calculo = TABELA_ITAPOA["3"]["dias_max_total"] + dias_no_periodo

    if str(periodo_selecionado) in TABELA_ITAPOA and TABELA_ITAPOA[str(periodo_selecionado)]["dias_max_total"] != float('inf'):
        dia_total_para_calculo = min(dia_total_para_calculo, TABELA_ITAPOA[str(periodo_selecionado)]["dias_max_total"])
    logger.info(f"perform_calculations: Dia total para cálculo: {dia_total_para_calculo}")

    # --- Cálculo de Armazenagem por Contêiner (Lógica Ajustada) ---
    total_armazenagem_todos_containers = 0.0
    
    vmld_por_container = vmld_di_original / qtde_container if qtde_container > 0 else 0.0
    logger.info(f"perform_calculations: VMLD por container: {vmld_por_container}")

    for i in range(qtde_container): # Use 'i' to indicate iteration
        armazenagem_container = 0.0
        
        if dia_total_para_calculo <= 0:
            armazenagem_container = 0.0
        else:
            current_total_days_processed = 0
            
            # Período 1 (dias 1 a 6)
            if dia_total_para_calculo >= TABELA_ITAPOA["1"]["dias_min_total"]:
                val_periodo1_base_raw = vmld_por_container * TABELA_ITAPOA["1"]["percent"]
                val_periodo1_base = val_periodo1_base_raw
                if qtde_processos <= 1 and val_periodo1_base < TABELA_ITAPOA["1"]["minimo"]:
                    val_periodo1_base = TABELA_ITAPOA["1"]["minimo"]

                if dia_total_para_calculo <= TABELA_ITAPOA["1"]["dias_max_total"]:
                    armazenagem_container = val_periodo1_base
                else:
                    armazenagem_container = val_periodo1_base
                    current_total_days_processed = TABELA_ITAPOA["1"]["dias_max_total"]

                    # Acumula para Período 2 (dias 7 a 14)
                    if dia_total_para_calculo > current_total_days_processed and dia_total_para_calculo >= TABELA_ITAPOA["2"]["dias_min_total"]:
                        days_in_p2_segment = min(dia_total_para_calculo, TABELA_ITAPOA["2"]["dias_max_total"]) - current_total_days_processed
                        if days_in_p2_segment > 0:
                            val_diario_p2_raw = vmld_por_container * TABELA_ITAPOA["2"]["percent"]
                            val_diario_p2 = val_diario_p2_raw
                            if qtde_processos <= 1 and val_diario_p2 < TABELA_ITAPOA["2"]["minimo"]:
                                val_diario_p2 = TABELA_ITAPOA["2"]["minimo"]
                            armazenagem_container += val_diario_p2 * days_in_p2_segment
                        current_total_days_processed = TABELA_ITAPOA["2"]["dias_max_total"]

                    # Acumula para Período 3 (dias 15 a 29)
                    if dia_total_para_calculo > current_total_days_processed and dia_total_para_calculo >= TABELA_ITAPOA["3"]["dias_min_total"]:
                        days_in_p3_segment = min(dia_total_para_calculo, TABELA_ITAPOA["3"]["dias_max_total"]) - current_total_days_processed
                        if days_in_p3_segment > 0:
                            val_diario_p3_raw = vmld_por_container * TABELA_ITAPOA["3"]["percent"]
                            val_diario_p3 = val_diario_p3_raw
                            if qtde_processos <= 1 and val_diario_p3 < TABELA_ITAPOA["3"]["minimo"]:
                                val_diario_p3 = TABELA_ITAPOA["3"]["minimo"]
                            armazenagem_container += val_diario_p3 * days_in_p3_segment
                        current_total_days_processed = TABELA_ITAPOA["3"]["dias_max_total"]

                    # Acumula para Período 4 (dias 30 em diante)
                    if dia_total_para_calculo > current_total_days_processed and dia_total_para_calculo >= TABELA_ITAPOA["4"]["dias_min_total"]:
                        days_in_p4_segment = dia_total_para_calculo - current_total_days_processed
                        if days_in_p4_segment > 0:
                            val_diario_p4_raw = vmld_por_container * TABELA_ITAPOA["4"]["percent"]
                            val_diario_p4 = val_diario_p4_raw
                            if qtde_processos <= 1 and val_diario_p4 < TABELA_ITAPOA["4"]["minimo"]:
                                val_diario_p4 = TABELA_ITAPOA["4"]["minimo"]
                            armazenagem_container += val_diario_p4 * days_in_p4_segment
        
        total_armazenagem_todos_containers += armazenagem_container
    logger.info(f"perform_calculations: Total armazenagem todos containers: {total_armazenagem_todos_containers}")

    # --- Cálculo de Levante e Pesagem ---
    base_levante = LEVANTE_FIXO
    base_pesagem = PESAGEM_FIXA

    levante_final = base_levante * qtde_container
    pesagem_final = base_pesagem * qtde_container

    if qtde_processos > 1:
        levante_final = levante_final / qtde_processos
        pesagem_final = pesagem_final / qtde_processos
    else:
        levante_final = max(levante_final, LEVANTE_FIXO)
        pesagem_final = max(pesagem_final, PESAGEM_FIXA)
    logger.info(f"perform_calculations: Levante final: {levante_final}, Pesagem final: {pesagem_final}")


    # --- Total a Depositar ---
    total_a_depositar = total_armazenagem_todos_containers + levante_final + pesagem_final + diferenca + taxas_extras
    logger.info(f"perform_calculations: Total a depositar: {total_a_depositar}")


    # Armazena os resultados no session_state
    st.session_state.itapoa_calculated_data = {
        'vmld_di': vmld_di_original,
        'armazenagem': total_armazenagem_todos_containers,
        'levante': levante_final,
        'pesagem': pesagem_final,
        'total_a_depositar': total_a_depositar
    }
    logger.info("perform_calculations: Cálculo concluído e dados armazenados no session_state.")

# --- Funções de Ação ---
def load_di_data_for_itapoa(declaracao_id):
    """
    Carrega os dados da DI selecionada do banco de dados e inicializa
    os campos de entrada e dados calculados no session_state.
    """
    logger.info(f"load_di_data_for_itapoa: Chamado para DI ID: {declaracao_id}")
    di_data_raw = get_declaracao_by_id(declaracao_id)
    if di_data_raw:
        di_data = dict(di_data_raw)
        st.session_state.itapoa_di_data = di_data
        st.session_state.itapoa_declaracao_id = declaracao_id
        logger.info(f"load_di_data_for_itapoa: DI data loaded: {di_data.get('numero_di')}, Ref: {di_data.get('informacao_complementar')}")


        # NOVO: Carregar dados do processo para obter a quantidade de agrupados e containers
        # Certifique-se de que st.session_state.processo_data foi definido pela tela anterior
        processo_data = st.session_state.get('processo_data') 
        logger.info(f"load_di_data_for_itapoa: processo_data from session_state: {processo_data}")

        default_qtde_processos = 1
        default_qtde_container = 1

        if processo_data:
            consolidado_status = str(processo_data.get('Consolidado', 'Não')).strip().lower()
            logger.info(f"load_di_data_for_itapoa: Consolidado status: {consolidado_status}")

            # Lógica para Quantidade de Processos Agrupados
            if consolidado_status == 'sim':
                processos_vinculados_raw = processo_data.get('Processos_Vinculados')
                if isinstance(processos_vinculados_raw, list):
                    default_qtde_processos = len(processos_vinculados_raw) + 1
                    logger.info(f"load_di_data_for_itapoa: Consolidado, Processos_Vinculados list: {processos_vinculados_raw}, Calculated default_qtde_processos: {default_qtde_processos}")
                else:
                    default_qtde_processos = 1 # Se consolidado mas sem lista de vínculos, considera 1 (o próprio processo)
                    logger.info(f"load_di_data_for_itapoa: Consolidado but no linked processes list, default_qtde_processos: {default_qtde_processos}")
            else:
                default_qtde_processos = 1 # Se não consolidado, sempre 1
                logger.info(f"load_di_data_for_itapoa: Not consolidated, default_qtde_processos: {default_qtde_processos}")


            # Lógica para Quantidade de Contêineres
            if consolidado_status == 'sim':
                default_qtde_container = 1 # Se consolidado, a quantidade de containers é 1
                logger.info(f"load_di_data_for_itapoa: Consolidado, default_qtde_container: {default_qtde_container}")
            else:
                # Se não consolidado, usa o valor de 'Quantidade_Containers' do processo
                qtde_containers_from_process = processo_data.get('Quantidade_Containers')
                try:
                    default_qtde_container = int(qtde_containers_from_process) if pd.notna(qtde_containers_from_process) else 1
                    logger.info(f"load_di_data_for_itapoa: Not consolidated, Quantidade_Containers from process: {qtde_containers_from_process}, default_qtde_container: {default_qtde_container}")
                except (ValueError, TypeError) as e:
                    default_qtde_container = 1
                    logger.warning(f"load_di_data_for_itapoa: Could not convert Quantidade_Containers '{qtde_containers_from_process}' to int, setting default_qtde_container to 1. Error: {e}")


        # Atualiza o session_state com os valores calculados
        st.session_state.itapoa_qtde_processos = default_qtde_processos
        st.session_state.itapoa_qtde_container = default_qtde_container
        logger.info(f"load_di_data_for_itapoa: Session state updated - qtde_processos: {st.session_state.itapoa_qtde_processos}, qtde_container: {st.session_state.itapoa_qtde_container}")

        st.session_state.itapoa_periodo = 1
        st.session_state.itapoa_dias = 5
        st.session_state.itapoa_diferenca = 0.00
        st.session_state.itapoa_taxas_extras = 0.00


        perform_calculations() # Realiza o cálculo inicial
        logging.info(f"Dados da DI {declaracao_id} carregados para Itapoá.")
    else:
        st.error(f"Nenhum dado encontrado para a DI ID: {declaracao_id} (Itapoá)")
        clear_itapoa_data()
        logger.info(f"load_di_data_for_itapoa: DI data not found for ID: {declaracao_id}, cleared Itapoá data.")

def clear_itapoa_data():
    """Limpa todos os dados e campos da tela Itapoá no session_state."""
    logger.info("clear_itapoa_data: Iniciado.")
    st.session_state.itapoa_di_data = None
    st.session_state.itapoa_declaracao_id = None
    st.session_state.itapoa_qtde_processos = 1
    st.session_state.itapoa_qtde_container = 1
    st.session_state.itapoa_periodo = 1
    st.session_state.itapoa_dias = 1
    st.session_state.itapoa_diferenca = 0.00
    st.session_state.itapoa_taxas_extras = 0.00

    st.session_state.itapoa_calculated_data = {
        'vmld_di': 0.0,
        'armazenagem': 0.0,
        'levante': 0.0,
        'pesagem': 0.0,
        'total_a_depositar': 0.0
    }
    # Limpa também os campos de e-mail
    st.session_state.itapoa_email_to = "jjenessa23@gmail.com"
    st.session_state.itapoa_email_subject_send = ""
    st.session_state.itapoa_email_body_send = ""
    st.session_state.itapoa_email_attachments_list = []
    logging.info("clear_itapoa_data: Dados da tela Itapoá limpos.")

# --- Funções de Geração de Conteúdo de E-mail para Itapoá ---
def generate_itapoa_email_content():
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
    """Gera o conteúdo do e-mail para Armazenagem Portuária - Itapoá."""
    di_data = st.session_state.itapoa_di_data
    referencia_processo = di_data['informacao_complementar'] if 'informacao_complementar' in di_data and di_data['informacao_complementar'] else "N/A"
    
    # Pega os valores formatados para exibição
    valor_total_depositar = _format_currency(st.session_state.itapoa_calculated_data['total_a_depositar'])
    periodo = st.session_state.itapoa_periodo
    dias = st.session_state.itapoa_dias
    qtde_container = st.session_state.itapoa_qtde_container

    current_hour = datetime.now().hour
    saudacao = "Bom dia" if 6 <= current_hour < 12 else "Boa tarde"

    usuario_programa = st.session_state.get('user_info', {}).get('username', 'Usuário do Programa')
    data_hoje = datetime.now().strftime("%d/%m/%Y")
    
    email_body_plaintext = f"""{saudacao} Mayra,

Segue armazenagem Portuária.
Referência dos Processos: {referencia_processo}
Valor total a Depositar: {valor_total_depositar}
Período: {periodo}
Dias: {dias}
Serviço: Armazenagem portuária, Remoção de {qtde_container}*40HC
Vencimento: {data_hoje}

PAGAMENTO VIA BOLETO

Conforme instruções em anexo.
Obs.: Invoice e DI da importação em anexo.

Obrigado,
{usuario_programa}
"""
    email_subject = f"{referencia_processo} - Pagamento de Armazenagem Itapoá"
    
    return email_subject, email_body_plaintext

# --- Função para Enviar E-mail com Anexos (adaptada de Pac Log Elo) ---
def send_email_with_attachments_itapoa(to_emails, subject, body, uploaded_files):
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


def save_armazenagem_to_db():
    """Salva o valor do Total a Depositar calculado no banco de dados."""
    if 'itapoa_di_data' not in st.session_state or st.session_state.itapoa_declaracao_id is None:
        st.warning("Dados da DI não carregados para salvar o Total a Depositar.")
        return

    try:
        total_a_depositar_float = st.session_state.itapoa_calculated_data['total_a_depositar']

        di_data = st.session_state.itapoa_di_data
        declaracao_id = st.session_state.itapoa_declaracao_id

        # Cria um dicionário com os dados da DI, atualizando apenas 'armazenagem'
        updated_di_data = dict(di_data) # Cria uma cópia mutável
        updated_di_data['armazenagem'] = total_a_depositar_float

        # Chamar a função de atualização do db_utils
        # Usar a função importada update_declaracao
        success = update_declaracao(declaracao_id, updated_di_data)

        if success:
            st.success("Valor do Total a Depositar salvo no banco de dados!")
            # Opcional: Recarregar os dados da DI para refletir a mudança, se necessário
            # load_di_data_for_itapoa(declaracao_id)
        else:
            st.error("Falha ao salvar o Total a Depositar no banco de dados.")

    except Exception as e:
        st.error(f"Ocorreu um erro inesperado ao salvar o Total a Depositar: {e}")
        logging.exception("Erro inesperado ao salvar Total a Depositar no DB (Itapoá).")

def send_email_and_save_action_itapoa():
    """
    Combina a lógica de preparar, exibir, enviar e-mail e salvar no banco de dados para Itapoá.
    """
    if 'itapoa_di_data' not in st.session_state or not st.session_state.itapoa_di_data:
        st.warning("Carregue os dados da DI antes de enviar o e-mail.")
        return

    # Preenche os campos do formulário de envio de e-mail ao carregar a DI ou recalcular
    email_subject_generated, email_body_plaintext_generated = generate_itapoa_email_content()
    
    # Atualiza st.session_state diretamente para que os widgets reflitam os valores gerados
    # Preenche apenas se não tiver sido editado manualmente (para evitar sobrescrever edições do usuário)
    # A verificação 'if not st.session_state.itapoa_email_subject_send' garante que o campo não seja sobrescrito
    # se o usuário já tiver digitado algo.
    # Para forçar a atualização automática sempre, remova a condição 'if not ...'
    st.session_state.itapoa_email_subject_send = email_subject_generated
    st.session_state.itapoa_email_body_send = email_body_plaintext_generated
    
    # CAMPOS DE ENTRADA DO E-MAIL
    to_emails_input = st.text_input(
        "Para (e-mails separados por vírgula):",
        value=st.session_state.itapoa_email_to,
        key="itapoa_send_to_emails_input"
    )
    st.session_state.itapoa_email_to = to_emails_input.strip()

    st.session_state.itapoa_email_subject_send = st.text_input(
        "Assunto:",
        value=st.session_state.itapoa_email_subject_send,
        key="itapoa_send_email_subject_input"
    )
    
    st.session_state.itapoa_email_body_send = st.text_area(
        "Corpo do E-mail:",
        value=st.session_state.itapoa_email_body_send,
        height=300, # Aumentei a altura para melhor visualização
        key="itapoa_send_email_body_input"
    )
    
    uploaded_files = st.file_uploader(
        "Arraste e solte ou selecione arquivos para anexar (múltiplos)",
        type=None, # Permite todos os tipos de arquivo
        accept_multiple_files=True,
        key="itapoa_send_email_attachments_uploader"
    )
    # Garante que st.session_state.itapoa_email_attachments_list é uma lista mutável
    if 'itapoa_email_attachments_list' not in st.session_state:
        st.session_state.itapoa_email_attachments_list = []

    # Atualiza a lista de anexos se novos arquivos foram carregados
    if uploaded_files:
        current_attached_names = {f.name for f in st.session_state.itapoa_email_attachments_list}
        for file in uploaded_files:
            if file.name not in current_attached_names:
                st.session_state.itapoa_email_attachments_list.append(file)
    
    # Exibe os arquivos atualmente anexados (e permite remover)
    if st.session_state.itapoa_email_attachments_list:
        st.markdown("###### Arquivos anexados:")
        for i, file in enumerate(st.session_state.itapoa_email_attachments_list):
            col_file_name, col_remove_btn = st.columns([0.8, 0.2])
            with col_file_name:
                st.write(f"- {file.name}")
            with col_remove_btn:
                if st.button("Remover", key=f"itapoa_remove_attachment_{i}"):
                    st.session_state.itapoa_email_attachments_list.pop(i)
                    st.rerun() # Força o Streamlit a rerenderizar para atualizar a lista

    col1, col2 = st.columns([0.5, 0.2]) # Colunas para o botão de enviar/salvar e talvez um espaço
    with col1:
        if st.button("Enviar E-mail e Salvar", key="itapoa_send_email_and_save_btn", use_container_width=True):
            if not st.session_state.itapoa_email_to:
                st.warning("Por favor, preencha o(s) destinatário(s) do e-mail.")
            else:
                list_of_recipients = [email.strip() for email in st.session_state.itapoa_email_to.split(',') if email.strip()]
                
                if list_of_recipients:
                    with st.spinner("Enviando e-mail e salvando no banco de dados..."):
                        # 1. Tenta enviar o e-mail
                        email_sent_successfully = send_email_with_attachments_itapoa(
                            to_emails=list_of_recipients,
                            subject=st.session_state.itapoa_email_subject_send,
                            body=st.session_state.itapoa_email_body_send,
                            uploaded_files=st.session_state.itapoa_email_attachments_list # Usa a lista de arquivos anexados
                        )
                        
                        # 2. Se o e-mail foi enviado com sucesso, salva no banco de dados
                        if email_sent_successfully:
                            save_armazenagem_to_db()
                            # REMOVIDO: load_di_data_for_itapoa(st.session_state.itapoa_di_data.get('id'))
                            
                            # Limpa os campos após o envio bem-sucedido
                            st.session_state.itapoa_email_to = "jjenessa23@gmail.com"
                            st.session_state.itapoa_email_subject_send = ""
                            st.session_state.itapoa_email_body_send = ""
                            st.session_state.itapoa_email_attachments_list = [] # Limpa a lista de anexos
                            st.toast(f"✅ E-mail enviado com sucesso!", icon="✅")
                            sleep (3) # Pausa de 3 segundos para o usuário ver a mensagem
                    st.rerun() # Força rerender para limpar os campos ou mostrar status
                else:
                    st.warning("Nenhum destinatário válido encontrado.")

# --- Tela Principal do Streamlit para Itapoá ---
def show_page():
    logger.info("show_page: Iniciado.")
    background_image_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'assets', 'logo_navio_atracado.png')
    set_background_image(background_image_path)
    
    st.subheader("Cálculo Armazenagem Portuária - Itapoá")

    # Inicializa o estado da sessão para esta página
    # Garante que as chaves existam no session_state antes de serem acessadas
    st.session_state.setdefault('itapoa_di_data', None)
    st.session_state.setdefault('itapoa_declaracao_id', None)
    st.session_state.setdefault('itapoa_qtde_processos', 1)
    st.session_state.setdefault('itapoa_qtde_container', 1)
    st.session_state.setdefault('itapoa_periodo', 1)
    st.session_state.setdefault('itapoa_dias', 5)
    st.session_state.setdefault('itapoa_diferenca', 0.00)
    st.session_state.setdefault('itapoa_taxas_extras', 0.00)
    st.session_state.setdefault('itapoa_calculated_data', {
        'vmld_di': 0.0,
        'armazenagem': 0.0,
        'levante': 0.0,
        'pesagem': 0.0,
        'total_a_depositar': 0.0
    })
    # Inicializa os estados para os campos de e-mail a serem enviados
    st.session_state.setdefault('itapoa_email_to', "jjenessa23@gmail.com")
    st.session_state.setdefault('itapoa_email_subject_send', "")
    st.session_state.setdefault('itapoa_email_body_send', "")
    st.session_state.setdefault('itapoa_email_attachments_list', [])

    logger.info(f"show_page: Session state after setdefault - qtde_processos: {st.session_state.itapoa_qtde_processos}, qtde_container: {st.session_state.itapoa_qtde_container}")

    # Verifica se há um ID de DI vindo da tela de Detalhes
    # A lógica aqui é fundamental para disparar o carregamento dos dados do processo.
    if 'itapoa_selected_di_id' in st.session_state and st.session_state.itapoa_selected_di_id is not None:
        logger.info(f"show_page: itapoa_selected_di_id found: {st.session_state.itapoa_selected_di_id}")
        
        # Condição para recarregar os dados:
        # 1. Se `itapoa_di_data` ainda não foi carregado
        # 2. OU se o ID da DI atual na tela é diferente do ID da DI que veio da tela de detalhes
        # Isso garante que a DI seja carregada APENAS quando necessário.
        if st.session_state.itapoa_di_data is None or \
           st.session_state.itapoa_di_data.get('id') != st.session_state.itapoa_selected_di_id:
            logger.info("show_page: Calling load_di_data_for_itapoa due to new/unloaded DI ID.")
            load_di_data_for_itapoa(st.session_state.itapoa_selected_di_id)
            # É CRÍTICO aqui limpar o `itapoa_selected_di_id` *imediatamente após* o carregamento
            # e forçar um `st.rerun()` para que os `st.number_input` sejam renderizados
            # com os novos valores que foram definidos em `load_di_data_for_itapoa`.
            st.session_state.itapoa_selected_di_id = None
            st.rerun() # Adicionado st.rerun() para forçar a atualização dos widgets de input


    logger.info(f"show_page: Before rendering inputs - qtde_processos: {st.session_state.itapoa_qtde_processos}, qtde_container: {st.session_state.itapoa_qtde_container}")

    app_root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    # Seção para carregar DI
    st.markdown("---")
    st.markdown("#### Carregar Dados da DI")
    
    # Layout para o título do processo e o logo
    col_1, col_2 = st.columns([0.7, 0.3]) 
    with col_1:
        # Exibe a referência do processo
        if st.session_state.itapoa_di_data:
            st.markdown(f"#### Processo: **{st.session_state.itapoa_di_data.get('informacao_complementar', 'N/A')}**")
            st.markdown(f"**VMLD da DI:** {_format_currency(st.session_state.itapoa_di_data.get('vmld', 0.0))}")
        else:
            st.info("Nenhuma DI carregada. Por favor, carregue uma DI para iniciar os cálculos.")
    with col_2:  
        # Adicionando imagem de logo da Itapoá
        logo_itapoa_path = os.path.join(app_root_dir, 'assets', 'itapoa.png') # Assumindo o nome do arquivo do logo
        if os.path.exists(logo_itapoa_path):
            st.image(logo_itapoa_path, width=150, caption="Itapoá")
        else:
            st.warning("Logo da Itapoá não encontrada. Verifique o caminho do arquivo 'assets/itapoa.png'.")


    st.markdown("---")
    st.markdown("#### Parâmetros de Cálculo")

    # Layout dos campos de entrada em colunas
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        # Usa o valor do session_state como valor padrão
        st.number_input(
            "Qtde de Processos", 
            min_value=1, 
            format="%d", 
            key="itapoa_qtde_processos", 
            value=st.session_state.itapoa_qtde_processos, # Definido aqui
            on_change=perform_calculations
        )
        st.number_input(
            "Qtde de Contêiner", 
            min_value=1, 
            format="%d", 
            key="itapoa_qtde_container", 
            value=st.session_state.itapoa_qtde_container, # Definido aqui
            on_change=perform_calculations
        )
    
    with col2:
        st.number_input("Período", min_value=1, max_value=4, format="%d", key="itapoa_periodo", on_change=perform_calculations)
        st.number_input("Dias no Período", min_value=1, format="%d", key="itapoa_dias", on_change=perform_calculations)

    with col3:
        # Levante e Pesagem como inputs, permitindo edição
        # Usar os valores calculados do session_state, não as constantes fixas
        st.number_input("Remoção (R$)", format="%.2f", key="itapoa_levante_display", 
                        value=st.session_state.itapoa_calculated_data['levante'], on_change=perform_calculations)
        st.number_input("Controle de Acesso (R$)", format="%.2f", key="itapoa_pesagem_display", 
                        value=st.session_state.itapoa_calculated_data['pesagem'], on_change=perform_calculations)

    with col4:
        # Diferença e Taxas Extras
        st.number_input("DIFERENÇA (R$)", format="%.2f", key="itapoa_diferenca", on_change=perform_calculations)
        st.number_input("Taxas Extras (R$)", format="%.2f", key="itapoa_taxas_extras", on_change=perform_calculations)


    st.markdown("---")
    st.markdown("#### Resultados do Cálculo")

    # Exibição dos resultados em uma tabela ou colunas
    if st.session_state.itapoa_calculated_data:
        calc_data = st.session_state.itapoa_calculated_data
        
        col_res1, col_res2, col_res3, col_res4 = st.columns(4)
        with col_res1:
            st.metric("Armazenagem", _format_currency(calc_data['armazenagem']))
        with col_res2:
            st.metric("Remoção", _format_currency(calc_data['levante']))
        with col_res3:
            st.metric("Controle de Acesso", _format_currency(calc_data['pesagem']))
        with col_res4:
            st.metric("Total a Depositar", _format_currency(calc_data['total_a_depositar']))
    else:
        st.info("Aguardando dados para cálculo...")

    st.markdown("---")
    st.markdown("#### Tabela de Referência Itapoa")
    # Exibir a tabela de referência (pode ser um DataFrame ou Markdown)
    tabela_data_df = pd.DataFrame([
        ("1º período", "0,656%", "até 5 dias", "R$ 1197,00"),
        ("2º período", "0,348%", "6 a 10 dias", "R$ 264,00"),
        ("3º período", "0,440%", "11 a 29 dias", "R$ 372,00"),
        ("4º período", "0,473%", "30 em diante", "R$ 479,00"),
        ("LEVANTE", "", "", "R$ 424,00"),
        ("PESAGEM", "", "", "R$ 105,00")
    ], columns=["Período", "%", "Dias", "Mínimos"])
    st.dataframe(tabela_data_df, hide_index=True, use_container_width=True)

    st.markdown("* Observação: em casos de divergência de valores consultar tabela padrão no link abaixo")

    st.markdown("---")
    st.markdown("#### Enviar E-mail e Salvar no Banco de Dados")
    send_email_and_save_action_itapoa() # Chamada da nova função que gerencia a seção de e-mail e salvamento

    st.markdown("---")
    if st.button("Voltar para Detalhes da DI", key="itapoa_voltar_di"):
        st.session_state.current_page = "Pagamentos" # Assumindo que você voltaria para a página de Pagamentos
        st.rerun()

