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
from app_logic.utils import set_background_image, get_dolar_cotacao

# NOVO: Importar funções do db_utils para salvar e carregar frete internacional
from app_logic.db_utils import (
    inserir_ou_atualizar_frete_internacional,
    get_frete_internacional_by_referencia
)

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
        # Formata com 4 casas decimais, troca ponto por hash, depois hash por vírgula para PT-BR
        # Note: Mantido .2f para exibir 2 casas decimais em valores totais, ajustando para .4f nos inputs
        # (mas o formatador aqui é genérico, mantendo .2f para apresentação final)
        return f"{prefix}{val:,.2f}".replace('.', '#').replace(',', '.').replace('#', ',')
    except (ValueError, TypeError):
        return f"{prefix}0,00" # Ajustado para .00 já que o formatador é para valores finais

# --- Função de callback para limpar os campos Aéreo ---
def _clear_aereo_fields():
    """
    Reseta os valores dos campos relacionados ao frete aéreo no session_state.
    """
    st.session_state.taxa_awb_aereo = 0.0
    st.session_state.dta_aereo = 0.0
    st.session_state.agency_fee_aereo = 150.0
    st.session_state.chd_aereo = 40.0
    st.session_state.total_comparacao_aereo = 0.0
    # Adicionado o reset do dólar de venda (abertura) editável
    dolar_data = get_dolar_cotacao()
    dolar_venda_abertura_api = 0.0
    if dolar_data and dolar_data['abertura_venda'] != 'N/A':
        try:
            dolar_venda_abertura_api = float(dolar_data['abertura_venda'].replace(',', '.'))
        except ValueError:
            pass # Continua com 0.0 se houver erro
    st.session_state.dolar_venda_abertura_editable = dolar_venda_abertura_api
    
    # NOVO: Limpa também os campos de e-mail ao limpar os dados do frete
    _clear_email_fields()


# --- Função de callback para limpar os campos Marítimo ---
def _clear_maritimo_fields():
    """
    Reseta os valores dos campos relacionados ao frete marítimo no session_state.
    """
    st.session_state.frete_bl_maritimo = 0.0
    st.session_state.thc_maritimo = 0.0
    st.session_state.taxas_destino_dolar_maritimo = 0.0
    st.session_state.taxas_destino_real_maritimo = 0.0
    st.session_state.agency_fee_maritimo = 0.0
    
    # NOVO: Limpa também os campos de e-mail ao limpar os dados do frete
    _clear_email_fields()

# NOVO: Função para limpar os campos de e-mail
def _clear_email_fields():
    """
    Reseta os valores dos campos relacionados ao envio de e-mail no session_state.
    """
    # Define o valor padrão (não None)
    st.session_state.frete_email_to = "jjenessa23@gmail.com"
    # O assunto e corpo serão recalculados automaticamente no próximo rerun
    st.session_state.frete_email_subject_send = ""
    st.session_state.frete_email_body_send = ""
    st.session_state.frete_email_attachments_list = [] # Limpa a lista de anexos

# --- Função para copiar texto para a área de transferência usando JavaScript ---
def _copy_to_clipboard(text_to_copy, button_key):
    """
    Copia o texto fornecido para a área de transferência do usuário.
    Usa um hack com st.components.v1.html para executar JavaScript no navegador.
    """
    js_code = f"""
    <script>
        var text = `{text_to_copy}`;
        var textArea = document.createElement("textarea");
        textArea.value = text;
        document.body.appendChild(textArea);
        textArea.select();
        try {{
            document.execCommand('copy');
            alert('Conteúdo copiado!');
        }} catch (err) {{
            alert('Não foi possível copiar: ' + err);
        }}
        document.body.removeChild(textArea);
    </script>
    """
    components.html(js_code, height=0, width=0) # height e width 0 para não ocupar espaço

# --- Função para obter a saudação conforme o horário ---
def _get_greeting():
    """
    Retorna uma saudação apropriada baseada na hora atual (GMT-3).
    """
    # Define o fuso horário de Brasília (que é GMT-3 na maior parte do ano)
    brasilia_tz = pytz.timezone('America/Sao_Paulo')
    # Obtém a hora atual no fuso horário de Brasília
    current_hour = datetime.now(brasilia_tz).hour

    if 6 <= current_hour < 12:
        return "Bom dia"
    elif 12 <= current_hour < 18:
        return "Boa tarde"
    else:
        return "Boa noite"

# NOVO: Função para salvar o frete internacional no banco de dados
def _save_frete_internacional(frete_type, total_calculated_brl, iof_usd_val, dolar_cotacao_usado):
    referencia_processo = st.session_state.get('referencia_pch', 'N/A').strip()
    if not referencia_processo or referencia_processo == 'N/A' or not referencia_processo.startswith("PCH-"):
        st.error("Por favor, insira uma Referência de Processo válida (ex: PCH-XXXXX-XX) antes de salvar.")
        return False

    frete_data = {
        "referencia_processo": referencia_processo,
        "tipo_frete": frete_type,
        "data_calculo": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "dolar_cotacao_usado": dolar_cotacao_usado
    }

    if frete_type == "Aéreo":
        frete_data.update({
            "taxa_awb_aereo": st.session_state.taxa_awb_aereo,
            "dta_aereo": st.session_state.dta_aereo,
            "agency_fee_aereo": st.session_state.agency_fee_aereo,
            "chd_aereo": st.session_state.chd_aereo,
            "iof_aereo_usd": iof_usd_val,
            "total_aereo_brl": total_calculated_brl,
            # Campos marítimos zerados para consistência
            "frete_bl_maritimo": 0.0,
            "thc_maritimo": 0.0,
            "taxas_destino_dolar_maritimo": 0.0,
            "taxas_destino_real_maritimo": 0.0,
            "agency_fee_maritimo": 0.0,
            "iof_maritimo_usd": 0.0,
            "total_maritimo_brl": 0.0
        })
    elif frete_type == "Marítimo":
        frete_data.update({
            "frete_bl_maritimo": st.session_state.frete_bl_maritimo,
            "thc_maritimo": st.session_state.thc_maritimo, 
            "taxas_destino_dolar_maritimo": st.session_state.taxas_destino_dolar_maritimo,
            "taxas_destino_real_maritimo": st.session_state.taxas_destino_real_maritimo,
            "agency_fee_maritimo": st.session_state.agency_fee_maritimo,
            "iof_maritimo_usd": iof_usd_val,
            "total_maritimo_brl": total_calculated_brl,
            # Campos aéreos zerados para consistência
            "taxa_awb_aereo": 0.0,
            "dta_aereo": 0.0,
            "agency_fee_aereo": 0.0,
            "chd_aereo": 0.0,
            "iof_aereo_usd": 0.0,
            "total_aereo_brl": 0.0
        })
    
    if inserir_ou_atualizar_frete_internacional(frete_data):
        st.success(f"Cálculo de frete {frete_type} para a referência '{referencia_processo}' salvo/atualizado com sucesso!")
        st.toast(f"✅ Cálculo salvo!", icon="✅")
        sleep (1.5) # Pausa para o usuário ver a mensagem
        return True
    else:
        st.error(f"Falha ao salvar/atualizar cálculo de frete {frete_type} para a referência '{referencia_processo}'.")
        return False

# NOVO: Função para carregar o frete internacional do banco de dados
def _load_frete_internacional():
    referencia_processo = st.session_state.get('referencia_pch', '').strip()
    
    # Não tenta carregar se a referência estiver vazia ou com o valor padrão inicial
    if not referencia_processo or referencia_processo == "PCH-":
        return

    existing_frete_data = get_frete_internacional_by_referencia(referencia_processo)

    if existing_frete_data:
        st.info(f"Dados de frete para a referência '{referencia_processo}' carregados. Tipo: {existing_frete_data['tipo_frete']}.")
        
        # Atualiza o tipo de frete selecionado na UI
        st.session_state.frete_type_select = existing_frete_data.get('tipo_frete', 'Aéreo')

        # Atualiza o dólar de venda (abertura) editável
        st.session_state.dolar_venda_abertura_editable = existing_frete_data.get('dolar_cotacao_usado', 0.0)

        # Atualiza o frete Aéreo
        st.session_state.taxa_awb_aereo = existing_frete_data.get('taxa_awb_aereo', 0.0)
        st.session_state.dta_aereo = existing_frete_data.get('dta_aereo', 0.0)
        st.session_state.agency_fee_aereo = existing_frete_data.get('agency_fee_aereo', 0.0)
        st.session_state.chd_aereo = existing_frete_data.get('chd_aereo', 0.0)
        # O total_comparacao é setado como o total_aereo_brl salvo, para que a diferença seja 0 inicialmente
        st.session_state.total_comparacao_aereo = existing_frete_data.get('total_aereo_brl', 0.0) 

        # Atualiza o frete Marítimo
        st.session_state.frete_bl_maritimo = existing_frete_data.get('frete_bl_maritimo', 0.0)
        st.session_state.thc_maritimo = existing_frete_data.get('thc_maritimo', 0.0)
        st.session_state.taxas_destino_dolar_maritimo = existing_frete_data.get('taxas_destino_dolar_maritimo', 0.0)
        st.session_state.taxas_destino_real_maritimo = existing_frete_data.get('taxas_destino_real_maritimo', 0.0)
        st.session_state.agency_fee_maritimo = existing_frete_data.get('agency_fee_maritimo', 0.0)
        
        # NOVO: Recarrega a seção de e-mail com os valores gerados dinamicamente
        saudacao = _get_greeting()
        usuario_sistema = st.session_state.get('user_info', {}).get('username', 'Usuário do Sistema')

        # Gera o conteúdo padrão baseado nos dados carregados
        if existing_frete_data.get('tipo_frete') == "Aéreo":
            total_brl = existing_frete_data.get('total_aereo_brl', 0.0)
        else:
            total_brl = existing_frete_data.get('total_maritimo_brl', 0.0)

        iof_usd_val = existing_frete_data.get('iof_aereo_usd', 0.0) if existing_frete_data.get('tipo_frete') == "Aéreo" else existing_frete_data.get('iof_maritimo_usd', 0.0)

        email_subject_generated, email_body_plaintext_generated = _generate_frete_email_content(
            existing_frete_data.get('tipo_frete'), referencia_processo, total_brl, 
            iof_usd_val,
            existing_frete_data.get('dolar_cotacao_usado', 0.0), saudacao, usuario_sistema
        )

        # Atualiza os campos de e-mail para que reflitam os dados recarregados (e possam ser editados)
        # Note: O campo 'frete_email_to' é mantido para que o usuário não perca o último destinatário
        st.session_state['frete_email_subject_send'] = email_subject_generated
        st.session_state['frete_email_body_send'] = email_body_plaintext_generated
        
        # Força um re-render para que os campos sejam preenchidos
        st.rerun()


# NOVO: Função para gerar o conteúdo do e-mail de frete internacional
def _generate_frete_email_content(frete_type, referencia_digitada, total_brl, iof_usd, dolar_cotacao_usado, saudacao, usuario_sistema):
    email_subject = f"{referencia_digitada} - Pagamento de frete internacional Ethima"
    
    # Formatação dos valores para o corpo do e-mail
    total_brl_formatted = _format_currency(total_brl, prefix='R$ ')
    

    email_body_plaintext = f"""
{saudacao} Mayra,

Gentileza realizar depósito para a Ethima Logistics:
Processo: {referencia_digitada}
Valor total a depositar: {total_brl_formatted}
Serviço: Frete e taxas de embarque {frete_type}.


Chave PIX: financeiro@ethima.com.br
Favorecido: Ethima Comercio Exterior LTDA
Banco: Itaú Unibanco S.A. - 341
Agência: 8262
Conta: 41461-1
CNPJ: 21.129.987/0001-19

Conforme instruções em anexo.
Obs.: Invoice da importação em anexo.

Esta cobrança é válida para pagamento hoje, devido à taxa de conversão diária. Caso esta cobrança não seja paga nesta data, gentileza
solicitar ao nosso setor financeiro taxa cambial atualizada na data do pagamento.

Obrigado(a),
{usuario_sistema}
    """
    return email_subject, email_body_plaintext

# NOVO: Função para enviar e-mail com anexos (adaptada de outras telas)
def _send_email_with_attachments_frete_internacional(to_emails, subject, body, uploaded_files):
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
                # O arquivo uploaded_file é um objeto BytesIO. Precisamos garantir que ele esteja no início (seek(0)).
                uploaded_file.seek(0)
                part = MIMEBase("application", "octet-stream")
                part.set_payload(uploaded_file.read())
                encoders.encode_base64(part)
                part.add_header(
                    "Content-Disposition",
                    f"attachment; filename= {uploaded_file.name}",
                )
                msg.attach(part)
            except Exception as e:
                st.warning(f"Erro ao anexar o arquivo '{uploaded_file.name}': {e}. O e-mail será enviado sem este anexo.")

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(remetente, senha_aplicativo)
            smtp.send_message(msg)
        st.success("E-mail enviado com sucesso!")
        st.toast(f"✅ E-mail enviado com sucesso!", icon="📧")
        return True
    except KeyError as e:
        st.error(f"Credenciais de e-mail não configuradas nos segredos do Streamlit. Verifique a seção [gmail_credentials] e as chaves 'gmail_email' e 'gmail_app_password'. Erro: {e}")
        return False
    except Exception as e:
        st.error(f"Erro ao enviar o e-mail: {e}. Verifique se a 'senha de aplicativo' do Gmail está correta e se o acesso SMTP está liberado.")
        return False

# NOVO: Função para exibir a seção unificada de envio de e-mail
def _display_email_sending_section(frete_type, total_calculated_brl, iof_usd_val, dolar_cotacao_usado):
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
    
    st.markdown("---")
    st.markdown("#### Enviar E-mail e Salvar no Banco de Dados")

    # Preenche os campos do formulário de envio de e-mail
    saudacao = _get_greeting()
    usuario_sistema = st.session_state.get('user_info', {}).get('username', 'Usuário do Sistema')
    referencia_digitada = st.session_state.get('referencia_pch', 'PCH-XXXXX-XX')

    email_subject_generated, email_body_plaintext_generated = _generate_frete_email_content(
        frete_type, referencia_digitada, total_calculated_brl, iof_usd_val, dolar_cotacao_usado, saudacao, usuario_sistema
    )

    # Inicializa os valores no session_state para os widgets.
    # O setdefault garante que o valor seja definido APENAS na primeira execução
    st.session_state.setdefault('frete_email_to', "jjenessa23@gmail.com")
    # Se o subject ou body estiverem vazios (ex: após limpar os campos), preenche com o valor dinâmico
    st.session_state.setdefault('frete_email_subject_send', email_subject_generated)
    st.session_state.setdefault('frete_email_body_send', email_body_plaintext_generated)
    st.session_state.setdefault('frete_email_attachments_list', [])
    
    # NOVO AJUSTE DE RECARGA: Se o valor dinâmico gerado for diferente do que está no state, 
    # e o state estiver com o valor vazio (indicando que deve ser preenchido), atualiza
    if not st.session_state.frete_email_subject_send.strip():
         st.session_state.frete_email_subject_send = email_subject_generated
    if not st.session_state.frete_email_body_send.strip():
         st.session_state.frete_email_body_send = email_body_plaintext_generated


    # 1. Entrada do e-mail de destino (Para)
    st.text_input(
        "Para (e-mails separados por vírgula):",
        key="frete_email_to" # Usa a chave do session_state
        # O valor inicial é pego do st.session_state.setdefault acima.
    )
    # CORREÇÃO CRÍTICA: Adicionar verificação de None antes de chamar .strip()
    if st.session_state.get('frete_email_to') is not None and isinstance(st.session_state.frete_email_to, str):
        st.session_state.frete_email_to = st.session_state.frete_email_to.strip()
    # FIM DA CORREÇÃO


    # 2. Entrada do Assunto
    st.text_input(
        "Assunto:",
        key="frete_email_subject_send" # Usa a chave do session_state
        # O valor digitado persiste automaticamente via key
    )
    
    # 3. Entrada do Corpo do E-mail
    st.text_area(
        "Corpo do E-mail:",
        height=300,
        key="frete_email_body_send" # Usa a chave do session_state
        # O valor digitado persiste automaticamente via key
    )
    
    uploaded_files = st.file_uploader(
        "Arraste e solte ou selecione arquivos para anexar (múltiplos)",
        type=None,
        accept_multiple_files=True,
        key=f"frete_send_email_attachments_uploader_{frete_type}"
    )

    # Atualiza a lista de anexos se novos arquivos foram carregados
    if uploaded_files:
        # Quando o uploader é usado, ele substitui a lista anterior. 
        # Apenas garantir que o session_state reflita o upload mais recente
        st.session_state.frete_email_attachments_list = uploaded_files

    # Exibe os arquivos atualmente anexados (e permite remover)
    if st.session_state.frete_email_attachments_list:
        st.markdown("###### Arquivos anexados:")
        files_to_keep = []
        for i, file in enumerate(st.session_state.frete_email_attachments_list):
            col_file_name, col_remove_btn = st.columns([0.8, 0.2])
            with col_file_name:
                st.write(f"- **{file.name}**")
            with col_remove_btn:
                # O botão deve apenas marcar para exclusão, e a lista deve ser reconstruída.
                if st.button("Remover", key=f"frete_remove_attachment_{frete_type}_{i}"):
                    # Remove o arquivo do session_state e força um rerun
                    # Cria uma nova lista exceto o item removido
                    new_list = [f for idx, f in enumerate(st.session_state.frete_email_attachments_list) if idx != i]
                    st.session_state.frete_email_attachments_list = new_list
                    st.rerun()

    col1, col2 = st.columns([0.5, 0.5])
    with col1:
        # ATENÇÃO: Substituindo use_container_width=True por width='stretch' (depreciação)
        if st.button("Enviar E-mail e Salvar", key=f"frete_send_email_and_save_btn_{frete_type}", width='stretch'):
            if not st.session_state.frete_email_to:
                st.warning("Por favor, preencha o(s) destinatário(s) do e-mail.")
            else:
                list_of_recipients = [email.strip() for email in st.session_state.frete_email_to.split(',') if email.strip()]
                
                if list_of_recipients:
                    with st.spinner("Enviando e-mail e salvando no banco de dados..."):
                        # Captura o valor ATUALIZADO do corpo e assunto do e-mail
                        current_body = st.session_state.frete_email_body_send
                        current_subject = st.session_state.frete_email_subject_send
                        
                        email_sent_successfully = _send_email_with_attachments_frete_internacional(
                            to_emails=list_of_recipients,
                            subject=current_subject,
                            body=current_body,
                            uploaded_files=st.session_state.frete_email_attachments_list
                        )
                        
                        if email_sent_successfully:
                            # Prepara os valores para salvar no DB
                            if frete_type == "Aéreo":
                                # Recálculo da diferença e IOF Aéreo para garantir o valor exato no momento do clique
                                taxa_awb_brl = st.session_state.taxa_awb_aereo * (st.session_state.dolar_venda_abertura_editable * 1.03)
                                dta_brl = st.session_state.dta_aereo * (st.session_state.dolar_venda_abertura_editable * 1.03)
                                iof_aereo_calculated_usd = st.session_state.taxa_awb_aereo * 0.0038
                                iof_aereo_brl = iof_aereo_calculated_usd * (st.session_state.dolar_venda_abertura_editable * 1.03)

                                total_aereo_brl_calculated = (taxa_awb_brl + dta_brl + iof_aereo_brl + st.session_state.chd_aereo * (st.session_state.dolar_venda_abertura_editable * 1.03)) + st.session_state.agency_fee_aereo
                                diferenca_aereo = total_aereo_brl_calculated - st.session_state.total_comparacao_aereo
                                final_total_to_save = diferenca_aereo
                                final_iof_usd = iof_aereo_calculated_usd
                            else: # Marítimo
                                final_total_to_save = total_calculated_brl
                                final_iof_usd = iof_usd_val 
                            
                            _save_frete_internacional(
                                frete_type, 
                                final_total_to_save, 
                                final_iof_usd, 
                                dolar_cotacao_usado
                            )
                            
                    st.rerun()
                else:
                    st.warning("Nenhum destinatário válido encontrado.")

def show_calculo_frete_internacional_page():
    """
    Exibe a página de cálculo de Frete Internacional, com opções para Aéreo e Marítimo.
    """
    # Define o caminho da imagem de fundo
    background_image_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'assets', 'logo_navio_atracado.png')
    set_background_image(background_image_path)

    st.subheader("Cálculo Frete Internacional")

    # NOVO: Exibição do logo da Ethima
    app_root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    logo_ethima_path = os.path.join(app_root_dir, 'assets', 'ethima.png') # Assumindo ethima.png na pasta assets
    
        
            
    # Fetch dollar rates
    dolar_data = get_dolar_cotacao()
    
    # Cotações para cálculo Aéreo e Marítimo (Abertura Venda)
    dolar_venda_abertura_api = 0.0
    if dolar_data and dolar_data['abertura_venda'] != 'N/A':
        try:
            dolar_venda_abertura_api = float(dolar_data['abertura_venda'].replace(',', '.'))
        except ValueError:
            st.warning("Não foi possível converter a cotação de Abertura do dólar para cálculo. Usando 0.0.")

    # Inicializa o campo editável do dólar de venda (abertura) no session_state
    if 'dolar_venda_abertura_editable' not in st.session_state:
        st.session_state.dolar_venda_abertura_editable = dolar_venda_abertura_api


    # Exibir cotações do dólar no topo (APENAS ABERTURA)
    st.markdown("#### Cotação do Dólar para Cálculos")
    col_dv_abertura, col_dv3_abertura, col3 = st.columns([0.4,0.4,0.2])
    with col_dv_abertura:
        # Campo Dólar Venda (Abertura) agora é editável
        st.session_state.dolar_venda_abertura_editable = st.number_input(
            label="Dólar Venda (Abertura)",
            value=st.session_state.dolar_venda_abertura_editable,
            format="%.4f",
            key="dolar_venda_abertura_input",
            min_value=0.0
        )
    with col_dv3_abertura:
        # A cotação de Dólar + 3% deve usar o valor editável
        dolar_abertura_3_percent_calculated = st.session_state.dolar_venda_abertura_editable * 1.03
        st.metric(label="Dólar + 3% (Abertura)", 
              value=f"{dolar_abertura_3_percent_calculated:,.4f}".replace('.', '#').replace(',', '.').replace('#', ','))
    st.markdown("---")
    with col3:
        if os.path.exists(logo_ethima_path):
            try:
                # Tenta abrir o arquivo
                with open(logo_ethima_path, "rb") as f:
                    # Lê o conteúdo
                    image_data = f.read()
                    # Codifica para Base64
                    encoded = base64.b64encode(image_data).decode()
                    # Cria a URI de dados
                    data_uri = f"data:image/png;base64,{encoded}"
                    # Exibe a imagem usando a URI de dados
                    st.image(data_uri, width=150, caption="Ethima")
            except Exception as e:
                st.warning(f"Erro ao carregar o logo da Ethima: {e}")
        else:
            st.warning(f"Logo da Ethima não encontrada. Verifique o caminho do arquivo: {logo_ethima_path}. Existe? {os.path.exists(logo_ethima_path)}") # Adicionado depuração
    # Campo de referência PCH-*****
    # Pré-preencher o campo de referência
    if 'referencia_pch' not in st.session_state:
        st.session_state.referencia_pch = "PCH-"
    
    # NOVO: Adicionado um callback para carregar os dados do frete quando a referência for alterada
    referencia_input = st.text_input(
        "Referência (Ex: PCH-*****)", 
        key="referencia_pch", 
        value=st.session_state.referencia_pch,
        on_change=_load_frete_internacional # Chama a função de carregamento ao mudar
    )


    # Select box for freight type
    col1, col2 = st.columns([1, 3])  # Proporção 1:2
    with col1:
        # O valor inicial do selectbox deve vir do session_state, que é atualizado pela função de carregamento
        frete_type = st.selectbox(
        "Selecione o Tipo de Frete",
        ("Aéreo", "Marítimo"),
        key="frete_type_select"
    )

    if frete_type == "Aéreo":
        st.markdown("##### Detalhes do Frete Aéreo")
        
        # Inicializa valores no session state se ainda não existirem, com valores padrão
        if 'taxa_awb_aereo' not in st.session_state:
            st.session_state.taxa_awb_aereo = 0.0
        if 'dta_aereo' not in st.session_state:
            st.session_state.dta_aereo = 0.0
        if 'agency_fee_aereo' not in st.session_state:
            st.session_state.agency_fee_aereo = 150.0 # Pré-preenchido
        if 'chd_aereo' not in st.session_state:
            st.session_state.chd_aereo = 40.0 # Pré-preenchido
        if 'total_comparacao_aereo' not in st.session_state:
            st.session_state.total_comparacao_aereo = 0.0
            
        # Calcula Frete Aéreo
        taxa_awb_brl = st.session_state.taxa_awb_aereo * dolar_abertura_3_percent_calculated
        dta_brl = st.session_state.dta_aereo * dolar_abertura_3_percent_calculated
        
        # Cálculo do IOF (0.38% sobre Taxa AWB)
        iof_aereo_calculated_usd = st.session_state.taxa_awb_aereo * 0.0038
        iof_aereo_brl = iof_aereo_calculated_usd * dolar_abertura_3_percent_calculated

        # Cálculo do Total
        # CHD e Taxas de AWB/DTA (DTA e AWB são em dólar e são convertidos com o dólar de venda + 3%)
        # CHD (Cargo Handling) também é em dólar e convertido
        total_aereo_brl_calculated = (taxa_awb_brl + dta_brl + iof_aereo_brl + st.session_state.chd_aereo * dolar_abertura_3_percent_calculated) + st.session_state.agency_fee_aereo
        
        diferenca_aereo = total_aereo_brl_calculated - st.session_state.total_comparacao_aereo

        col_awb, col_dta = st.columns(2)
        with col_awb:
            st.session_state.taxa_awb_aereo = st.number_input(
                "Taxa AWB ($)", 
                value=st.session_state.taxa_awb_aereo, 
                key="awb_aereo_input", 
                min_value=0.0, 
                format="%.4f"
            )
        with col_dta:
            st.session_state.dta_aereo = st.number_input(
                "DTA ($)", 
                value=st.session_state.dta_aereo, 
                key="dta_aereo_input", 
                min_value=0.0, 
                format="%.4f"
            )

        col_agency, col_chd = st.columns(2)
        with col_agency:
            st.session_state.agency_fee_aereo = st.number_input(
                "Agency Fee (R$)", 
                value=st.session_state.agency_fee_aereo, 
                key="agency_fee_aereo_input", 
                min_value=0.0, 
                format="%.2f" # Agency Fee é em R$
            )
        with col_chd:
            st.session_state.chd_aereo = st.number_input(
                "CHD ($)", 
                value=st.session_state.chd_aereo, 
                key="chd_aereo_input", 
                min_value=0.0, 
                format="%.4f"
            )

        st.markdown("###### Comparação e Total A Pagar")
        st.session_state.total_comparacao_aereo = st.number_input(
            "Total Anterior/Comparação (R$)", 
            value=st.session_state.total_comparacao_aereo, 
            key="total_comparacao_aereo_input", 
            min_value=0.0, 
            format="%.2f" # Comparação é em R$
        )

        col_desc, col_usd, col_brl = st.columns([0.4, 0.3, 0.3])
        col_desc.markdown("**Descrição**")
        col_usd.markdown("**Valor ($)**")
        col_brl.markdown("**Valor (R$)**")
        st.markdown("---")
        
        col_desc.write("Taxa AWB")
        col_usd.write(f"{st.session_state.taxa_awb_aereo:,.4f}".replace('.', '#').replace(',', '.').replace('#', ','))
        col_brl.write(_format_currency(taxa_awb_brl, prefix="R$ "))

        col_desc.write("DTA")
        col_usd.write(f"{st.session_state.dta_aereo:,.4f}".replace('.', '#').replace(',', '.').replace('#', ','))
        col_brl.write(_format_currency(dta_brl, prefix="R$ "))
        
        col_desc.write("CHD")
        col_usd.write(f"{st.session_state.chd_aereo:,.4f}".replace('.', '#').replace(',', '.').replace('#', ','))
        col_brl.write(_format_currency(st.session_state.chd_aereo * dolar_abertura_3_percent_calculated, prefix="R$ "))
        
        col_desc.write("IOF (0.38% sobre AWB)")
        col_usd.write(f"{iof_aereo_calculated_usd:,.4f}".replace('.', '#').replace(',', '.').replace('#', ','))
        col_brl.write(_format_currency(iof_aereo_brl, prefix="R$ "))

        col_desc.write("Agency Fee (R$)")
        col_usd.write("N/A")
        col_brl.write(_format_currency(st.session_state.agency_fee_aereo, prefix="R$ "))

        st.markdown("---")
        
        st.metric(label="TOTAL CALCULADO (R$)", value=_format_currency(total_aereo_brl_calculated, prefix="R$ "))
        st.metric(label="DIFERENÇA (TOTAL CALCULADO - TOTAL ANTERIOR) (R$)", value=_format_currency(diferenca_aereo, prefix="R$ "))

        col_buttons_aereo = st.columns(3)
        with col_buttons_aereo[0]:
            # Usa a função de callback _clear_aereo_fields para resetar os valores
            st.button("LIMPAR Aéreo", key="clear_aereo", on_click=_clear_aereo_fields, width='stretch')
        
        # NOVO: Botão para Salvar Frete Aéreo
        with col_buttons_aereo[1]:
            if st.button("Salvar Frete Aéreo", key="save_aereo", width='stretch'):
                _save_frete_internacional(
                    "Aéreo", 
                    diferenca_aereo, # Salva a diferença para Aéreo
                    iof_aereo_calculated_usd,
                    st.session_state.dolar_venda_abertura_editable
                )
        with col_buttons_aereo[2]:
            st.button("LIMPAR E-MAIL", key="clear_email_aereo", on_click=_clear_email_fields, width='stretch')

        # Chamada para a nova seção unificada de envio de e-mail
        _display_email_sending_section(
            frete_type, 
            diferenca_aereo, # Passa a diferença como o total a pagar para Aéreo
            iof_aereo_calculated_usd,
            st.session_state.dolar_venda_abertura_editable
        )


    elif frete_type == "Marítimo":
        st.markdown("##### Detalhes do Frete Marítimo")

        # Inicializa valores no session state se ainda não existirem, com valores padrão
        if 'frete_bl_maritimo' not in st.session_state:
            st.session_state.frete_bl_maritimo = 0.0
        if 'thc_maritimo' not in st.session_state:
            st.session_state.thc_maritimo = 0.0
        if 'taxas_destino_dolar_maritimo' not in st.session_state:
            st.session_state.taxas_destino_dolar_maritimo = 0.0
        if 'taxas_destino_real_maritimo' not in st.session_state:
            st.session_state.taxas_destino_real_maritimo = 0.0
        if 'agency_fee_maritimo' not in st.session_state:
            st.session_state.agency_fee_maritimo = 0.0 # Pré-preenchido

        # Cálculo do IOF (0.38% sobre Frete BL)
        iof_maritimo_calculated_usd = st.session_state.frete_bl_maritimo * 0.0038
        
        # Conversão de Dólar para Real
        frete_bl_brl = st.session_state.frete_bl_maritimo * dolar_abertura_3_percent_calculated
        thc_brl = st.session_state.thc_maritimo * dolar_abertura_3_percent_calculated
        taxas_destino_dolar_brl = st.session_state.taxas_destino_dolar_maritimo * dolar_abertura_3_percent_calculated
        iof_maritimo_brl = iof_maritimo_calculated_usd * dolar_abertura_3_percent_calculated

        # Cálculo do Total
        total_maritimo_brl_calculated = (
            frete_bl_brl + 
            thc_brl + 
            taxas_destino_dolar_brl + 
            st.session_state.taxas_destino_real_maritimo + 
            st.session_state.agency_fee_maritimo + 
            iof_maritimo_brl
        )

        col_bl, col_thc = st.columns(2)
        with col_bl:
            st.session_state.frete_bl_maritimo = st.number_input(
                "Frete BL ($)", 
                value=st.session_state.frete_bl_maritimo, 
                key="frete_bl_maritimo_input", 
                min_value=0.0, 
                format="%.4f"
            )
        with col_thc:
            st.session_state.thc_maritimo = st.number_input(
                "THC ($)", 
                value=st.session_state.thc_maritimo, 
                key="thc_maritimo_input", 
                min_value=0.0, 
                format="%.4f"
            )
            
        col_taxas_dolar, col_taxas_real = st.columns(2)
        with col_taxas_dolar:
            st.session_state.taxas_destino_dolar_maritimo = st.number_input(
                "Taxas Destino ($)", 
                value=st.session_state.taxas_destino_dolar_maritimo, 
                key="taxas_destino_dolar_maritimo_input", 
                min_value=0.0, 
                format="%.4f"
            )
        with col_taxas_real:
            st.session_state.taxas_destino_real_maritimo = st.number_input(
                "Taxas Destino (R$)", 
                value=st.session_state.taxas_destino_real_maritimo, 
                key="taxas_destino_real_maritimo_input", 
                min_value=0.0, 
                format="%.2f"
            )
        
        st.session_state.agency_fee_maritimo = st.number_input(
                "Agency Fee (R$)", 
                value=st.session_state.agency_fee_maritimo, 
                key="agency_fee_maritimo_input", 
                min_value=0.0, 
                format="%.2f"
            )

        st.markdown("###### Detalhamento do Cálculo (R$)")
        col_desc, col_usd, col_brl = st.columns([0.4, 0.3, 0.3])
        col_desc.markdown("**Descrição**")
        col_usd.markdown("**Valor ($)**")
        col_brl.markdown("**Valor (R$)**")
        st.markdown("---")
        
        col_desc.write("Frete BL")
        col_usd.write(f"{st.session_state.frete_bl_maritimo:,.4f}".replace('.', '#').replace(',', '.').replace('#', ','))
        col_brl.write(_format_currency(frete_bl_brl, prefix="R$ "))

        col_desc.write("THC")
        col_usd.write(f"{st.session_state.thc_maritimo:,.4f}".replace('.', '#').replace(',', '.').replace('#', ','))
        col_brl.write(_format_currency(thc_brl, prefix="R$ "))
        
        col_desc.write("Taxas Destino ($)")
        col_usd.write(f"{st.session_state.taxas_destino_dolar_maritimo:,.4f}".replace('.', '#').replace(',', '.').replace('#', ','))
        col_brl.write(_format_currency(taxas_destino_dolar_brl, prefix="R$ "))
        
        col_desc.write("Taxas Destino (R$)")
        col_usd.write("N/A")
        col_brl.write(_format_currency(st.session_state.taxas_destino_real_maritimo, prefix="R$ "))

        col_desc.write("IOF (0.38% sobre BL)")
        col_usd.write(f"{iof_maritimo_calculated_usd:,.4f}".replace('.', '#').replace(',', '.').replace('#', ','))
        col_brl.write(_format_currency(iof_maritimo_brl, prefix="R$ "))

        col_desc.write("Agency Fee (R$)")
        col_usd.write("N/A")
        col_brl.write(_format_currency(st.session_state.agency_fee_maritimo, prefix="R$ "))

        st.markdown("---")
        st.metric(label="TOTAL (R$)", value=_format_currency(total_maritimo_brl_calculated, prefix="R$ "))

        col_buttons_maritimo = st.columns(3)
        with col_buttons_maritimo[0]:
            # Usa a função de callback _clear_maritimo_fields para resetar os valores
            st.button("LIMPAR Marítimo", key="clear_maritimo", on_click=_clear_maritimo_fields, width='stretch')
        
        # NOVO: Botão para Salvar Frete Marítimo
        with col_buttons_maritimo[1]:
            if st.button("Salvar Frete Marítimo", key="save_maritimo", width='stretch'):
                _save_frete_internacional(
                    "Marítimo", 
                    total_maritimo_brl_calculated, 
                    iof_maritimo_calculated_usd,
                    st.session_state.dolar_venda_abertura_editable
                )
        with col_buttons_maritimo[2]:
            st.button("LIMPAR E-MAIL", key="clear_email_maritimo", on_click=_clear_email_fields, width='stretch')

        # Chamada para a nova seção unificada de envio de e-mail
        _display_email_sending_section(
            frete_type, 
            total_maritimo_brl_calculated, 
            iof_maritimo_calculated_usd,
            st.session_state.dolar_venda_abertura_editable
        )
