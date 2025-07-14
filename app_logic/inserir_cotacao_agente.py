import streamlit as st
import os
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List
import pandas as pd # Importar pandas para exibir as solicitações

# Importar funções do módulo de utilitários de banco de dados
import app_logic.db_utils as db_utils
import app_logic.db_cotacao_frete as db_cotacao_frete # Módulo de DB para cotação de frete
from app_logic.utils import set_background_image

# Configuração de logging para este módulo
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# --- Funções de UI (Streamlit) ---

def show_inserir_cotacao_agente_page():
    background_image_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'assets', 'logo_navio_atracado.png')
    set_background_image(background_image_path)

    st.title("Inserir Cotação de Frete - Agente de Carga")

    # Esta página agora assume que o usuário já está logado no sistema principal.
    # Verifica se o usuário principal está autenticado.
    if not st.session_state.get('authenticated', False):
        st.warning("Você precisa estar logado no sistema para acessar esta tela.")
        st.info("Por favor, faça login na tela principal.")
        return

    # Verifica se o usuário logado é um agente de carga
    user_info = st.session_state.get('user_info', {})
    is_freight_agent = user_info.get('is_freight_agent', False)
    agent_username = user_info.get('username')

    if not is_freight_agent:
        st.warning("Seu usuário não está configurado como um Agente de Carga. Você não tem permissão para acessar esta tela.")
        st.info("Se você acredita que isso é um erro, entre em contato com o administrador do sistema.")
        logger.info(f"Tentativa de acesso à tela de agente por usuário não agente: {agent_username}. UserInfo: {user_info}")
        return

    # Se chegou aqui, o usuário está autenticado e é um agente de carga.
    if not agent_username:
        st.error("Não foi possível identificar o nome de usuário do agente logado. Por favor, tente fazer login novamente.")
        return

    st.subheader(f"Bem-vindo, Agente {agent_username}!")
    st.markdown("---")
    st.subheader("Solicitações de Cotação Pendentes para Você")

    # Obter todas as solicitações de cotação
    all_quotation_requests = db_cotacao_frete.get_all_quotation_requests()
    
    # NOVO: Filtrar solicitações onde o agente logado está em 'agentes_enviados'
    # E verificar se o agente JÁ RESPONDEU a esta solicitação.
    pending_requests_for_agent = []
    for req in all_quotation_requests:
        if agent_username in req.get('agentes_enviados', []):
            # Verifica se o agente já respondeu a esta solicitação
            if not db_cotacao_frete.has_agent_responded(req['id'], agent_username):
                pending_requests_for_agent.append(req)

    if pending_requests_for_agent:
        df_pending_requests = pd.DataFrame(pending_requests_for_agent)
        
        # Formatar a coluna 'data_solicitacao' para exibição
        df_pending_requests['data_solicitacao_fmt'] = df_pending_requests['data_solicitacao'].apply(
            lambda x: datetime.fromisoformat(x).strftime('%d/%m/%Y %H:%M') if x else 'N/A'
        )
        
        # Selecionar e reordenar colunas para exibição
        display_columns = [
            "id", "origem_cidade", "origem_pais", "destino_cidade", "destino_pais",
            "tipo_transporte", "incoterm", "data_solicitacao_fmt"
        ]
        
        # Adicionar colunas específicas de transporte se existirem nos dados
        if 'tipo_carga' in df_pending_requests.columns:
            display_columns.insert(6, "tipo_carga")
        if 'qtd_containers' in df_pending_requests.columns:
            display_columns.insert(7, "qtd_containers")
        if 'peso_kg' in df_pending_requests.columns:
            display_columns.insert(7, "peso_kg")

        st.dataframe(df_pending_requests[display_columns], use_container_width=True, hide_index=True)

        st.markdown("---")
        st.subheader("Inserir Cotação para Solicitação Selecionada")

        # Permitir que o agente selecione uma solicitação para responder
        request_ids_to_respond = [req['id'] for req in pending_requests_for_agent]
        selected_request_id = st.selectbox(
            "Selecione o ID da Solicitação para Responder:",
            options=[""] + request_ids_to_respond, # Adiciona uma opção vazia
            key="select_request_to_respond"
        )

        request_details = None
        if selected_request_id:
            request_details = next((req for req in pending_requests_for_agent if req['id'] == selected_request_id), None)
            if request_details:
                st.info(f"Detalhes da Solicitação ID: {request_details['id']}")
                st.write(f"**Origem:** {request_details.get('origem_cidade', 'N/A')}, {request_details.get('origem_pais', 'N/A')}")
                st.write(f"**Destino:** {request_details.get('destino_cidade', 'N/A')}, {request_details.get('destino_pais', 'N/A')}")
                st.write(f"**Tipo de Transporte:** {request_details.get('tipo_transporte', 'N/A')}")
                if request_details.get('tipo_transporte') == "Marítimo":
                    st.write(f"**Tipo de Carga:** {request_details.get('tipo_carga', 'N/A')}")
                    st.write(f"**Quantidade de Containers:** {request_details.get('qtd_containers', 'N/A')}")
                elif request_details.get('tipo_transporte') == "Aéreo":
                    st.write(f"**Peso (kg):** {request_details.get('peso_kg', 'N/A')}")
                st.write(f"**Incoterm:** {request_details.get('incoterm', 'N/A')}")
                st.write(f"**Data da Solicitação:** {datetime.fromisoformat(request_details['data_solicitacao']).strftime('%d/%m/%Y %H:%M') if request_details.get('data_solicitacao') else 'N/A'}")

                with st.form("inserir_cotacao_form"):
                    col1, col2 = st.columns(2)
                    
                    # Campos comuns a ambos os tipos de frete
                    with col1:
                        valor_frete = st.number_input("Frete (USD)", min_value=0.0, format="%.2f", key="valor_frete")
                        taxas_origem = st.number_input("Taxas Origem (USD)", min_value=0.0, format="%.2f", key="taxas_origem")
                    with col2:
                        taxas_destino = st.number_input("Taxas Destino (USD)", min_value=0.0, format="%.2f", key="taxas_destino")
                        # Ajuste aqui para o label exibir o formato desejado
                        validade_cotacao = st.date_input("Validade Cotação (DD/MM/AAAA)", value=datetime.now().date() + timedelta(days=7), key="validade_cotacao")
                    
                    # Campos específicos para Marítimo
                    if request_details.get('tipo_transporte') == "Marítimo":
                        with col1:
                            free_time = st.number_input("Free Time (dias)", min_value=0, step=1, key="free_time")
                        with col2:
                            transit_time = st.number_input("Transit Time (dias)", min_value=0, step=1, key="transit_time")
                    else: # Para Aéreo, esses campos não são exibidos
                        free_time = None
                        transit_time = None

                    # Campo Spread Cambial (comum, mas pode ser ajustado se necessário)
                    spread_cambial = st.number_input("Spread Cambial (%)", min_value=0.0, max_value=100.0, value=0.0, format="%.2f", key="spread_cambial")

                    submitted = st.form_submit_button("Enviar Cotação")

                    if submitted:
                        if not valor_frete:
                            st.error("Por favor, preencha o valor do frete.")
                        else:
                            quotation_data = {
                                "request_id": request_details['id'],
                                "agent_username": agent_username, # Usa o username do agente logado
                                "valor_frete": valor_frete,
                                "taxas_origem": taxas_origem,
                                "taxas_destino": taxas_destino,
                                "validade_cotacao": validade_cotacao.isoformat(),
                                "data_envio": datetime.now().isoformat(),
                                "spread_cambial": spread_cambial
                            }
                            
                            # Adiciona campos específicos se existirem
                            if free_time is not None:
                                quotation_data["free_time"] = free_time
                            if transit_time is not None:
                                quotation_data["transit_time"] = transit_time

                            if db_cotacao_frete.add_quotation_response(quotation_data):
                                st.success("Cotação enviada com sucesso!")
                                st.balloons()
                                # Limpar o formulário ou redirecionar
                                # É importante limpar o cache de dados para que a lista de pendentes seja atualizada
                                st.cache_data.clear() 
                                st.rerun() # Recarrega a página para limpar o formulário e atualizar a lista
                            else:
                                st.error("Erro ao enviar a cotação. Tente novamente.")
            else:
                st.warning("Solicitação de cotação não encontrada ou não é mais pendente.")
        else:
            st.info("Selecione uma solicitação de cotação acima para inserir os detalhes.")
    else:
        st.info("Nenhuma solicitação de cotação pendente para você neste momento.")
