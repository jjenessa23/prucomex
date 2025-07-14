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

# URL base para a API da Portonave
PORTONAVE_API_BASE_URL = "https://recursos.portonave.com.br/v1/portonaveapiservice"

def show_portonave_lineup_page():
    """
    Exibe a interface para testar o endpoint de Lineup da API da Portonave.
    Permite inserir o token de autorização e exibe os dados retornados.
    """
    # Define o caminho da imagem de fundo
    background_image_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'assets', 'logo_navio_atracado.png')
    set_background_image(background_image_path)

    st.subheader("Testar API Portonave Lineup")
    st.info("Insira suas credenciais para obter um token e consultar os dados de Lineup da Portonave.")

    # --- Seção para Obter Token ---
    st.markdown("#### 1. Obter Token de Autorização")

    # Inicializa o session_state para os campos de login e token
    if 'portonave_login_cnpj' not in st.session_state:
        st.session_state.portonave_login_cnpj = "09376495000122" # Valor padrão CNPJ
    if 'portonave_login_email' not in st.session_state:
        st.session_state.portonave_login_email = "comex@pichau.com.br" # Valor padrão E-mail
    if 'portonave_login_tipoperfil' not in st.session_state:
        st.session_state.portonave_login_tipoperfil = "CL" # Valor padrão Tipo de Perfil
    if 'portonave_login_usuario' not in st.session_state:
        st.session_state.portonave_login_usuario = "04135731929" # Valor padrão Usuário
    if 'portonave_login_senha' not in st.session_state:
        st.session_state.portonave_login_senha = "Pch2025$" # Valor padrão Senha
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
            "Usuário:",
            value=st.session_state.portonave_login_usuario,
            key="portonave_login_usuario_input"
        )
        st.session_state.portonave_login_senha = st.text_input(
            "Senha:",
            type="password",
            value=st.session_state.portonave_login_senha,
            key="portonave_login_senha_input"
        )

        if st.form_submit_button("Obter Token"):
            login_data = {
                "cnpjEmpresaContratada": st.session_state.portonave_login_cnpj,
                "email": st.session_state.portonave_login_email,
                "tipoPerfil": st.session_state.portonave_login_tipoperfil,
                "usuario": st.session_state.portonave_login_usuario,
                "senha": st.session_state.portonave_login_senha
            }
            
            login_url = f"{PORTONAVE_API_BASE_URL}/login"
            headers = {"Content-Type": "application/json"}

            with st.spinner("Autenticando e obtendo token..."):
                try:
                    response = requests.post(login_url, headers=headers, json=login_data)
                    response.raise_for_status()
                    token_data = response.json()

                    if "access_token" in token_data:
                        st.session_state.portonave_api_auth_token = token_data["access_token"]
                        st.session_state.portonave_api_permission_token = token_data.get("permission_token", "")
                        st.success("Token obtido com sucesso!")
                        st.write(f"**Access Token:** `{st.session_state.portonave_api_auth_token[:30]}...`") # Exibe parte do token
                        if st.session_state.portonave_api_permission_token:
                            st.write(f"**Permission Token:** `{st.session_state.portonave_api_permission_token[:30]}...`")
                    else:
                        st.error("Resposta da API não contém 'access_token'.")
                        st.json(token_data)

                except requests.exceptions.HTTPError as http_err:
                    st.error(f"Erro HTTP ao obter token: {http_err}")
                    st.error(f"Status Code: {response.status_code}")
                    try:
                        error_details = response.json()
                        st.json(error_details)
                    except json.JSONDecodeError:
                        st.error(f"Resposta de erro: {response.text}")
                except requests.exceptions.RequestException as req_err:
                    st.error(f"Erro de requisição ao obter token: {req_err}")
                except json.JSONDecodeError:
                    st.error("Erro ao decodificar a resposta JSON do token. A resposta não é um JSON válido.")
                    st.text(response.text)

    st.markdown("---")

    # --- Seção para Consultar Lineup (usando o token obtido) ---
    st.markdown("#### 2. Consultar Lineup (usando o token acima)")

    if not st.session_state.portonave_api_auth_token:
        st.warning("Por favor, obtenha um token na seção acima para consultar o Lineup.")
    else:
        if st.button("Consultar Lineup"):
            api_url = f"{PORTONAVE_API_BASE_URL}/relatorios/lineup"

            headers = {
                "Authorization": f"Bearer {st.session_state.portonave_api_auth_token}",
                "Accept": "application/json"
            }

            with st.spinner("Consultando API da Portonave..."):
                try:
                    response = requests.get(api_url, headers=headers)
                    response.raise_for_status()

                    data = response.json()

                    st.success("Dados do Lineup obtidos com sucesso!")
                    st.markdown("#### Dados do Lineup:")
                    
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
                        st.error(f"Resposta de erro da API: {response.text}")
                except requests.exceptions.RequestException as req_err:
                    st.error(f"Ocorreu um erro inesperado na requisição: {req_err}")
                except json.JSONDecodeError:
                    st.error("Erro ao decodificar a resposta JSON da API. A resposta não é um JSON válido.")
                    st.text(response.text)

    st.markdown("---")
    st.write("Esta tela é para fins de teste e depuração da integração com a API da Portonave.")
