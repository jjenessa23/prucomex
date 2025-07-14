import pytz
import streamlit as st
import pandas as pd
import logging
import os
from datetime import datetime, date # Importar date também
import urllib.parse # Para codificar URLs para o mailto
from time import sleep

# Importa as funções reais do db_utils
# ATENÇÃO: Certifique-se de que 'db_utils.py' existe no mesmo diretório raiz do 'app_main.py'
# e que as funções 'get_declaracao_by_id' e 'update_declaracao_field'
# estão corretamente implementadas nele para interagir com seu banco de dados real.
from db_utils import get_declaracao_by_id, update_declaracao_field

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

    
def generate_armazenagem_email_content():
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
    """Gera o conteúdo do e-mail para Armazenagem Elo - Pac Log."""
    di_data = st.session_state.elo_di_data
    referencia_processo = st.session_state.elo_processo_ref
    valor_total_depositar = st.session_state.elo_total_a_depositar_display # Puxa do valor calculado e exibido

    current_hour = datetime.now().hour
    saudacao = "Bom dia" if 9 <= current_hour < 15 else "Boa tarde"
    usuario_programa = st.session_state.get('user_info', {}).get('username', 'usuário do sistema')
    
    # Obtém a data de vencimento do session_state, formatando-a
    data_vencimento_str = st.session_state.elo_data_vencimento.strftime("%d/%m/%Y")
    
    pagamento = "PAGAMENTO VIA BOLETO" # texto cor vermelha e negrito
    # Corpo do e-mail em texto plano (pode ser adaptado para HTML)
    email_body_plaintext = f"""{saudacao} Mayra,

Segue armazenagem.
Processo: {referencia_processo}
Valor total a Depositar: {valor_total_depositar}
Vencimento: {data_vencimento_str}

{pagamento}

Banco: ITAÚ
Empresa: ELO SOLUCOES LOGISTICAS INTEGRADAS LTDA
CNPJ nº 31.626.973/0001-64
Agência: 0292
Conta Corrente: 58339-0-7

Conforme instruções em anexo.
Obs.: Invoice e DI da importação em anexo.

Obrigado(a),
{usuario_programa}
"""
    email_subject = f"{referencia_processo} - Armazenagem Elo - Pac Log"
    
    return email_subject, email_body_plaintext

# --- Função para Enviar E-mail com Anexos ---
def send_email_with_attachments_elo(to_emails, subject, body, uploaded_files):
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

        # Anexa o corpo do e-mail (agora espera que o 'body' possa ser HTML)
        # Se você for usar HTML, certifique-se de que o 'body' gerado por generate_armazenagem_email_content
        # seja um HTML válido. Caso contrário, mantenha "plain".
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

def _save_armazenagem_to_db():
    """Salva o valor da armazenagem calculada no banco de dados."""
    if 'elo_di_data' not in st.session_state or not st.session_state.elo_di_data:
        st.error("Não há dados da DI carregados para salvar a armazenagem.")
        return

    # O ID da DI é acessado como uma chave do dicionário
    di_id = st.session_state.elo_di_data.get('id')
    
    if di_id is None:
        st.error("ID da DI não encontrado nos dados carregados para salvar a armazenagem.")
        return

    # O valor a ser salvo é o 'Total a Depositar' calculado (VMLD * 0.40%)
    # Ele já está disponível em st.session_state.elo_total_a_depositar_display
    # Precisamos convertê-lo de volta para float.
    armazenagem_to_save_str = st.session_state.elo_total_a_depositar_display
    try:
        armazenagem_float = float(armazenagem_to_save_str.replace('R$', '').replace('.', '').replace(',', '.').strip())
    except ValueError:
        st.error("Valor de Armazenagem calculado inválido para salvar no banco de dados.")
        return

    if update_declaracao_field(di_id, 'armazenagem', armazenagem_float):
        st.success(f"Valor de armazenagem ({_format_currency(armazenagem_float)}) salvo com sucesso para a DI ID {di_id}!")
        st.toast(f"✅ E-mail enviado com sucesso!", icon="✅")
        sleep (3) # Pausa de 1 segundo para o usuário ver a mensagem
    else:
        st.error(f"Falha ao salvar o valor de armazenagem para a DI ID {di_id}.")

def load_elo_di_data(declaracao_id):
    """
    Carrega os dados da DI para a tela Armazenagem Elo e inicializa o estado da sessão.
    """
    if not declaracao_id:
        logger.warning("Nenhum ID de declaração fornecido para carregar dados (Armazenagem Elo).")
        clear_elo_di_data()
        return

    logger.info(f"Carregando dados para DI ID (Armazenagem Elo): {declaracao_id}")
    di_data_dict = get_declaracao_by_id(declaracao_id) # Agora retorna um dicionário

    if di_data_dict:
        st.session_state.elo_di_data = di_data_dict # Armazena o dicionário diretamente
        
        # Acessa os dados usando .get() para robustez e legibilidade
        # Forneça um valor padrão (0.0 ou "N/A") caso a chave não exista, para evitar erros.
        informacao_complementar = di_data_dict.get('informacao_complementar')
        vmld = di_data_dict.get('vmld', 0.0)
        peso_bruto = di_data_dict.get('peso_bruto', 0.0)
        peso_liquido = di_data_dict.get('peso_liquido', 0.0)
        armazenagem_db_value = di_data_dict.get('armazenagem', 0.0) # Assume que a chave é 'armazenagem'
        # frete_nacional_db = di_data_dict.get('frete_nacional', 0.0) # Não está sendo usado diretamente aqui

        st.session_state.elo_processo_ref = informacao_complementar if informacao_complementar else "N/A"
        
        logger.info(f"DEBUG ELO: DI ID {declaracao_id} - VMLD: {vmld}, Peso Bruto: {peso_bruto}, Armazenagem DB: {armazenagem_db_value}")


        # Atualiza os valores brutos da DI no session_state para uso nos cálculos
        st.session_state.elo_vmld_raw = vmld
        st.session_state.elo_peso_bruto_raw = peso_bruto
        st.session_state.elo_peso_liquido_raw = peso_liquido
        st.session_state.elo_armazenagem_db_raw = armazenagem_db_value # Guarda o valor do DB para comparação

        # Força o recálculo para garantir que os valores iniciais do DB sejam usados
        perform_elo_calculations()

    else:
        st.warning(f"Nenhum dado encontrado para a DI ID: {declaracao_id} (Armazenagem Elo)")
        clear_elo_di_data()

def clear_elo_di_data():
    """Limpa todos os dados e estados da sessão para a tela Armazenagem Elo."""
    st.session_state.elo_di_data = None
    st.session_state.elo_processo_ref = "PCH-XXXX-XX"
    # st.session_state.elo_armazenagem_value = _format_currency(0.00) # Removido, não é mais um input
    st.session_state.show_elo_email_expander = False
    st.session_state.elo_email_type_to_show = None
    # Limpa os valores calculados e brutos
    st.session_state.elo_vmld_raw = 0.0
    st.session_state.elo_peso_bruto_raw = 0.0
    st.session_state.elo_peso_liquido_raw = 0.0
    st.session_state.elo_armazenagem_db_raw = 0.0
    st.session_state.elo_vmld_di_display = _format_currency(0.00)
    st.session_state.elo_periodo_display = "N/A"
    st.session_state.elo_peso_bruto_di_display = _format_weight_no_kg(0.00)
    st.session_state.elo_peso_liquido_di_display = _format_weight_no_kg(0.00)
    st.session_state.elo_total_armazenagem_display = _format_currency(0.00)
    st.session_state.elo_tabela_valor_display = _format_currency(0.00)
    st.session_state.elo_total_a_depositar_display = _format_currency(0.00)
    st.session_state.elo_taxas_extras_value = _format_currency(0.00)
    st.session_state.elo_diferenca_value = _format_currency(0.00)
    st.session_state.elo_pis_cofins_iss_display = _format_currency(0.00)
    st.session_state.elo_carregamento_display = _format_currency(0.00)
    st.session_state.elo_data_vencimento = date.today() # NOVO: Define a data de hoje ao limpar

    # Limpa os campos de e-mail
    st.session_state.elo_email_to = "jjenessa23@gmail.com"
    st.session_state.elo_email_subject_send = ""
    st.session_state.elo_email_body_send = ""
    st.session_state.elo_email_attachments_list = []


def perform_elo_calculations():
    """Realiza os cálculos de armazenagem, capatazia e impostos para a tela Elo."""
    if 'elo_di_data' not in st.session_state or not st.session_state.elo_di_data:
        logger.warning("Não há dados da DI para realizar cálculos (Elo).")
        return

    # Puxa os valores brutos da DI do session_state
    vmld = st.session_state.elo_vmld_raw
    peso_bruto = st.session_state.elo_peso_bruto_raw
    # peso_liquido = st.session_state.elo_peso_liquido_raw # Não usado diretamente nos cálculos abaixo
    # armazenagem_db_value = st.session_state.elo_armazenagem_db_raw # Não é mais usado para inicializar input

    # Obter valores de Taxas Extras e Diferença como floats dos session_states
    try:
        taxas_extras_atual_float = float(st.session_state.elo_taxas_extras_value.replace('R$', '').replace('.', '').replace(',', '.').strip())
    except ValueError:
        taxas_extras_atual_float = 0.00
        logger.warning("Valor de Taxas Extras (Elo) inválido, usando 0.00 para cálculo.")
    
    try:
        diferenca_atual_float = float(st.session_state.elo_diferenca_value.replace('R$', '').replace('.', '').replace(',', '.').strip())
    except ValueError:
        diferenca_atual_float = 0.00
        logger.warning("Valor de Diferença (Elo) inválido, usando 0.00 para cálculo.")

    # --- Cálculo de Armazenagem ---
    # O total de armazenagem é VMLD x período (0,40%)
    periodo_percent = 0.0040 # 0,40%
    total_armazenagem = vmld * periodo_percent
        
    # --- Cálculo de Capatazia ---
    capatazia_por_kg = 0.08
    capatazia_calculada = peso_bruto * capatazia_por_kg
    capatazia_minima = 17.95 # Valor fixo da tabela
    
    # Aplica a regra da capatazia mínima (se a calculada for menor que a mínima, usa a mínima)
    capatazia_final = max(capatazia_calculada, capatazia_minima)
    
    tabela_valor = capatazia_final 

    # --- Cálculo de Impostos (PIS/COFINS/ISS) - NOVA FÓRMULA ---
    # Impostos = (Armazenagem + Capatazia + Carregamento) / 0.8775 - (Armazenagem + Capatazia + Carregamento)
    CARREGAMENTO_FIXO = 350.00 # Definido como constante na classe CalculoPacLogEloView
    base_impostos_nova = total_armazenagem + capatazia_final + CARREGAMENTO_FIXO
    if base_impostos_nova != 0: # Evita divisão por zero
        impostos_calculados = (base_impostos_nova / 0.8775) - base_impostos_nova
    else:
        impostos_calculados = 0.0
    
    # --- Total a Depositar ---
    # Inclui o CARREGAMENTO_FIXO, Taxas Extras e o valor da DIFERENÇA
    total_a_depositar = total_armazenagem + capatazia_final + impostos_calculados + CARREGAMENTO_FIXO + diferenca_atual_float + taxas_extras_atual_float

    # DEBUG: Log dos valores intermediários e final do cálculo
    logger.info(f"DEBUG ELO Cálculos: Total Armazenagem (VMLD*0.40%): {total_armazenagem}, Capatazia Final: {capatazia_final}, Impostos Calculados: {impostos_calculados}, Carregamento Fixo: {CARREGAMENTO_FIXO}, Diferença: {diferenca_atual_float}, Taxas Extras: {taxas_extras_atual_float}")
    logger.info(f"DEBUG ELO Cálculos: TOTAL A DEPOSITAR FINAL: {total_a_depositar}")


    # Atualiza os valores no session_state para exibição
    st.session_state.elo_vmld_di_display = _format_currency(vmld)
    st.session_state.elo_periodo_display = "1" # Placeholder, você pode calcular o período real aqui
    st.session_state.elo_peso_bruto_di_display = _format_weight_no_kg(peso_bruto)
    st.session_state.elo_peso_liquido_di_display = _format_weight_no_kg(st.session_state.elo_peso_liquido_raw) # Puxa do raw para exibição
    st.session_state.elo_total_armazenagem_display = _format_currency(total_armazenagem)
    st.session_state.elo_tabela_valor_display = _format_currency(tabela_valor)
    st.session_state.elo_total_a_depositar_display = _format_currency(total_a_depositar)
    st.session_state.elo_pis_cofins_iss_display = _format_currency(impostos_calculados)
    st.session_state.elo_carregamento_display = _format_currency(CARREGAMENTO_FIXO)

    # NOVO: Atualiza o assunto e corpo do e-mail ao recalcular
    email_subject_generated, email_body_plaintext_generated = generate_armazenagem_email_content()
    st.session_state.elo_email_subject_send = email_subject_generated
    st.session_state.elo_email_body_send = email_body_plaintext_generated


def show_calculo_paclog_elo_page():
    """
    Exibe a interface de usuário para o cálculo de Armazenagem Elo - Pac Log.
    """
    # --- Configuração da Imagem de Fundo para a página ---
    current_dir = os.path.dirname(os.path.abspath(__file__))
    root_dir = os.path.join(current_dir, '..')
    app_root_dir = os.path.join(root_dir, '..')
    #background_image_path = os.path.join(app_root_dir, 'assets', 'logo_navio_atracado.png')
    

    background_image_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'assets', 'logo_navio_atracado.png')
    

    try:
        from app_logic.utils import set_background_image
        set_background_image(background_image_path)
    except ImportError:
        st.warning("Não foi possível carregar a função de imagem de fundo. Verifique o arquivo utils.py.")
    # --- Fim da Configuração da Imagem de Fundo ---

    st.subheader("Armazenagem Elo - Pac Log")

    # Inicializa variáveis de estado para a página
    st.session_state.setdefault('elo_di_data', None)
    st.session_state.setdefault('elo_processo_ref', "PCH-XXXX-XX")
    st.session_state.setdefault('show_elo_email_expander', False)
    st.session_state.setdefault('elo_email_type_to_show', None)
    # Inicializa variáveis de estado para os valores calculados
    st.session_state.setdefault('elo_vmld_di_display', _format_currency(0.00))
    st.session_state.setdefault('elo_periodo_display', "N/A")
    st.session_state.setdefault('elo_peso_bruto_di_display', _format_weight_no_kg(0.00))
    st.session_state.setdefault('elo_peso_liquido_di_display', _format_weight_no_kg(0.00))
    st.session_state.setdefault('elo_total_armazenagem_display', _format_currency(0.00))
    st.session_state.setdefault('elo_tabela_valor_display', _format_currency(0.00))
    st.session_state.setdefault('elo_total_a_depositar_display', _format_currency(0.00))
    st.session_state.setdefault('elo_taxas_extras_value', _format_currency(0.00))
    st.session_state.setdefault('elo_diferenca_value', _format_currency(0.00))
    st.session_state.setdefault('elo_pis_cofins_iss_display', _format_currency(0.00))
    st.session_state.setdefault('elo_carregamento_display', _format_currency(0.00))
    # Inicializa os valores brutos da DI no session_state
    st.session_state.setdefault('elo_vmld_raw', 0.0)
    st.session_state.setdefault('elo_peso_bruto_raw', 0.0)
    st.session_state.setdefault('elo_peso_liquido_raw', 0.0)
    st.session_state.setdefault('elo_armazenagem_db_raw', 0.0)
    st.session_state.setdefault('elo_data_vencimento', date.today()) # NOVO: Inicializa com a data de hoje

    # Inicializa os estados para os campos de e-mail a serem enviados
    st.session_state.setdefault('elo_email_to', "jjenessa23@gmail.com")  # Valor padrão, pode ser alterado
    st.session_state.setdefault('elo_email_subject_send', "")
    st.session_state.setdefault('elo_email_body_send', "")
    st.session_state.setdefault('elo_email_attachments_list', []) # Lista para gerenciar anexos


    # Carrega os dados da DI se um ID foi passado da página anterior
    if 'selected_di_id_paclog' in st.session_state and st.session_state.selected_di_id_paclog:
        load_elo_di_data(st.session_state.selected_di_id_paclog)
        st.session_state.selected_di_id_paclog = None # Limpa o ID após carregar
        st.rerun() # Força rerun para refletir os dados carregados nos inputs

    col_1, col_2 = st.columns([0.7, 0.3]) # Colunas para o conteúdo principal e ações
    with col_1:
        st.markdown(f"#### Processo: **{st.session_state.elo_processo_ref}**")
    with col_2:  
        #adicionando imagem de logo da paclog elo
        logo_paclog_elo = os.path.join(app_root_dir, 'assets', 'paclog_elo.png')
        if os.path.exists(logo_paclog_elo):
            st.image(logo_paclog_elo, width=150, caption="Pac Log")
        else:
            st.warning("Logo da Pac Log não encontrada. Verifique o caminho do arquivo.")
    st.markdown("---")

    # O campo de entrada para o valor da armazenagem foi removido.
    # O valor da armazenagem agora é sempre calculado com base no VMLD.

    # --- Tabela de Cálculo da Armazenagem ---
    st.markdown("##### Detalhes do Cálculo de Armazenagem")
    col_vmld, col_periodo, col_peso_bruto, col_peso_liquido = st.columns(4)
    with col_vmld:
        st.markdown(f"**VMLD DI:** {st.session_state.elo_vmld_di_display}")
    with col_periodo:
        st.markdown(f"**Período:** {st.session_state.elo_periodo_display}")
    with col_peso_bruto:
        st.markdown(f"**Peso Bruto DI:** {st.session_state.elo_peso_bruto_di_display}")
    with col_peso_liquido:
        st.markdown(f"**Peso Líquido DI:** {st.session_state.elo_peso_liquido_di_display}")

    col_total_armazenagem, col_tabela_valor = st.columns(2)
    with col_total_armazenagem:
        st.markdown(f"**Total Armazenagem:** {st.session_state.elo_total_armazenagem_display}")
    with col_tabela_valor:
        st.markdown(f"**Tabela Valor (Capatazia):** {st.session_state.elo_tabela_valor_display}")
    
    st.markdown("---") # Separador antes do Total a Depositar

    # NOVO: Exibição do "Total a Depositar" acima de "Taxas Extras" e "Diferença"
    st.markdown(f"##### **Total a Depositar:** {st.session_state.elo_total_a_depositar_display}")
    
   

    # Taxas Extras e Diferença
    col_taxas_extras, col_diferenca = st.columns(2)
    with col_taxas_extras:
        taxas_extras_input = st.text_input(
            "Taxas Extras (R$):",
            value=st.session_state.elo_taxas_extras_value,
            key="elo_taxas_extras_input",
            on_change=perform_elo_calculations # Recalcula ao alterar
        )
        st.session_state.elo_taxas_extras_value = taxas_extras_input
        col_taxas_btn1, col_taxas_btn2 = st.columns(2)
        with col_taxas_btn1:
            if st.button("+0.01", key="elo_taxas_plus", use_container_width=True):
                try:
                    current_value = float(st.session_state.elo_taxas_extras_value.replace('R$', '').replace('.', '').replace(',', '.').strip())
                    st.session_state.elo_taxas_extras_value = _format_currency(round(current_value + 0.01, 2))
                    perform_elo_calculations()
                    st.rerun()
                except ValueError:
                    st.error("Valor inválido para Taxas Extras.")
        with col_taxas_btn2:
            if st.button("-0.01", key="elo_taxas_minus", use_container_width=True):
                try:
                    current_value = float(st.session_state.elo_taxas_extras_value.replace('R$', '').replace('.', '').replace(',', '.').strip())
                    st.session_state.elo_taxas_extras_value = _format_currency(round(current_value - 0.01, 2))
                    perform_elo_calculations()
                    st.rerun()
                except ValueError:
                    st.error("Valor inválido para Taxas Extras.")

    with col_diferenca:
        diferenca_input = st.text_input(
            "Diferença (R$):",
            value=st.session_state.elo_diferenca_value,
            key="elo_diferenca_input",
            on_change=perform_elo_calculations # Recalcula ao alterar
        )
        st.session_state.elo_diferenca_value = diferenca_input
        col_diff_btn1, col_diff_btn2 = st.columns(2)
        with col_diff_btn1:
            if st.button("+0.01", key="elo_diferenca_plus", use_container_width=True):
                try:
                    current_value = float(st.session_state.elo_diferenca_value.replace('R$', '').replace('.', '').replace(',', '.').strip())
                    st.session_state.elo_diferenca_value = _format_currency(round(current_value + 0.01, 2))
                    perform_elo_calculations()
                    st.rerun()
                except ValueError:
                    st.error("Valor inválido para Diferença.")
        with col_diff_btn2:
            if st.button("-0.01", key="elo_diferenca_minus", use_container_width=True):
                try:
                    current_value = float(st.session_state.elo_diferenca_value.replace('R$', '').replace('.', '').replace(',', '.').strip())
                    st.session_state.elo_diferenca_value = _format_currency(round(current_value - 0.01, 2))
                    perform_elo_calculations()
                    st.rerun()
                except ValueError:
                    st.error("Valor inválido para Diferença.")

    st.markdown("---")

    # NOVO: Campo para definir a data de vencimento
    st.markdown("##### Data de Vencimento")
    st.date_input(
        "Selecione a Data de Vencimento:",
        value=st.session_state.elo_data_vencimento,
        key="elo_data_vencimento",
        on_change=perform_elo_calculations, # Recalcula o e-mail ao alterar
        format="DD/MM/YYYY"
    )

    st.markdown("---")

    # Tabela de Impostos e Carregamento Fixo
    st.markdown("##### Impostos e Carregamento")
    col_pis_cofins, col_carregamento = st.columns(2)
    with col_pis_cofins:
        st.markdown(f"**PIS/COFINS/ISS (12,25%):** {st.session_state.elo_pis_cofins_iss_display}")
    with col_carregamento:
        st.markdown(f"CARREGAMENTO: {st.session_state.elo_carregamento_display}")

    st.markdown("---")

    # Removido o botão "Gerar E-mail Armazenagem" separado.
    # A seção de envio de e-mail agora é sempre visível ou iniciada por outro fluxo.

    # Removido o botão "Salvar Armazenagem no DB" separado.
    # Sua lógica será movida para o botão "Enviar E-mail Agora".

    # --- SEÇÃO PRINCIPAL DE ENVIAR E-MAIL E SALVAR ---
    st.markdown("##### Enviar E-mail e Salvar no Banco de Dados")
    
    # Preenche os campos do formulário de envio de e-mail ao carregar a DI ou recalcular
    # Apenas preenche se os campos não tiverem sido editados manualmente, para preservar as edições do usuário
    email_subject_generated, email_body_plaintext_generated = generate_armazenagem_email_content()
    
    # Se o assunto ainda for o padrão (vazio), preenche com o gerado
    if not st.session_state.elo_email_subject_send: 
        st.session_state.elo_email_subject_send = email_subject_generated
    # Se o corpo ainda for o padrão (vazio), preenche com o gerado
    if not st.session_state.elo_email_body_send:
        st.session_state.elo_email_body_send = email_body_plaintext_generated

    to_emails_input = st.text_input(
        "Para (e-mails separados por vírgula):",
        value=st.session_state.elo_email_to,
        key="elo_send_to_emails_input"
    )
    st.session_state.elo_email_to = to_emails_input.strip()

    st.session_state.elo_email_subject_send = st.text_input(
        "Assunto:",
        value=st.session_state.elo_email_subject_send,
        key="elo_send_email_subject_input"
    )
    
    st.session_state.elo_email_body_send = st.text_area(
        "Corpo do E-mail:",
        value=st.session_state.elo_email_body_send,
        height=300, # Aumentei a altura para melhor visualização
        key="elo_send_email_body_input"
    )
    
    uploaded_files = st.file_uploader(
        "Arraste e solte ou selecione arquivos para anexar (múltiplos)",
        type=None, # Permite todos os tipos de arquivo
        accept_multiple_files=True,
        key="elo_send_email_attachments_uploader"
    )
    # Garante que st.session_state.elo_email_attachments é uma lista mutável
    if 'elo_email_attachments_list' not in st.session_state:
        st.session_state.elo_email_attachments_list = []

    # Atualiza a lista de anexos se novos arquivos foram carregados
    if uploaded_files:
        # Se houver novos arquivos, adicione-os à lista existente (evitando duplicatas se Streamlit recarregar)
        current_attached_names = {f.name for f in st.session_state.elo_email_attachments_list}
        for file in uploaded_files:
            if file.name not in current_attached_names:
                st.session_state.elo_email_attachments_list.append(file)
    
    # Exibe os arquivos atualmente anexados (e permite remover)
    if st.session_state.elo_email_attachments_list:
        st.markdown("###### Arquivos anexados:")
        for i, file in enumerate(st.session_state.elo_email_attachments_list):
            col_file_name, col_remove_btn = st.columns([0.8, 0.2])
            with col_file_name:
                st.write(f"- {file.name}")
            with col_remove_btn:
                if st.button("Remover", key=f"remove_attachment_{i}"):
                    st.session_state.elo_email_attachments_list.pop(i)
                    st.rerun() # Força o Streamlit a rerenderizar para atualizar a lista

    col1, col2 = st.columns([0.5, 0.2])
    with col1:
        if st.button("Enviar E-mail e Salvar", key="elo_send_email_and_save_btn", use_container_width=True):
            if not st.session_state.elo_email_to:
                st.warning("Por favor, preencha o(s) destinatário(s) do e-mail.")
            else:
                list_of_recipients = [email.strip() for email in st.session_state.elo_email_to.split(',') if email.strip()]
                
                if list_of_recipients:
                    with st.spinner("Enviando e-mail e salvando no banco de dados..."):
                        # 1. Tenta enviar o e-mail
                        email_sent_successfully = send_email_with_attachments_elo(
                            to_emails=list_of_recipients,
                            subject=st.session_state.elo_email_subject_send,
                            body=st.session_state.elo_email_body_send,
                            uploaded_files=st.session_state.elo_email_attachments_list # Usa a lista de arquivos anexados
                        )
                        
                        # 2. Se o e-mail foi enviado com sucesso, salva no banco de dados
                        if email_sent_successfully:
                            _save_armazenagem_to_db()
                            # Opcional: Recarregar dados da DI para exibir o valor atualizado
                            if st.session_state.elo_di_data:
                                load_elo_di_data(st.session_state.elo_di_data.get('id'))
                            
                            # Limpa os campos após o envio bem-sucedido
                            st.session_state.elo_email_to = "jjenessa23@gmail.com"
                            st.session_state.elo_email_subject_send = ""
                            st.session_state.elo_email_body_send = ""
                            st.session_state.elo_email_attachments_list = [] # Limpa a lista de anexos
                            
                    st.rerun() # Força rerender para limpar os campos ou mostrar status
                    
                else:
                    st.warning("Nenhum destinatário válido encontrado.")
    # --- FIM DA SEÇÃO PRINCIPAL DE ENVIAR E-MAIL E SALVAR ---

    st.markdown("---")
    if st.button("Voltar para Detalhes da DI", key="elo_voltar_di"):
        st.session_state.current_page = "Pagamentos" # Assumindo que você voltaria para a página de Pagamentos
        st.rerun()
