import streamlit as st
import requests
import json
import logging
import os
from datetime import datetime, timedelta

# Importar funcións de utilidade do módulo utils
try:
    from app_logic.utils import set_background_image
except ImportError:
    logging.warning("Módulo 'app_logic.utils' non atopado. Funcións de imaxe de fondo poden non funcionar.")
    def set_background_image(image_path, opacity=None):
        pass # Función mock se utils non é atopado

logger = logging.getLogger(__name__)

# URL base para a API da Portonave
# ATENCIÓN: Cambiado ao ambiente de HOMOLOGACIÓN, segundo probado no Swagger UI.
# Se é necesario usar o ambiente de produción, cambie a "https://recursos.portonave.com.br/v1/portonaveapiservice"
PORTONAVE_API_BASE_URL = "https://recursos.homolog.portonave.com.br/v1/portonaveapiservice"

def show_portonave_lineup_page():
    """
    Mostra a interface para probar o endpoint de Lineup da API da Portonave.
    Permite inserir o token de autorización e mostra os datos retornados.
    """
    # Define o camiño da imaxe de fondo
    background_image_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'assets', 'logo_navio_atracado.png')
    set_background_image(background_image_path)

    st.subheader("Probar API Portonave Lineup")
    st.info("Insira as súas credenciais para obter un token e consultar os datos de Lineup da Portonave.")

    # --- Sección para Obter Token ---
    st.markdown("#### 1. Obter Token de Autorización")

    # Inicializa o session_state para os campos de login e token
    if 'portonave_login_cnpj' not in st.session_state:
        st.session_state.portonave_login_cnpj = "09376495000122" # Valor predeterminado CNPJ
    if 'portonave_login_email' not in st.session_state:
        st.session_state.portonave_login_email = "comex@pichau.com.br" # Valor predeterminado E-mail
    if 'portonave_login_tipoperfil' not in st.session_state:
        st.session_state.portonave_login_tipoperfil = "CL" # Valor predeterminado Tipo de Perfil
    if 'portonave_login_usuario' not in st.session_state:
        st.session_state.portonave_login_usuario = "04135731929" # Valor predeterminado Usuario
    if 'portonave_login_senha' not in st.session_state:
        st.session_state.portonave_login_senha = "Pch2025$" # Valor predeterminado Contrasinal
    if 'portonave_api_auth_token' not in st.session_state:
        st.session_state.portonave_api_auth_token = ""
    if 'portonave_api_permission_token' not in st.session_state:
        st.session_state.portonave_api_permission_token = ""

    with st.form(key="portonave_login_form"):
        st.session_state.portonave_login_cnpj = st.text_input(
            "CNPJ Empresa Contratada:",
            value=st.session_state.portonave_login_cnpj,
            key="portonave_login_cnpj_input"
        )
        st.session_state.portonave_login_email = st.text_input(
            "E-mail:",
            value=st.session_state.portonave_login_email,
            key="portonave_login_email_input"
        )
        st.session_state.portonave_login_tipoperfil = st.text_input(
            "Tipo de Perfil (Ex: CL):",
            value=st.session_state.portonave_login_tipoperfil,
            key="portonave_login_tipoperfil_input"
        )
        st.session_state.portonave_login_usuario = st.text_input(
            "Usuario:",
            value=st.session_state.portonave_login_usuario,
            key="portonave_login_usuario_input"
        )
        st.session_state.portonave_login_senha = st.text_input(
            "Contrasinal:",
            type="password",
            value=st.session_state.portonave_login_senha,
            key="portonave_login_senha_input"
        )

        if st.form_submit_button("Obter Token"):
            login_data = {
                "cnpjEmpresaSelecionada": st.session_state.portonave_login_cnpj,
                "email": st.session_state.portonave_login_email,
                "tipoPerfil": st.session_state.portonave_login_tipoperfil,
                "usuario": st.session_state.portonave_login_usuario,
                "senha": st.session_state.portonave_login_senha
            }
            
            # CORRECCIÓN: Usando a URL de login completa e exacta que confirmou
            login_url = "https://recursos.homolog.portonave.com.br/v1/portonaveapiservice/login"
            
            headers = {
                "Content-Type": "application/json",
                "Accept": "*/*", 
                "User-Agent": "StreamlitApp/1.0 (Python requests)" 
            }

            with st.spinner("Autenticando e obtendo token..."):
                st.write("Datos de login sendo enviados (para depuración):")
                st.json(login_data)

                try:
                    response = requests.post(login_url, headers=headers, json=login_data, timeout=10) 
                    response.raise_for_status()
                    token_data = response.json()

                    # CORRECCIÓN: Accede a 'access_token' dentro do campo 'dados'
                    if "dados" in token_data and "access_token" in token_data["dados"]:
                        st.session_state.portonave_api_auth_token = token_data["dados"]["access_token"]
                        st.session_state.portonave_api_permission_token = token_data["dados"].get("permission_token", "")
                        st.success("Token obtido con éxito!")
                        st.write(f"**Access Token:** `{st.session_state.portonave_api_auth_token[:30]}...`") 
                        if st.session_state.portonave_api_permission_token:
                            st.write(f"**Permission Token:** `{st.session_state.portonave_api_permission_token[:30]}...`")
                    else:
                        st.error("Resposta da API non contén 'access_token' no campo 'dados'.") # Mensaxe de erro máis específica
                        st.json(token_data)

                except requests.exceptions.HTTPError as http_err:
                    st.error(f"Erro HTTP ao obter token: {http_err}")
                    st.error(f"Status Code: {response.status_code}")
                    try:
                        error_details = response.json()
                        st.json(error_details) # Mostra detalles do erro JSON, se hai
                    except json.JSONDecodeError:
                        st.error(f"Resposta de erro completa da API (non JSON): {response.text}") # Log da resposta completa
                except requests.exceptions.Timeout:
                    st.error("A requisição excedeu o tempo limite (10 segundos). Verifique a conexão ou a disponibilidade da API.")
                except requests.exceptions.RequestException as req_err:
                    st.error(f"Erro de requisição ao obter token: {req_err}")
                except json.JSONDecodeError:
                    st.error("Erro ao decodificar a resposta JSON do token. A resposta non é un JSON válido.")
                    st.text(response.text)

    st.markdown("---")

    # --- Sección para Consultar Lineup (usando o token obtido) ---
    st.markdown("#### 2. Consultar Lineup (usando o token acima)")

    if not st.session_state.portonave_api_auth_token:
        st.warning("Por favor, obteña un token na sección anterior para consultar o Lineup.")
    else:
        # Reintroduzindo campos de data e parâmetros de query string para o Lineup
        # É provável que sejam obrigatórios, apesar de não documentados no Swagger UI
        st.markdown("##### Filtros de Data para Lineup (Provavelmente Obrigatório)")
        col1, col2 = st.columns(2)
        with col1:
            # Define a data inicial como hoje por padrão
            default_start_date = datetime.now().date()
            start_date = st.date_input("Data Inicial:", value=default_start_date, key="lineup_start_date")
        with col2:
            # Define a data final como 30 dias a partir de hoje por padrão
            default_end_date = datetime.now().date() + timedelta(days=30)
            end_date = st.date_input("Data Final:", value=default_end_date, key="lineup_end_date")

        if st.button("Consultar Lineup"):
            api_url = f"{PORTONAVE_API_BASE_URL}/relatorios/lineup"
            
            # Adiciona parâmetros de query string se as datas forem fornecidas
            params = {}
            if start_date:
                params["dataInicial"] = start_date.strftime("%Y-%m-%d") # Formato YYYY-MM-DD
            if end_date:
                params["dataFinal"] = end_date.strftime("%Y-%m-%d") # Formato YYYY-MM-DD

            headers = {
                "Authorization": f"Bearer {st.session_state.portonave_api_auth_token}",
                "Accept": "*/*", # Mantido *//* conforme Swagger UI para o endpoint de Lineup
                "User-Agent": "StreamlitApp/1.0 (Python requests)", 
                "permission_token": st.session_state.portonave_api_permission_token 
            }

            with st.spinner("Consultando API da Portonave..."):
                st.write("Headers enviados para o Lineup (para depuración):")
                st.json(headers) # Exibe os headers enviados
                st.write("Parâmetros de query string enviados para o Lineup (para depuração):")
                st.json(params) # Exibe os parâmetros de query string enviados

                try:
                    response = requests.get(api_url, headers=headers, params=params, timeout=10) 
                    response.raise_for_status()

                    data = response.json()

                    st.success("Datos do Lineup obtidos con éxito!")
                    st.markdown("#### Datos do Lineup:")
                    
                    if isinstance(data, list) and all(isinstance(item, dict) for item in data):
                        st.dataframe(data, use_container_width=True)
                    else:
                        st.json(data)

                except requests.exceptions.HTTPError as http_err:
                    st.error(f"Erro HTTP ao consultar a API: {http_err}")
                    st.error(f"Status Code: {response.status_code}")
                    try:
                        error_details = response.json()
                        st.json(error_details)
                    except json.JSONDecodeError:
                        st.error(f"Resposta de erro da API (não JSON): {response.text}") # Log da resposta completa
                except requests.exceptions.Timeout:
                    st.error("A requisição excedeu o tempo limite (10 segundos). Verifique a conexão ou a disponibilidade da API.")
                except requests.exceptions.RequestException as req_err:
                    st.error(f"Ocorreu un erro inesperado na requisição: {req_err}")
                except json.JSONDecodeError:
                    st.error("Erro ao decodificar a resposta JSON da API. A resposta non é un JSON válido.")
                    st.text(response.text)

    st.markdown("---")
    st.write("Esta pantalla é para fins de proba e depuración da integración coa API da Portonave.")
