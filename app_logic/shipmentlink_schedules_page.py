import streamlit as st
import requests
import json
import logging
import os
from datetime import datetime, timedelta

# Importar funções de utilidade do módulo utils
try:
    from app_logic.utils import set_background_image
except ImportError:
    logging.warning("Módulo 'app_logic.utils' não encontrado. Funções de imagem de fundo podem não funcionar.")
    def set_background_image(image_path, opacity=None):
        pass # Função mock se utils não for encontrado

logger = logging.getLogger(__name__)

# URL base hipotética para a API Commercial Schedules.
# A documentação fornecida é uma especificação, não um endpoint ao vivo.
# Você precisará substituir esta URL pela URL base real da API da ShipmentLink Commercial Schedules.
SHIPMENTLINK_SCHEDULES_API_BASE_URL = "https://api.shipmentlink.com/v1/commercialschedules"

def show_shipmentlink_schedules_page():
    """
    Exibe a interface para testar a API ShipmentLink Commercial Schedules.
    Permite inserir o token de autorização e consultar programações de navios.
    """
    # Define o caminho da imagem de fundo
    background_image_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'assets', 'logo_navio_atracado.png')
    set_background_image(background_image_path)

    st.subheader("Testar API ShipmentLink Commercial Schedules")
    st.info("Consulte programações de navios por porto, navio ou rota.")

    # Campo para o token de autorização
    if 'shipmentlink_schedules_auth_token' not in st.session_state:
        st.session_state.shipmentlink_schedules_auth_token = ""

    auth_token = st.text_input(
        "Token de Autorização (Bearer Token ou API Key):",
        type="password", # Esconde o token
        value=st.session_state.shipmentlink_schedules_auth_token,
        key="shipmentlink_schedules_auth_token_input",
        help="Este é o token de acesso ou API Key necessário para autenticar na API."
    )
    st.session_state.shipmentlink_schedules_auth_token = auth_token

    st.markdown("---")

    # Seleção do tipo de consulta
    query_type = st.radio(
        "Selecione o Tipo de Consulta:",
        ("Por Porto", "Por Navio", "Ponto a Ponto"),
        key="shipmentlink_schedules_query_type"
    )

    # Parâmetros de consulta dinâmicos
    params = {}
    today = datetime.now().date()
    default_end_date = today + timedelta(days=30) # Próximos 30 dias

    if query_type == "Por Porto":
        port_code = st.text_input("Código do Porto (Ex: BRSSZ para Santos):", key="sl_port_code")
        start_date = st.date_input("Data de Início:", value=today, key="sl_port_start_date")
        end_date = st.date_input("Data de Fim:", value=default_end_date, key="sl_port_end_date")
        params = {
            "portCode": port_code.strip(),
            "startDate": start_date.strftime("%Y-%m-%d"),
            "endDate": end_date.strftime("%Y-%m-%d")
        }
        endpoint = "/schedules/byPort" # Endpoint hipotético
        
    elif query_type == "Por Navio":
        vessel_name = st.text_input("Nome do Navio (Ex: MAERSK MC-KINNEY MOLLER):", key="sl_vessel_name")
        start_date = st.date_input("Data de Início:", value=today, key="sl_vessel_start_date")
        end_date = st.date_input("Data de Fim:", value=default_end_date, key="sl_vessel_end_date")
        params = {
            "vesselName": vessel_name.strip(),
            "startDate": start_date.strftime("%Y-%m-%d"),
            "endDate": end_date.strftime("%Y-%m-%d")
        }
        endpoint = "/schedules/byVessel" # Endpoint hipotético

    elif query_type == "Ponto a Ponto":
        origin_port_code = st.text_input("Código do Porto de Origem (Ex: BRSSZ):", key="sl_origin_port_code")
        destination_port_code = st.text_input("Código do Porto de Destino (Ex: USNYC):", key="sl_destination_port_code")
        start_date = st.date_input("Data de Início:", value=today, key="sl_p2p_start_date")
        end_date = st.date_input("Data de Fim:", value=default_end_date, key="sl_p2p_end_date")
        params = {
            "originPortCode": origin_port_code.strip(),
            "destinationPortCode": destination_port_code.strip(),
            "startDate": start_date.strftime("%Y-%m-%d"),
            "endDate": end_date.strftime("%Y-%m-%d")
        }
        endpoint = "/schedules/pointToPoint" # Endpoint hipotético

    # Botão para fazer a chamada à API
    if st.button("Consultar Programação"):
        if not auth_token:
            st.warning("Por favor, insira um token de autorização.")
            return
        
        # Validação básica dos parâmetros
        if query_type == "Por Porto" and not params["portCode"]:
            st.warning("Por favor, insira o código do porto.")
            return
        if query_type == "Por Navio" and not params["vesselName"]:
            st.warning("Por favor, insira o nome do navio.")
            return
        if query_type == "Ponto a Ponto" and (not params["originPortCode"] or not params["destinationPortCode"]):
            st.warning("Por favor, insira os códigos dos portos de origem e destino.")
            return

        api_url = f"{SHIPMENTLINK_SCHEDULES_API_BASE_URL}{endpoint}"

        headers = {
            "Authorization": f"Bearer {auth_token}", # Assumindo Bearer Token
            "Accept": "application/json",
            "Content-Type": "application/json" # Para requisições POST, se aplicável
        }

        with st.spinner("Consultando API ShipmentLink Commercial Schedules..."):
            try:
                # Para simplificar, faremos todas as chamadas como GET com parâmetros de query.
                # Se a API real exigir POST para alguns tipos de consulta, isso precisaria ser ajustado.
                response = requests.get(api_url, headers=headers, params=params)
                response.raise_for_status()

                data = response.json()

                st.success("Dados da programação obtidos com sucesso!")
                st.markdown("#### Resultados da Programação:")
                
                if isinstance(data, list) and all(isinstance(item, dict) for item in data):
                    # Exibir em DataFrame para melhor visualização
                    df = st.dataframe(data, use_container_width=True)
                else:
                    st.json(data) # Exibe como JSON bruto se o formato não for uma lista de dicionários

            except requests.exceptions.HTTPError as http_err:
                st.error(f"Erro HTTP ao consultar a API: {http_err}")
                st.error(f"Status Code: {response.status_code}")
                try:
                    error_details = response.json()
                    st.json(error_details)
                except json.JSONDecodeError:
                    st.error(f"Resposta de erro da API: {response.text}")
            except requests.exceptions.ConnectionError as conn_err:
                st.error(f"Erro de conexão: Não foi possível conectar à API da ShipmentLink. Verifique sua conexão com a internet ou o status da API. Detalhes: {conn_err}")
            except requests.exceptions.Timeout as timeout_err:
                st.error(f"Tempo limite da requisição excedido ao consultar a API da ShipmentLink. Detalhes: {timeout_err}")
            except requests.exceptions.RequestException as req_err:
                st.error(f"Ocorreu um erro inesperado na requisição: {req_err}")
            except json.JSONDecodeError:
                st.error("Erro ao decodificar a resposta JSON da API. A resposta não é um JSON válido.")
                st.text(response.text)

    st.markdown("---")
    st.write("Esta tela é para fins de teste e depuração da integração com a API ShipmentLink Commercial Schedules.")

