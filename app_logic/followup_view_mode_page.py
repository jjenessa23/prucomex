import streamlit as st
import os
import base64 # Importar base64 para codificar imagens

# Configuração de logging para este módulo
import logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Importar funções de utilidade do módulo utils
try:
    from app_logic.utils import set_background_image
except ImportError:
    logging.warning("Módulo 'app_logic.utils' não encontrado. Funções de imagem de fundo podem não funcionar.")
    def set_background_image(image_path, opacity=None):
        pass # Função mock se utils não for encontrado

def _toggle_view_mode():
    """Alterna o modo de visualização entre 'cards' e 'tables'."""
    if st.session_state.view_mode == 'cards':
        st.session_state.view_mode = 'tables' 
    else:
        st.session_state.view_mode = 'cards'
    st.rerun() # Força o rerun para aplicar a nova visualização

def display_view_mode_page():
    """Exibe a página dedicada para alterar o modo de visualização do Follow-up."""
    background_image_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'assets', 'logo_navio_atracado.png')
    set_background_image(background_image_path)

    st.subheader("Alterar Visualização do Follow-up")
    st.info("Escolha o modo de visualização para os processos de importação.")

    with st.form(key="view_mode_form"):
        current_view_mode = st.session_state.get('view_mode', 'cards')
        current_show_payment_view = st.session_state.get('show_payment_view', False)

        st.markdown("#### Tipo de Visualização")
        view_mode_options = {
            'cards': 'Visualização em Cards (Padrão)',
            'tables': 'Visualização em Tabela'
        }
        selected_display_mode = st.radio(
            "Selecione o layout:",
            options=list(view_mode_options.keys()),
            format_func=lambda x: view_mode_options[x],
            index=list(view_mode_options.keys()).index(current_view_mode),
            key="select_display_mode"
        )

        st.markdown("---")
        st.markdown("#### Detalhes da Visualização")
        # Botão para alternar a visualização de pagamentos
        payment_view_checkbox = st.checkbox(
            "Mostrar Visualização de Pagamentos (apenas em Cards)",
            value=current_show_payment_view,
            key="toggle_payment_view_checkbox"
        )

        st.markdown("---")
        col_apply, col_cancel = st.columns(2)
        with col_apply:
            if st.form_submit_button("Aplicar Visualização"):
                st.session_state.view_mode = selected_display_mode
                st.session_state.show_payment_view = payment_view_checkbox
                st.session_state.current_page = "Follow-up Importação" # Retorna à página principal
                st.rerun()
        with col_cancel:
            if st.form_submit_button("Cancelar"):
                st.session_state.current_page = "Follow-up Importação" # Retorna à página principal
                st.rerun()

