import streamlit as st
import os
import base64

# --- Função para definir imagem de fundo com opacidade (para o corpo principal) ---
def set_background_image(image_path):
    """
    Define uma imagem de fundo para o corpo principal da aplicação Streamlit.
    A imagem é convertida para Base64 e injetada via CSS em um pseudo-elemento ::before,
    garantindo que o conteúdo da página não fique transparente.
    """
    try:
        with open(image_path, "rb") as image_file:
            encoded_string = base64.b64encode(image_file.read()).decode()
        st.markdown(
            f"""
            <style>
            .stApp {{
                background-color: transparent !important; /* Garante que o fundo do app seja transparente */
            }}
            .stApp::before {{
                content: "";
                position: fixed;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
                background-image: url("data:image/png;base64,{encoded_string}");
                background-size: cover;
                background-position: center;
                background-repeat: no-repeat;
                background-attachment: fixed;
                opacity: 0.20; /* Opacidade ajustada para 20% */
                z-index: -1; /* Garante que o pseudo-elemento fique atrás do conteúdo */
            }}
            </style>
            """,
            unsafe_allow_html=True
        )
    except FileNotFoundError:
        st.warning(f"A imagem de fundo não foi encontrada no caminho: {image_path}")
    except Exception as e:
        st.error(f"Erro ao carregar a imagem de fundo: {e}")

# --- Função para definir imagem de fundo para a Sidebar ---
def set_sidebar_background_image(image_path, opacity=0.3):
    """
    Define uma imagem de fundo para a barra lateral (sidebar) da aplicação Streamlit.
    A imagem é convertida para Base64 e injetada via CSS em um pseudo-elemento ::before,
    garantindo que o conteúdo da sidebar não fique transparente.
    """
    try:
        with open(image_path, "rb") as image_file:
            encoded_string = base64.b64encode(image_file.read()).decode()
        st.markdown(
            f"""
            <style>
            [data-testid="stSidebar"] {{
                background-color: transparent !important; /* Garante que o fundo da sidebar seja transparente */
                position: relative; /* Necessário para que o pseudo-elemento se posicione corretamente */
            }}
            [data-testid="stSidebar"]::before {{
                content: "";
                position: absolute;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
                background-image: url("data:image/png;base64,{encoded_string}");
                background-size: cover;
                background-position: center;
                background-repeat: no-repeat;
                background-attachment: scroll; /* Use scroll if you want it to scroll with sidebar content */
                opacity: {opacity}; /* Opacidade da imagem de fundo da sidebar */
                z-index: -1; /* Garante que o pseudo-elemento fique atrás do conteúdo da sidebar */
            }}
            /* Garante que o conteúdo da sidebar (botões, texto) seja totalmente opaco */
            [data-testid="stSidebarContent"] > div {{
                opacity: 1 !important;
            }}
            </style>
            """,
            unsafe_allow_html=True
        )
    except FileNotFoundError:
        st.warning(f"A imagem de fundo da sidebar não foi encontrada no caminho: {image_path}")
    except Exception as e:
        st.error(f"Erro ao carregar a imagem de fundo da sidebar: {e}")
