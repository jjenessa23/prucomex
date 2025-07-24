import streamlit as st
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
import logging
from datetime import datetime, timedelta
import pandas as pd
from typing import Dict, List, Any

# Importar funções do módulo de utilitários de banco de dados
import app_logic.db_utils as db_utils
import app_logic.db_cotacao_frete as db_cotacao_frete # Novo módulo de DB para cotação de frete
from app_logic.utils import set_background_image

# Configuração de logging para este módulo
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# --- Funções de Lógica de Negócio ---

def send_quotation_request_email(request_details: Dict[str, Any], agent_email: str, agent_username: str):
    """
    Envia um e-mail com a solicitação de cotação para o agente de carga.
    O e-mail contém um link para a página de inserção de cotação.
    """
    try:
        # Usar st.secrets para acessar as credenciais de e-mail
        sender_email = st.secrets["email"]["sender_email"]
        sender_password = st.secrets["email"]["sender_password"]
        smtp_server = st.secrets["email"]["smtp_server"]
        smtp_port = int(st.secrets["email"]["smtp_port"])

        if not sender_email or not sender_password:
            st.error("Erro: Credenciais de e-mail não configuradas. Verifique as variáveis em secrets.toml na seção [email].")
            logger.error("Credenciais de e-mail não configuradas.")
            return False

        msg = MIMEMultipart("alternative")
        # Título do e-mail alterado para incluir países de origem e destino
        msg["Subject"] = f"Solicitação de Cotação de Frete Internacional - {request_details['origem_pais']} - {request_details['destino_pais']}"
        msg["From"] = sender_email
        msg["To"] = agent_email # Envia para o agente de carga

        # Gerar um link para a página de inserção de cotação.
        # O agente de carga terá que fazer login na página de inserção de cotação.
        quotation_link = (
            f"https://prucomexv.streamlit.app/"
        )

        # Construir o conteúdo específico do transporte para o e-mail
        transport_details_text = ""
        transport_details_html = ""
        if request_details.get('tipo_transporte') == "Marítimo":
            transport_details_text += f"""
        Tipo de Carga: {request_details.get('tipo_carga', 'N/A')}
        Quantidade de Containers: {request_details.get('qtd_containers', 'N/A')}"""
            transport_details_html += f"""
                    <li><b>Tipo de Carga:</b> {request_details.get('tipo_carga', 'N/A')}</li>
                    <li><b>Quantidade de Containers:</b> {request_details.get('qtd_containers', 'N/A')}</li>"""
        elif request_details.get('tipo_transporte') == "Aéreo":
            transport_details_text += f"""
        Peso (kg): {request_details.get('peso_kg', 'N/A')}"""
            transport_details_html += f"""
                    <li><b>Peso (kg):</b> {request_details.get('peso_kg', 'N/A')}</li>"""


        text_content = f"""
        Prezado(a) Agente de Carga,

        Recebemos uma nova solicitação de cotação de frete internacional com os seguintes detalhes:

        ID da Solicitação: {request_details['id']}
        Origem: {request_details['origem_cidade']}, {request_details['origem_pais']}
        Destino: {request_details['destino_cidade']}, {request_details['destino_pais']}
        Tipo de Transporte: {request_details.get('tipo_transporte', 'N/A')}
        Incoterm: {request_details['incoterm']}
        {transport_details_text}

        Por favor, acesse o link abaixo para inserir sua cotação:
        {quotation_link}

        Seu login é: {agent_username}
        Por favor, use sua senha cadastrada.

        Agradecemos sua atenção.

        Atenciosamente,
        Equipe de Gerenciamento COMEX
        """

        html_content = f"""
        <html>
            <body>
                <p>Prezado(a) Agente de Carga,</p>
                <p>Recebemos uma nova solicitação de cotação de frete internacional com os seguintes detalhes:</p>
                <ul>
                    <li><b>ID da Solicitação:</b> {request_details['id']}</li>
                    <li><b>Origem:</b> {request_details['origem_cidade']}, {request_details['origem_pais']}</li>
                    <li><b>Destino:</b> {request_details['destino_cidade']}, {request_details['destino_pais']}</li>
                    <li><b>Tipo de Transporte:</b> {request_details.get('tipo_transporte', 'N/A')}</li>
                    <li><b>Incoterm:</b> {request_details['incoterm']}</li>
                    {transport_details_html}
                </ul>
                <p>Por favor, acesse o link abaixo para inserir sua cotação:</p>
                <p><a href="{quotation_link}">Inserir Cotação</a></p>
                <p>Seu login é: <b>{agent_username}</b></p>
                <p>Por favor, use sua senha cadastrada.</p>
                <p>Agradecemos sua atenção.</p>
                <p>Atenciosamente,<br>Equipe de Gerenciamento COMEX</p>
            </body>
        </html>
        """

        part1 = MIMEText(text_content, "plain")
        part2 = MIMEText(html_content, "html")

        msg.attach(part1)
        msg.attach(part2)

        # Usar SMTP_SSL para porta 465, ou SMTP com starttls para outras portas
        if smtp_port == 465:
            server = smtplib.SMTP_SSL(smtp_server, smtp_port)
        else:
            server = smtplib.SMTP(smtp_server, smtp_port)
            server.starttls() # Inicia TLS se não for SMTP_SSL
        
        with server: # Usa 'with' para garantir que o servidor seja fechado
            server.login(sender_email, sender_password)
            server.sendmail(sender_email, agent_email, msg.as_string())
        logger.info(f"E-mail de solicitação de cotação enviado para {agent_email} (Solicitação ID: {request_details['id']}).")
        return True
    except Exception as e:
        logger.error(f"Erro ao enviar e-mail de solicitação de cotação para {agent_email}: {e}")
        st.error(f"Erro ao enviar e-mail para {agent_email}. Verifique as configurações de e-mail e tente novamente.")
        return False

# --- Funções de UI (Streamlit) ---

def show_cotacao_frete_page():
    background_image_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'assets', 'logo_navio_atracado.png')
    set_background_image(background_image_path)

    st.title("Cotação de Frete Internacional")

    st.markdown("---")
    st.subheader("Solicitar Nova Cotação")

    # Inicializa o estado para o tipo de transporte se não existir
    if "tipo_transporte_selection" not in st.session_state:
        st.session_state.tipo_transporte_selection = "Marítimo"

    # Seletor de tipo de transporte (FORA DO FORMULÁRIO)
    tipo_transporte_selected = st.selectbox(
        "Tipo de Transporte",
        ["Marítimo", "Aéreo"],
        key="tipo_transporte_selector"
    )
    
    # Atualiza o session_state e força um rerun SE o valor mudou
    if tipo_transporte_selected != st.session_state.tipo_transporte_selection:
        st.session_state.tipo_transporte_selection = tipo_transporte_selected
        st.rerun() # Força um rerun para renderizar os campos corretos

    # Usa o valor do session_state para controlar a renderização condicional
    current_tipo_transporte = st.session_state.tipo_transporte_selection

    with st.form("solicitar_cotacao_form"):
        col1, col2 = st.columns(2)
        with col1:
            origem_full = st.text_input("Origem (Cidade, País)", help="Ex: Xangai, China", key="origem_full")
        with col2:
            destino_full = st.text_input("Destino (Cidade, País)", help="Ex: Santos, Brasil", key="destino_full")

        # Campos condicionais baseados no tipo de transporte
        tipo_carga = None
        incoterm = None
        qtd_containers = None
        peso_kg = None

        if current_tipo_transporte == "Marítimo":
            col_maritimo_1, col_maritimo_2 = st.columns(2)
            with col_maritimo_1:
                tipo_carga = st.selectbox("Tipo de Carga", ["FCL", "LCL", "Granel", "Projeto"], key="tipo_carga_maritimo")
                incoterm = st.selectbox("Incoterm", ["EXW", "FOB", "CIF", "DDP"], key="incoterm_maritimo")
            with col_maritimo_2:
                qtd_containers = st.number_input("Quantidade de Containers", min_value=1, value=1, step=1, key="qtd_containers_maritimo")
        elif current_tipo_transporte == "Aéreo":
            col_aereo_1, col_aereo_2 = st.columns(2)
            with col_aereo_1:
                peso_kg = st.number_input("Peso (kg)", min_value=0.01, format="%.2f", key="peso_aereo")
            with col_aereo_2:
                incoterm = st.selectbox("Incoterm", ["EXW", "FOB", "CIF", "DDP"], key="incoterm_aereo")


        st.markdown("---")
        st.subheader("Selecionar Agentes de Carga para Enviar Cotação")

        # Carregar agentes de carga do banco de dados (agora todos os agentes em 'users' com is_freight_agent=True)
        agents = db_cotacao_frete.get_all_freight_agents()
        agent_options = {agent['username']: agent for agent in agents}
        
        if not agents:
            st.warning("Nenhum agente de carga cadastrado. Por favor, cadastre agentes na tela 'Gerenciamento de Usuários'.")
            st.form_submit_button("Solicitar Cotações", disabled=True)
        else:
            selected_agents_usernames = st.multiselect(
                "Selecione os agentes de carga para enviar a solicitação:",
                options=list(agent_options.keys()),
                key="selected_agents_for_quotation"
            )

            submitted = st.form_submit_button("Solicitar Cotações")

            if submitted:
                # Extrair cidade e país da origem e destino
                origem_partes = [p.strip() for p in origem_full.split(',')]
                destino_partes = [p.strip() for p in destino_full.split(',')]

                origem_cidade = origem_partes[0] if len(origem_partes) > 0 else ""
                origem_pais = origem_partes[1] if len(origem_partes) > 1 else ""
                
                destino_cidade = destino_partes[0] if len(destino_partes) > 0 else ""
                destino_pais = destino_partes[1] if len(destino_partes) > 1 else ""

                if not origem_cidade or not origem_pais or not destino_cidade or not destino_pais:
                    st.error("Por favor, preencha a Origem e o Destino no formato 'Cidade, País'.")
                elif current_tipo_transporte == "Aéreo" and (peso_kg is None or peso_kg <= 0):
                    st.error("Por favor, preencha o Peso para frete Aéreo.")
                elif current_tipo_transporte == "Marítimo" and (tipo_carga is None or qtd_containers is None or qtd_containers <= 0):
                    st.error("Por favor, preencha o Tipo de Carga e a Quantidade de Containers para frete Marítimo.")
                elif not selected_agents_usernames:
                    st.error("Por favor, selecione pelo menos um agente de carga para enviar a solicitação.")
                else:
                    # Gerar ID da solicitação com base na data e hora (formatoABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789)
                    request_id = datetime.now().strftime("%Y%m%d%H%M%S%f")
                    
                    request_details = {
                        "id": request_id, # Usar o ID gerado
                        "origem_cidade": origem_cidade,
                        "origem_pais": origem_pais,
                        "destino_cidade": destino_cidade,
                        "destino_pais": destino_pais,
                        "tipo_transporte": current_tipo_transporte, # Usar o valor do session_state
                        "incoterm": incoterm,
                        "status": "Pendente",
                        "data_solicitacao": datetime.now().isoformat(),
                        "agentes_enviados": selected_agents_usernames
                    }
                    
                    if current_tipo_transporte == "Marítimo":
                        request_details["tipo_carga"] = tipo_carga
                        request_details["qtd_containers"] = qtd_containers
                    elif current_tipo_transporte == "Aéreo":
                        request_details["peso_kg"] = peso_kg

                    # Salvar a solicitação no banco de dados
                    if db_cotacao_frete.add_quotation_request(request_details): # Passa o request_details completo
                        st.success(f"Solicitação de cotação enviada com sucesso! ID: {request_id}")
                        
                        # Enviar e-mails para os agentes selecionados
                        emails_sent = 0
                        for username in selected_agents_usernames:
                            agent_data = agent_options[username]
                            # Passa apenas o username e email
                            if send_quotation_request_email(request_details, agent_data['email'], agent_data['username']):
                                emails_sent += 1
                        
                        if emails_sent > 0:
                            st.success(f"{emails_sent} e-mail(s) de solicitação enviado(s) com sucesso aos agentes selecionados.")
                        else:
                            st.warning("Nenhum e-mail foi enviado. Verifique as configurações de e-mail e se os agentes têm e-mail cadastrado.")
                    else:
                        st.error("Erro ao salvar a solicitação de cotação no banco de dados.")
    
    st.markdown("---")
    st.subheader("Solicitações de Cotação Atuais")

    # Exibir solicitações de cotação existentes
    quotation_requests = db_cotacao_frete.get_all_quotation_requests()

    # Inicializa o estado para mensagens de exclusão
    if 'delete_status_message' not in st.session_state:
        st.session_state.delete_status_message = ""
    if 'delete_status_type' not in st.session_state:
        st.session_state.delete_status_type = ""
    # NOVO: Inicializa o conjunto de IDs de solicitações a serem ocultadas
    if 'hidden_requests' not in st.session_state:
        st.session_state.hidden_requests = set()

    # Exibe a mensagem de status de exclusão, se houver
    if st.session_state.delete_status_message:
        if st.session_state.delete_status_type == "success":
            st.success(st.session_state.delete_status_message)
        elif st.session_state.delete_status_type == "error":
            st.error(st.session_state.delete_status_message)
        # Limpa a mensagem após exibir
        st.session_state.delete_status_message = ""
        st.session_state.delete_status_type = ""


    if quotation_requests:
        # Ordenar as solicitações pela data de solicitação (mais recente primeiro)
        quotation_requests.sort(key=lambda x: x.get('data_solicitacao', ''), reverse=True)

        # Filtrar as solicitações que devem ser ocultadas
        filtered_requests = [
            req for req in quotation_requests 
            if req.get('id') not in st.session_state.hidden_requests
        ]

        if not filtered_requests:
            st.info("Nenhuma solicitação de cotação encontrada.")
            return # Sai da função se não houver solicitações para exibir

        for req in filtered_requests: # Itera sobre as solicitações filtradas
            with st.container(border=True): # Container para simular um card
                col_display_1, col_display_2, col_display_3 = st.columns(3)

                with col_display_1:
                    st.markdown(f"**ID da Solicitação:** `{req.get('id', 'N/A')}`")
                    st.write(f"**Origem:** {req.get('origem_cidade', 'N/A')}, {req.get('origem_pais', 'N/A')}")
                    st.write(f"**Destino:** {req.get('destino_cidade', 'N/A')}, {req.get('destino_pais', 'N/A')}")
                
                with col_display_2:
                    st.write(f"**Tipo de Transporte:** {req.get('tipo_transporte', 'N/A')}")
                    if req.get('tipo_transporte') == "Marítimo":
                        st.write(f"**Tipo de Carga:** {req.get('tipo_carga', 'N/A')}")
                        st.write(f"**Quantidade de Containers:** {req.get('qtd_containers', 'N/A')}")
                    elif req.get('tipo_transporte') == "Aéreo":
                        st.write(f"**Peso (kg):** {req.get('peso_kg', 'N/A')}")
                    st.write(f"**Incoterm:** {req.get('incoterm', 'N/A')}")

                with col_display_3:
                    st.write(f"**Status:** {req.get('status', 'N/A')}")
                    st.write(f"**Data da Solicitação:** {datetime.fromisoformat(req['data_solicitacao']).strftime('%d/%m/%Y %H:%M') if req.get('data_solicitacao') else 'N/A'}")
                    st.write(f"**Agentes Enviados:** {', '.join(req.get('agentes_enviados', []))}")

                col_actions, _ = st.columns([1, 4]) # Usar colunas para alinhar o popover
                with col_actions:
                    # Usar um popover para as opções
                    with st.popover("Opções", use_container_width=True):
                        # Botão para Visualizar Respostas
                        view_responses_key = f"view_responses_{req['id']}"
                        if st.button("Visualizar Respostas", key=view_responses_key, use_container_width=True):
                            # Alternar a exibição das respostas para esta solicitação específica
                            if f'show_responses_{req["id"]}' not in st.session_state:
                                st.session_state[f'show_responses_{req["id"]}'] = True
                            else:
                                st.session_state[f'show_responses_{req["id"]}'] = not st.session_state[f'show_responses_{req["id"]}']
                            st.rerun()

                        st.markdown("---") # Separador no popover

                        # Botão para Excluir Solicitação
                        delete_key = f"delete_request_{req['id']}"
                        if st.button("Ocultar Solicitação", key=delete_key, use_container_width=True): # Texto alterado para "Ocultar"
                            # Adiciona uma confirmação antes de excluir
                            st.session_state[f'confirm_delete_{req["id"]}'] = True
                            st.info("Clique em 'Confirmar Ocultar' abaixo para remover da tela.") # Texto alterado
                            st.rerun() # Força um rerun para exibir o botão de confirmação

                # Lógica para o botão de confirmação de exclusão (fora do popover, mas dentro do container do card)
                if st.session_state.get(f'confirm_delete_{req["id"]}', False):
                    st.warning(f"Tem certeza que deseja ocultar a solicitação `{req['id']}` da tela?")
                    confirm_delete_button_key = f"execute_delete_{req['id']}"
                    if st.button("Confirmar Ocultar", key=confirm_delete_button_key, use_container_width=True):
                        logger.info(f"Ocultando solicitação ID: {req['id']} da tela.")
                        # Adiciona o ID da solicitação ao conjunto de solicitações ocultas
                        st.session_state.hidden_requests.add(req['id'])
                        st.session_state.delete_status_message = f"Solicitação ID `{req['id']}` oculta da tela com sucesso."
                        st.session_state.delete_status_type = "success"
                        
                        # Limpa o estado de confirmação para que o botão não apareça novamente
                        st.session_state[f'confirm_delete_{req["id"]}'] = False
                        st.rerun() # Atualiza a página para remover o card oculto e exibir a mensagem de status

                # Exibir respostas se a flag estiver ativada para esta solicitação
                if st.session_state.get(f'show_responses_{req["id"]}', False):
                    st.markdown("---")
                    st.subheader(f"Respostas para Solicitação `{req['id']}`")
                    responses = db_cotacao_frete.get_quotations_for_request(req['id'])
                    if responses:
                        df_responses = pd.DataFrame(responses)
                        # Formatar datas para exibição
                        df_responses['data_envio_fmt'] = df_responses['data_envio'].apply(
                            lambda x: datetime.fromisoformat(x).strftime('%d/%m/%Y %H:%M') if x else 'N/A'
                        )
                        df_responses['validade_cotacao_fmt'] = df_responses['validade_cotacao'].apply(
                            lambda x: datetime.fromisoformat(x).strftime('%d/%m/%Y') if x else 'N/A'
                        )
                        
                        # Adicionar coluna transit_time e free_time se existirem
                        if 'transit_time' not in df_responses.columns:
                            df_responses['transit_time'] = None # Garante que a coluna existe para evitar KeyError
                        if 'free_time' not in df_responses.columns:
                            df_responses['free_time'] = None # Garante que a coluna existe

                        # Obter a última cotação do Dólar Abertura Venda
                        latest_dolar_cotacoes = db_utils.get_latest_dolar_cotacao_from_db()
                        dolar_abertura_venda = latest_dolar_cotacoes.get('abertura_venda', {}).get('valor')

                        if isinstance(dolar_abertura_venda, float) and dolar_abertura_venda > 0:
                            # Calcular a nova coluna "Custo Total (BRL)"
                            # (valor frete + taxas origem + taxas destino) x (ultimo Dólar Abertura Venda + porcentagem do Spread Cambial)
                            df_responses['custo_base_usd'] = (
                                pd.to_numeric(df_responses['valor_frete'], errors='coerce').fillna(0) +
                                pd.to_numeric(df_responses['taxas_origem'], errors='coerce').fillna(0) +
                                pd.to_numeric(df_responses['taxas_destino'], errors='coerce').fillna(0)
                            )
                            
                            # Certifica-se que spread_cambial é numérico e divide por 100 para converter porcentagem
                            df_responses['spread_cambial_decimal'] = pd.to_numeric(df_responses['spread_cambial'], errors='coerce').fillna(0) / 100
                            
                            df_responses['custo_total_brl'] = df_responses['custo_base_usd'] * (dolar_abertura_venda * (1 + df_responses['spread_cambial_decimal']))
                            
                            # Formatar a nova coluna para exibição
                            df_responses['custo_total_brl_fmt'] = df_responses['custo_total_brl'].apply(
                                lambda x: f"R$ {x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
                            )
                            
                            # Formatar spread cambial para exibição
                            df_responses['spread_cambial_fmt'] = df_responses['spread_cambial'].apply(
                                lambda x: f"{x:.2f}%" if pd.notna(x) else 'N/A'
                            )

                            # Colunas a serem exibidas, incluindo as novas
                            display_columns = [
                                "agent_username", "valor_frete", "taxas_origem", "taxas_destino",
                                "free_time", "transit_time", "validade_cotacao_fmt", "data_envio_fmt", 
                                "spread_cambial_fmt", "custo_total_brl_fmt"
                            ]
                            column_names = {
                                "agent_username": "Agente",
                                "valor_frete": "Frete (USD)",
                                "taxas_origem": "Taxas Origem (USD)",
                                "taxas_destino": "Taxas Destino (USD)",
                                "free_time": "Free Time (dias)",
                                "transit_time": "Transit Time (dias)",
                                "validade_cotacao_fmt": "Validade Cotação",
                                "data_envio_fmt": "Data Envio",
                                "spread_cambial_fmt": "Spread Cambial",
                                "custo_total_brl_fmt": f"Custo Total (R$) @ Dólar {dolar_abertura_venda:.4f}"
                            }
                        else:
                            st.warning("Não foi possível obter a cotação do 'Dólar Abertura Venda' para calcular o Custo Total em BRL.")
                            # Colunas a serem exibidas sem a nova coluna de custo total
                            display_columns = [
                                "agent_username", "valor_frete", "taxas_origem", "taxas_destino",
                                "free_time", "transit_time", "validade_cotacao_fmt", "data_envio_fmt", "spread_cambial"
                            ]
                            column_names = {
                                "agent_username": "Agente",
                                "valor_frete": "Frete (USD)",
                                "taxas_origem": "Taxas Origem (USD)",
                                "taxas_destino": "Taxas Destino (USD)",
                                "free_time": "Free Time (dias)",
                                "transit_time": "Transit Time (dias)",
                                "validade_cotacao_fmt": "Validade Cotação",
                                "data_envio_fmt": "Data Envio",
                                "spread_cambial": "Spread Cambial"
                            }

                        # Filtrar colunas que não são relevantes para o tipo de transporte da solicitação original
                        # Por exemplo, se a solicitação é Aéreo, não mostre Free Time e Transit Time
                        if req.get('tipo_transporte') == "Aéreo":
                            display_columns = [col for col in display_columns if col not in ["free_time", "transit_time"]]
                            column_names = {k:v for k,v in column_names.items() if k not in ["free_time", "transit_time"]}


                        st.dataframe(df_responses[display_columns].rename(columns=column_names), use_container_width=True, hide_index=True)
                    else:
                        st.info("Nenhuma resposta encontrada para esta solicitação ainda.")
                
                st.markdown("---") # Separador entre os cards
    else:
        st.info("Nenhuma solicitação de cotação encontrada.")
