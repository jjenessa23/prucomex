import streamlit as st
from datetime import datetime

# Helper function to remove a notification
def _remove_notification(index_to_remove):
    """
    Remove uma notificação específica da lista de notificações na session_state.
    """
    if 'notifications' in st.session_state and 0 <= index_to_remove < len(st.session_state.notifications):
        st.session_state.notifications.pop(index_to_remove)
        st.rerun()

# Esta função será chamada pela página inicial (app_main.py)
def display_notifications_on_home():
    """
    Exibe as notificações na tela inicial do programa, com um botão para excluir cada uma.
    """
    # Removido: Injetar CSS para estilizar o botão de exclusão e as notificações
    # st.markdown("""
    # <style>
    # /* Estilo para o container de cada notificação para controlar o espaçamento */
    # .notification-item {
    #     margin-bottom: 0px; /* Reduz o espaço entre as notificações para 0px */
    # }

    # .delete-button-container {
    #     display: flex;
    #     align-items: center; /* Centraliza verticalmente o botão */
    #     justify-content: center; /* Centraliza horizontalmente o botão */
    #     height: 100%; /* Garante que o container ocupe a altura da coluna */
    # }

    # .delete-button-container button {
    #     background-color: transparent !important;
    #     color: #ff4b4b !important; /* Cor vermelha para o ícone */
    #     border: none !important;
    #     padding: 0.25rem 0.5rem !important;
    #     border-radius: 5px !important;
    #     font-size: 1.2rem !important; /* Tamanho do ícone */
    #     cursor: pointer !important;
    #     transition: color 0.2s, background-color 0.2s !important;
    #     display: flex !important;
    #     align-items: center !important;
    #     justify-content: center !important;
    #     height: 100% !important; /* Garante que o botão ocupe a altura da coluna */
    # }
    # .delete-button-container button:hover {
    #     color: #ff0000 !important; /* Vermelho mais escuro ao passar o mouse */
    #     background-color: rgba(255, 75, 75, 0.1) !important; /* Fundo levemente vermelho ao passar o mouse */
    # }
    # .delete-button-container button:focus {
    #     outline: none !important;
    #     box-shadow: none !important;
    # }
    # /* Removido o ajuste de alinhamento vertical dos botões "Adicionar" e "Limpar" */
    # /* div[data-testid="stVerticalBlock"] > div > div > div:nth-child(2) > div {
    #     display: flex;
    #     align-items: flex-end;
    # } */
    # </style>
    # <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
    # """, unsafe_allow_html=True)


    if 'notifications' not in st.session_state:
        st.session_state.notifications = []

    if not st.session_state.notifications:
        st.info("Nenhuma notificação recente.")
    else:
        for i, notification in enumerate(st.session_state.notifications):
            # Usar colunas para posicionar o texto da notificação e o botão de exclusão lado a lado
            # Removido: Adicionar a classe 'notification-item' para controlar o espaçamento
            col_notif_text, col_notif_delete = st.columns([0.9, 0.1]) # 90% para texto, 10% para botão
            with col_notif_text:
                # Removido: Usar um container para a notificação para aplicar a margem inferior
                # st.markdown(f'<div class="notification-item">', unsafe_allow_html=True)
                st.warning(f"**Notificação {i+1}:** {notification}")
                # st.markdown(f'</div>', unsafe_allow_html=True)
            with col_notif_delete:
                # O botão de exclusão com ícone de lixeira e tooltip
                # Removido: st.markdown(f'<div class="delete-button-container">', unsafe_allow_html=True)
                if st.button("🗑️", key=f"delete_notif_{i}", help="Excluir Notificação"): # Adicionado o tooltip (help)
                    _remove_notification(i)
                # Removido: st.markdown(f'</div>', unsafe_allow_html=True)


    # Adicionar botões para gerenciar notificações (opcional, para testes)
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Adicionar Notificação de Teste"):
            st.session_state.notifications.append(f"Novo aviso importante em {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}.")
            st.rerun()
    with col2:
        if st.button("Limpar Notificações"):
            st.session_state.notifications = []
            st.rerun()

# Esta função é a original do módulo, mas não será mais chamada pelo menu lateral.
# Pode ser removida ou adaptada se houver necessidade de uma página de "Notificações" separada no futuro.
def show_page():
    """
    Função original da página de Notificações (agora as notificações são mostradas na Home).
    Pode ser adaptada para um gerenciamento mais avançado de notificações se necessário.
    """
    st.subheader("Gerenciamento Avançado de Notificações")
    st.write("Esta página pode ser usada para um sistema mais complexo de gerenciamento de notificações,")
    st.write("enquanto os alertas rápidos aparecem na tela inicial.")
    # Aqui você pode adicionar filtros, arquivo de notificações, etc.
