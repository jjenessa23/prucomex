import streamlit as st
import pandas as pd
import logging
import hashlib # Para hashing de senha
import os # Para verificar a existência do DB
from typing import Dict, Optional, Any, List
from app_logic.utils import set_background_image, set_sidebar_background_image

# Importar funções do módulo de utilitários de banco de dados
import app_logic.db_utils as db_utils
# db_cotacao_frete não é mais necessário aqui para CRUD de agentes, pois db_utils.py faz isso
# import app_logic.db_cotacao_frete as db_cotacao_frete 

# Configuração de logging para este módulo
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Lista de nomes de telas disponíveis (deve ser sincronizada com app_main.py)
# Esta lista é usada para as checkboxes de permissão
AVAILABLE_SCREENS_LIST = [
    "Home",
    "Descrições",
    "Listagem NCM",
    "Follow-up Importação",
    "Importar XML DI",
    "Pagamentos",
    "Custo do Processo",
    "Cálculo Portonave",
    "Cálculo Itapoa",
    "Análise de Documentos",
    "Pagamentos Container",
    "Cálculo de Tributos TTCE",
    "Gerenciamento de Usuários",
    "Cálculo Frete Internacional",
    "Análise de Faturas/PL (PDF)",
    "Cálculo Futura",
    "Cálculo Pac Log - Elo",
    "Cálculo Fechamento",
    "Cálculo FN Transportes",
    "Atualizar Dados de Processo",
    "Vincular Consolidado",
    "Formulário Processo",
    "Consulta de Processo",
    "Gerenciar Notificações (Admin)",
    "Edição em Massa de Processos",
    "Gerenciamento de Processos em Massa",
    "Ações do Processo (Popover)",
    "Mais Opções (Popover)",
    "Cotação de Frete Internacional",
    "Inserir Cotação Agente"
]

# --- Funções de Lógica de Negócio para USUÁRIOS E AGENTES (Interação com o DB) ---
# Todas as funções de CRUD agora usam db_utils e a flag is_freight_agent

def adicionar_usuario_ou_agente_db(username: str, password: str, email: str, is_admin: bool = False, is_freight_agent: bool = False, allowed_screens_list: Optional[List[str]] = None):
    """Adiciona um novo usuário (ou agente de carga) ao banco de dados usando db_utils."""
    password_hash = db_utils.hash_password(password, username)
    if db_utils.adicionar_ou_atualizar_usuario(None, username, password_hash, is_admin, allowed_screens_list, email=email, is_freight_agent=is_freight_agent):
        st.success(f"'{'Agente de Carga' if is_freight_agent else 'Usuário'}' '{username}' adicionado com sucesso!")
        return True
    else:
        st.error(f"Erro ao adicionar '{'agente de carga' if is_freight_agent else 'usuário'}' '{username}'. Verifique os logs.")
        return False

def obter_todos_usuarios_e_agentes_db():
    """Obtém a lista de todos os usuários do banco de dados (incluindo agentes) usando db_utils."""
    if st.session_state.get('firebase_ready', False):
        all_users = db_utils.get_all_users()
        if all_users is None:
            st.error("Não foi possível conectar ao banco de dados para obter a lista de usuários/agentes.")
            return []
        return all_users
    else:
        st.warning("Banco de dados não está pronto para carregar usuários/agentes.")
        return []

def obter_usuario_ou_agente_por_id_db(user_identifier: Any):
    """Obtém os dados de um usuário/agente específico pelo ID ou username usando db_utils."""
    if st.session_state.get('firebase_ready', False):
        user_data = db_utils.get_user_by_id_or_username(user_identifier)
        if user_data is None:
            st.error(f"Usuário/Agente com ID/Nome '{user_identifier}' não encontrado no banco de dados.")
            return None
        return user_data
    else:
        st.warning("Banco de dados não está pronto para obter detalhes do usuário/agente.")
        return None

def atualizar_usuario_ou_agente_db(user_id_or_username: Any, username: str, email: str, is_admin: bool, is_freight_agent: bool, allowed_screens_list: Optional[List[str]]):
    """Atualiza os dados de um usuário (ou agente de carga) existente no banco de dados usando db_utils."""
    if not st.session_state.get('firebase_ready', False):
        st.error("Banco de dados não está pronto para atualizar o usuário/agente.")
        return False

    existing_user_data = db_utils.get_user_by_id_or_username(user_id_or_username)
    if not existing_user_data:
        st.error(f"Usuário/Agente '{username}' não encontrado para atualização.")
        return False
    
    final_username_for_update = existing_user_data['username']
    if existing_user_data['username'] != username:
         st.warning("A alteração do nome de usuário não é permitida diretamente neste formulário para evitar problemas de ID. Salve com o nome original e, se necessário, exclua e recrie o usuário.")
         return False

    current_password_hash = existing_user_data.get('password_hash')
    
    if db_utils.adicionar_ou_atualizar_usuario(user_id_or_username, final_username_for_update, current_password_hash, is_admin, allowed_screens_list, email=email, is_freight_agent=is_freight_agent):
        st.success(f"'{'Agente de Carga' if is_freight_agent else 'Usuário'}' '{final_username_for_update}' atualizado com sucesso!")
        return True
    else:
        st.error(f"Erro ao atualizar '{'agente de carga' if is_freight_agent else 'usuário'}' '{final_username_for_update}'. Verifique os logs.")
        return False

def atualizar_senha_usuario_ou_agente_db(user_id_or_username: Any, new_password: str, username: str):
    """Atualiza a senha de um usuário/agente específico usando db_utils."""
    if st.session_state.get('firebase_ready', False):
        if db_utils.atualizar_senha_usuario(user_id_or_username, new_password, username):
            st.success(f"Senha de '{username}' atualizada com sucesso!")
            return True
        else:
            st.error(f"Erro ao atualizar senha de '{username}'. Verifique os logs.")
            return False
    else:
        st.error("Banco de dados não está pronto para atualizar a senha.")
        return False

def deletar_usuario_ou_agente_db(user_id_or_username: Any):
    """Deleta um usuário/agente do banco de dados pelo ID ou username usando db_utils."""
    if st.session_state.get('firebase_ready', False):
        if db_utils.deletar_usuario(user_id_or_username):
            st.success(f"Usuário/Agente excluído com sucesso!")
            return True
        else:
            st.error(f"Falha ao excluir usuário/agente '{user_id_or_username}'. Verifique os logs.")
            return False
    else:
        st.error("Banco de dados não está pronto para deletar o usuário/agente.")
        return False


# --- Funções de UI (Streamlit) ---

@st.cache_data(ttl=1)
def load_and_filter_users_and_agents_data():
    """Carrega todos os usuários e agentes, e os filtra para exibição separada."""
    logger.info("load_and_filter_users_and_agents_data: Tentando carregar e filtrar usuários e agentes do DB.")
    all_users_raw = obter_todos_usuarios_e_agentes_db()
    
    users_only = [u for u in all_users_raw if not u.get('is_freight_agent', False)]
    agents_only = [u for u in all_users_raw if u.get('is_freight_agent', False)]

    st.session_state.users_data_for_display = users_only
    st.session_state.agents_data_for_display = agents_only
    
    logger.info(f"load_and_filter_users_and_agents_data: Carregados {len(users_only)} usuários e {len(agents_only)} agentes para exibição.")


def display_add_unified_form():
    """Exibe o formulário para adicionar um novo usuário ou agente de carga."""
    with st.form("add_unified_form", clear_on_submit=True):
        st.markdown("### Adicionar Novo Usuário ou Agente de Carga")
        new_username = st.text_input("Nome de Usuário", key="add_new_username_input")
        new_password = st.text_input("Senha", type="password", key="add_new_password_input")
        new_email = st.text_input("E-mail (opcional)", key="add_new_email_input")
        new_is_admin = st.checkbox("É Administrador", key="add_new_is_admin_checkbox")
        new_is_freight_agent = st.checkbox("É Agente de Carga", key="add_new_is_freight_agent_checkbox")

        st.markdown("##### Permissões de Tela:")
        selected_screens = []
        for screen in AVAILABLE_SCREENS_LIST:
            initial_value = False
            if new_is_freight_agent and screen == "Inserir Cotação Agente":
                initial_value = True # Pré-seleciona para agentes
            
            if st.checkbox(screen, value=initial_value, key=f"add_unified_perm_{screen}"):
                selected_screens.append(screen)

        if st.form_submit_button("Adicionar"):
            if new_username and new_password:
                if adicionar_usuario_ou_agente_db(new_username, new_password, new_email, new_is_admin, new_is_freight_agent, selected_screens):
                    load_and_filter_users_and_agents_data.clear() # Limpa o cache para recarregar todos os dados
                    load_and_filter_users_and_agents_data()
                    st.session_state.show_add_form = False
                    st.rerun()
            else:
                st.warning("Nome de usuário e senha são obrigatórios.")


def display_edit_unified_form():
    """Exibe o formulário para editar um usuário ou agente de carga existente."""
    user_id_to_edit = st.session_state.get('editing_user_id')
    
    if user_id_to_edit is None:
        st.error("Nenhum usuário/agente selecionado para edição.")
        st.session_state.show_edit_form = False
        return

    user_data = obter_usuario_ou_agente_por_id_db(user_id_to_edit)
    if user_data is None:
        st.error(f"Usuário/Agente com ID/Nome '{user_id_to_edit}' não encontrado no banco de dados.")
        st.session_state.show_edit_form = False
        return

    initial_username = user_data['username']
    initial_email = user_data.get('email', '')
    initial_is_admin = user_data.get('is_admin', False)
    initial_is_freight_agent = user_data.get('is_freight_agent', False)
    initial_allowed_screens_list = user_data.get('allowed_screens', [])

    with st.form(f"edit_unified_form_{initial_username}"):
        st.markdown(f"### Editar Usuário/Agente: {initial_username}")
        
        edited_username = st.text_input("Nome de Usuário", value=initial_username, key=f"edit_unified_username_{initial_username}")
        edited_email = st.text_input("E-mail", value=initial_email, key=f"edit_unified_email_{initial_username}")
        edited_is_admin = st.checkbox("É Administrador", value=initial_is_admin, key=f"edit_unified_is_admin_{initial_username}")
        edited_is_freight_agent = st.checkbox("É Agente de Carga", value=initial_is_freight_agent, key=f"edit_unified_is_freight_agent_{initial_username}")

        st.markdown("##### Permissões de Tela:")
        edited_screens = []
        for screen in AVAILABLE_SCREENS_LIST:
            current_value = (screen in initial_allowed_screens_list)
            if edited_is_freight_agent and screen == "Inserir Cotação Agente":
                current_value = True # Força a seleção para agentes
            
            if st.checkbox(screen, value=current_value, key=f"edit_unified_perm_{initial_username}_{screen}"):
                edited_screens.append(screen)

        col_save, col_cancel = st.columns(2)
        with col_save:
            if st.form_submit_button("Salvar Alterações"):
                if atualizar_usuario_ou_agente_db(initial_username, edited_username, edited_email, edited_is_admin, edited_is_freight_agent, edited_screens):
                    load_and_filter_users_and_agents_data.clear()
                    load_and_filter_users_and_agents_data()
                    st.session_state.show_edit_form = False
                    st.session_state.editing_user_id = None
                    st.rerun()
        with col_cancel:
            if st.form_submit_button("Cancelar"):
                st.session_state.show_edit_form = False
                st.session_state.editing_user_id = None
                st.rerun()


def display_delete_unified_confirm_popup():
    """Exibe um pop-up de confirmação para exclusão de usuário ou agente."""
    user_id_to_delete = st.session_state.get('delete_user_id_to_confirm')
    user_name_to_delete = st.session_state.get('delete_user_name_to_confirm')

    if user_id_to_delete is None:
        st.session_state.show_delete_confirm_popup = False
        return

    with st.form(key=f"delete_unified_confirm_form_{user_id_to_delete}"):
        st.markdown(f"### Confirmar Exclusão de '{user_name_to_delete}'")
        st.warning(f"Tem certeza que deseja excluir '{user_name_to_delete}' (ID: {user_id_to_delete})?")
        
        col_yes, col_no = st.columns(2)
        with col_yes:
            if st.form_submit_button("Sim, Excluir"):
                if deletar_usuario_ou_agente_db(user_id_to_delete):
                    load_and_filter_users_and_agents_data.clear()
                    load_and_filter_users_and_agents_data()
                    st.session_state.show_delete_confirm_popup = False
                    st.session_state.delete_user_id_to_confirm = None
                    st.session_state.delete_user_name_to_confirm = None
                    st.rerun()
        with col_no:
            if st.form_submit_button("Não, Cancelar"):
                st.session_state.show_delete_confirm_popup = False
                st.session_state.delete_user_id_to_confirm = None
                st.session_state.delete_user_name_to_confirm = None
                st.rerun()


def display_change_password_unified_form():
    user_id_or_username = st.session_state.get('change_password_user_id')
    username = st.session_state.get('change_password_username')

    if user_id_or_username is None or username is None:
        st.error("Nenhum usuário/agente selecionado para alterar a senha.")
        st.session_state.show_change_password_form = False
        return

    with st.form(key=f"change_password_unified_form_{user_id_or_username}"):
        st.markdown(f"### Alterar Senha para: {username}")
        new_password = st.text_input("Nova Senha", type="password", key=f"new_password_input_{user_id_or_username}")
        confirm_password = st.text_input("Confirmar Nova Senha", type="password", key=f"confirm_password_input_{user_id_or_username}")

        col_save, col_cancel = st.columns(2)
        with col_save:
            if st.form_submit_button("Salvar Nova Senha"):
                if new_password and confirm_password:
                    if new_password == confirm_password:
                        if atualizar_senha_usuario_ou_agente_db(user_id_or_username, new_password, username):
                            st.session_state.show_change_password_form = False
                            st.session_state.change_password_user_id = None
                            st.session_state.change_password_username = None
                            st.rerun()
                    else:
                        st.error("As senhas não coincidem.")
                else:
                    st.warning("Por favor, preencha ambos os campos de senha.")
        with col_cancel:
            if st.form_submit_button("Cancelar"):
                st.session_state.show_change_password_form = False
                st.session_state.change_password_user_id = None
                st.session_state.change_password_username = None
                st.rerun()


def show_page():
    background_image_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'assets', 'logo_navio_atracado.png')
    set_background_image(background_image_path)
    
    st.title("Gerenciamento de Usuários e Agentes de Carga")
    logger.debug("Executando show_page da user_management_page.")

    # Inicialização de variáveis de estado da sessão para esta página
    if 'users_data_for_display' not in st.session_state:
        st.session_state.users_data_for_display = []
    if 'agents_data_for_display' not in st.session_state:
        st.session_state.agents_data_for_display = []

    # Variáveis de estado para formulários unificados
    if 'show_add_form' not in st.session_state:
        st.session_state.show_add_form = False
    if 'show_edit_form' not in st.session_state:
        st.session_state.show_edit_form = False
    if 'editing_user_id' not in st.session_state:
        st.session_state.editing_user_id = None
    if 'show_delete_confirm_popup' not in st.session_state:
        st.session_state.show_delete_confirm_popup = False
    if 'delete_user_id_to_confirm' not in st.session_state:
        st.session_state.delete_user_id_to_confirm = None
    if 'delete_user_name_to_confirm' not in st.session_state:
        st.session_state.delete_user_name_to_confirm = None
    if 'show_change_password_form' not in st.session_state:
        st.session_state.show_change_password_form = False
    if 'change_password_user_id' not in st.session_state:
        st.session_state.change_password_user_id = None
    if 'change_password_username' not in st.session_state:
        st.session_state.change_password_username = None


    # Exibir pop-ups se ativos (formulários unificados)
    if st.session_state.show_add_form:
        display_add_unified_form()
        return
    if st.session_state.show_edit_form:
        display_edit_unified_form()
        return
    if st.session_state.show_delete_confirm_popup:
        display_delete_unified_confirm_popup()
        return
    if st.session_state.show_change_password_form:
        display_change_password_unified_form()
        return


    # Botão para abrir o formulário de adição unificado
    if st.button("Adicionar Novo Usuário ou Agente de Carga", key="open_add_unified_form_btn"):
        st.session_state.show_add_form = True
        st.session_state.editing_user_id = None
        st.rerun()

    st.markdown("---")
    st.subheader("Gerenciamento de Usuários do Sistema")
    st.write("Gerencie usuários com acesso ao sistema principal (excluindo agentes de carga).")

    # Botão para adicionar novo usuário (não agente)
    if st.button("Adicionar Novo Usuário", key="add_regular_user_btn"):
        st.session_state.show_add_form = True
        st.session_state.editing_user_id = None
        st.rerun()

    st.markdown("#### Lista de Usuários")

    if st.session_state.get('firebase_ready', False):
        if not st.session_state.users_data_for_display:
            load_and_filter_users_and_agents_data()
        if not st.session_state.users_data_for_display:
            st.info("Nenhum usuário regular cadastrado ou dados ainda não carregados.")
    else:
        st.info("Aguardando conexão com o Firebase para carregar a lista de usuários...")

    df_users = pd.DataFrame(st.session_state.users_data_for_display)

    if not df_users.empty:
        column_config_users = {
            "id": st.column_config.TextColumn("ID", width="small"),
            "username": st.column_config.TextColumn("Usuário", width="medium"),
            "email": st.column_config.TextColumn("E-mail", width="medium"),
            "is_admin": st.column_config.TextColumn("Admin?", width="small"),
            "allowed_screens": st.column_config.TextColumn("Telas Permitidas", width="large")
        }

        df_users_display_ordered = df_users[["id", "username", "email", "is_admin", "allowed_screens"]]

        selected_user_row = st.dataframe(
            df_users_display_ordered, 
            column_config=column_config_users,
            hide_index=False,
            use_container_width=True,
            selection_mode="single-row",
            key="users_table",
            on_select="rerun"
        )

        if selected_user_row and selected_user_row.get('selection', {}).get('rows'):
            selected_index = selected_user_row['selection']['rows'][0]
            
            selected_user_id_from_display = df_users_display_ordered.iloc[selected_index]['id']
            selected_username_from_display = df_users_display_ordered.iloc[selected_index]['username']
            
            st.write(f"Usuário selecionado: {selected_username_from_display}")
            
            col1_user, col2_user, col3_user = st.columns(3)
            with col1_user:
                if st.button(f"Editar Usuário: {selected_username_from_display}", key=f"edit_user_{selected_user_id_from_display}"):
                    st.session_state.editing_user_id = selected_user_id_from_display
                    st.session_state.show_edit_form = True # Usa o formulário unificado
                    st.rerun()
            with col2_user:
                if st.button(f"Excluir Usuário: {selected_username_from_display}", key=f"delete_user_{selected_user_id_from_display}"):
                    st.session_state.delete_user_id_to_confirm = selected_user_id_from_display
                    st.session_state.delete_user_name_to_confirm = selected_username_from_display
                    st.session_state.show_delete_confirm_popup = True # Usa o popup unificado
                    st.rerun()
            with col3_user:
                if st.button(f"Alterar Senha Usuário: {selected_username_from_display}", key=f"change_password_user_{selected_user_id_from_display}"):
                    st.session_state.change_password_user_id = selected_user_id_from_display
                    st.session_state.change_password_username = selected_username_from_display
                    st.session_state.show_change_password_form = True # Usa o formulário unificado
                    st.rerun()
        else:
            st.info("Selecione um usuário na tabela para editar, excluir ou alterar a senha.")

    else:
        st.info("Nenhum usuário cadastrado. Adicione um novo usuário.")


    # --- Seção de Gerenciamento de Agentes de Carga ---
    st.markdown("---")
    st.subheader("Gerenciamento de Agentes de Carga")
    st.write("Gerencie agentes de carga que inserem cotações de frete.")

    # Botão para adicionar novo agente de carga
    if st.button("Adicionar Novo Agente de Carga", key="add_agent_btn"):
        st.session_state.show_add_form = True
        st.session_state.editing_user_id = None # Reinicia para o formulário de adição
        st.rerun()

    st.markdown("#### Lista de Agentes de Carga")

    if st.session_state.get('firebase_ready', False):
        if not st.session_state.agents_data_for_display:
            load_and_filter_users_and_agents_data() # Garante que os dados estejam carregados e filtrados
        if not st.session_state.agents_data_for_display:
            st.info("Nenhum agente de carga cadastrado ou dados ainda não carregados.")
    else:
        st.info("Aguardando conexão com o Firebase para carregar a lista de agentes de carga...")

    df_agents = pd.DataFrame(st.session_state.agents_data_for_display)

    if not df_agents.empty:
        column_config_agents = {
            "id": st.column_config.TextColumn("ID", width="small"),
            "username": st.column_config.TextColumn("Usuário Agente", width="medium"),
            "email": st.column_config.TextColumn("E-mail", width="medium"),
            "allowed_screens": st.column_config.TextColumn("Telas Permitidas", width="large")
        }
        # A coluna 'is_freight_agent' não precisa ser exibida, pois todos nesta tabela são agentes
        df_agents_display_ordered = df_agents[["id", "username", "email", "allowed_screens"]]

        selected_agent_row = st.dataframe(
            df_agents_display_ordered, 
            column_config=column_config_agents,
            hide_index=False,
            use_container_width=True,
            selection_mode="single-row",
            key="agents_table",
            on_select="rerun"
        )

        if selected_agent_row and selected_agent_row.get('selection', {}).get('rows'):
            selected_index = selected_agent_row['selection']['rows'][0]
            
            selected_agent_id_from_display = df_agents_display_ordered.iloc[selected_index]['id']
            selected_agent_username_from_display = df_agents_display_ordered.iloc[selected_index]['username']
            
            st.write(f"Agente de Carga selecionado: {selected_agent_username_from_display}")
            
            col1_agent, col2_agent, col3_agent = st.columns(3)
            with col1_agent:
                if st.button(f"Editar Agente: {selected_agent_username_from_display}", key=f"edit_agent_{selected_agent_id_from_display}"):
                    st.session_state.editing_user_id = selected_agent_id_from_display # Usa o mesmo ID para o formulário unificado
                    st.session_state.show_edit_form = True # Usa o formulário unificado
                    st.rerun()
            with col2_agent:
                if st.button(f"Excluir Agente: {selected_agent_username_from_display}", key=f"delete_agent_{selected_agent_id_from_display}"):
                    st.session_state.delete_user_id_to_confirm = selected_agent_id_from_display
                    st.session_state.delete_user_name_to_confirm = selected_agent_username_from_display
                    st.session_state.show_delete_confirm_popup = True # Usa o popup unificado
                    st.rerun()
            with col3_agent:
                if st.button(f"Alterar Senha Agente: {selected_agent_username_from_display}", key=f"change_password_agent_{selected_agent_id_from_display}"):
                    st.session_state.change_password_user_id = selected_agent_id_from_display
                    st.session_state.change_password_username = selected_agent_username_from_display
                    st.session_state.show_change_password_form = True # Usa o formulário unificado
                    st.rerun()
        else:
            st.info("Selecione um agente de carga na tabela para editar, excluir ou alterar a senha.")

    else:
        st.info("Nenhum agente de carga cadastrado. Adicione um novo agente de carga.")

    st.markdown("---")
    st.write("Esta tela permite gerenciar usuários e agentes de carga da aplicação, incluindo suas permissões de acesso às diferentes telas.")

