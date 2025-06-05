import streamlit as st
import pandas as pd
import logging
import hashlib # Para hashing de senha
import os # Para verificar a existência do DB
from typing import Dict, Optional, Any, List
from app_logic.utils import set_background_image, set_sidebar_background_image

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
    "Análise de Documentos",
    "Pagamentos Container",
    "Cálculo de Tributos TTCE",
    "Gerenciamento de Usuários"
]

# Importar funções do módulo de utilitários de banco de dados
import db_utils


logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# --- Funções de Lógica de Negócio (Interação com o DB) ---

def hash_password(password, username):
    """Cria um hash SHA-256 da senha usando o nome de usuário como salt."""
    # NOTA: Em produção, use bibliotecas mais seguras como bcrypt ou Argon2.
    password_salted = password + username
    return hashlib.sha256(password_salted.encode('utf-8')).hexdigest()

def adicionar_usuario_db(username, password, is_admin=False, allowed_screens_list=None):
    """Adiciona um novo usuário ao banco de dados."""
    db_path = db_utils.get_db_path("users")
    st.info(f"DEBUG: Caminho do DB de usuários: {db_path}") # Debugging: Mostra o caminho do DB
    conn = db_utils.connect_db(db_path)
    if conn is None:
        st.error("Não foi possível conectar ao banco de dados de usuários.")
        logger.error(f"Falha ao conectar ao DB de usuários em {db_path}") # Debugging: Loga falha de conexão
        return False

    try:
        cursor = conn.cursor()
        
        # Verifica se o nome de usuário já existe
        cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
        if cursor.fetchone():
            st.error(f"O nome de usuário '{username}' já existe.")
            logger.warning(f"Tentativa de adicionar usuário existente: {username}") # Debugging: Loga usuário existente
            return False

        password_hash = hash_password(password, username)
        allowed_screens_str = ",".join(allowed_screens_list) if allowed_screens_list else ""

        logger.info(f"DEBUG: Tentando inserir usuário '{username}' no DB.") # Debugging: Antes da inserção
        cursor.execute("INSERT INTO users (username, password_hash, is_admin, allowed_screens) VALUES (?, ?, ?, ?)",
                       (username, password_hash, 1 if is_admin else 0, allowed_screens_str))
        
        row_count = cursor.rowcount # Obtém o número de linhas afetadas
        logger.info(f"DEBUG: Linhas afetadas pela inserção: {row_count}") # Debugging: Linhas afetadas
        st.info(f"DEBUG: Linhas afetadas pela inserção: {row_count}") # Debugging: Mostra linhas afetadas no Streamlit

        conn.commit()
        logger.info(f"DEBUG: conn.commit() executado para o usuário '{username}'.") # Debugging: Confirma commit
        st.info(f"DEBUG: Commit no DB executado para o usuário '{username}'.") # Debugging: Mostra commit no Streamlit

        logger.info(f"Usuário '{username}' adicionado (Admin: {is_admin}, Telas: {allowed_screens_str}).")
        st.success(f"Usuário '{username}' adicionado com sucesso!")
        return True
    except Exception as e:
        logger.exception(f"Erro ao adicionar usuário '{username}'")
        st.error(f"Erro ao adicionar usuário ao banco de dados: {e}")
        conn.rollback()
        return False
    finally:
        if conn:
            conn.close()
            logger.info("DEBUG: Conexão com o DB de usuários fechada.") # Debugging: Confirma fechamento da conexão

def obter_todos_usuarios_db():
    """Obtém a lista de todos os usuários do banco de dados."""
    db_path = db_utils.get_db_path("users")
    st.info(f"DEBUG: Obtendo usuários do DB: {db_path}") # Debugging: Mostra o caminho do DB ao obter
    conn = db_utils.connect_db(db_path)
    if conn is None:
        st.error("Não foi possível conectar ao banco de dados de usuários.")
        logger.error(f"Falha ao conectar ao DB de usuários em {db_path} para obter usuários.") # Debugging: Loga falha de conexão
        return []
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id, username, is_admin, allowed_screens FROM users ORDER BY username")
        users = cursor.fetchall()
        logger.info(f"DEBUG: {len(users)} usuários obtidos do DB.") # Debugging: Quantidade de usuários obtidos
        return users
    except Exception as e:
        logger.exception("Erro ao obter todos os usuários")
        st.error(f"Erro ao ler usuários do banco de dados: {e}")
        return []
    finally:
        if conn:
            conn.close()

def obter_usuario_por_id_db(user_id: int):
    """Obtém os dados de um usuário específico pelo ID."""
    db_path = db_utils.get_db_path("users")
    conn = db_utils.connect_db(db_path)
    if conn is None:
        st.error("Não foi possível conectar ao banco de dados de usuários.")
        return None
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id, username, is_admin, allowed_screens FROM users WHERE id = ?", (user_id,))
        user_data = cursor.fetchone()
        return user_data # Retorna (id, username, is_admin, allowed_screens) ou None
    except Exception as e:
        logger.exception(f"Erro ao obter usuário com ID {user_id}")
        st.error(f"Erro ao buscar usuário ID {user_id} no banco de dados: {e}")
        return None
    finally:
        if conn:
            conn.close()

def atualizar_usuario_db(user_id: int, username: str, is_admin: bool, allowed_screens_list: Optional[list]):
    """Atualiza os dados de um usuário existente no banco de dados."""
    db_path = db_utils.get_db_path("users")
    conn = db_utils.connect_db(db_path)
    if conn is None:
        st.error("Não foi possível conectar ao banco de dados de usuários.")
        return False

    try:
        cursor = conn.cursor()
        # Verifica se o novo nome de usuário já existe e não é o próprio usuário sendo editado
        cursor.execute("SELECT id FROM users WHERE username = ? AND id != ?", (username, user_id))
        if cursor.fetchone():
            st.error(f"O nome de usuário '{username}' já existe para outro usuário.")
            return False

        # Verifica se é o último admin antes de remover o status de admin
        if not is_admin: # Se o usuário está sendo definido como NÃO admin
             cursor.execute("SELECT COUNT(*) FROM users WHERE is_admin = 1")
             admin_count = cursor.fetchone()[0]
             cursor.execute("SELECT id, is_admin FROM users WHERE id = ?", (user_id,)) # Obter o ID e status de admin do usuário atual
             user_was_admin_data = cursor.fetchone()

             if user_was_admin_data and user_was_admin_data[1] == 1 and admin_count == 1:
                  st.error("Não é possível remover o status de administrador do último usuário administrador.")
                  return False

        allowed_screens_str = ",".join(allowed_screens_list) if allowed_screens_list is not None else ""

        cursor.execute('''
            UPDATE users
            SET username = ?, is_admin = ?, allowed_screens = ?
            WHERE id = ?
        ''', (username, 1 if is_admin else 0, allowed_screens_str, user_id))
        conn.commit()
        if cursor.rowcount > 0:
            logger.info(f"Usuário com ID {user_id} atualizado (Username: {username}, Admin: {is_admin}, Telas: {allowed_screens_str}).")
            st.success(f"Usuário '{username}' atualizado com sucesso!")
            return True
        else:
            logger.warning(f"Tentativa de atualizar usuário ID {user_id}, mas não foi encontrado.")
            st.error(f"Falha ao atualizar usuário ID {user_id}.")
            return False
    except Exception as e:
        logger.exception(f"Erro ao atualizar usuário com ID {user_id}")
        st.error(f"Erro ao atualizar usuário no banco de dados: {e}")
        conn.rollback()
        return False
    finally:
        if conn:
            conn.close()

def atualizar_senha_usuario_db(user_id: int, new_password: str, username: str):
    """Atualiza a senha de um usuário específico."""
    db_path = db_utils.get_db_path("users")
    conn = db_utils.connect_db(db_path)
    if conn is None:
        st.error("Não foi possível conectar ao banco de dados de usuários.")
        return False

    try:
        cursor = conn.cursor()
        new_password_hash = hash_password(new_password, username)
        cursor.execute("UPDATE users SET password_hash = ? WHERE id = ?", (new_password_hash, user_id))
        conn.commit()
        if cursor.rowcount > 0:
            logger.info(f"Senha do usuário com ID {user_id} (Username: {username}) atualizada.")
            st.success(f"Senha do usuário '{username}' atualizada com sucesso!")
            return True
        else:
            logger.warning(f"Tentativa de atualizar senha do usuário ID {user_id}, mas não foi encontrado.")
            st.error(f"Falha ao atualizar senha do usuário ID {user_id}.")
            return False
    except Exception as e:
        logger.exception(f"Erro ao atualizar senha do usuário com ID {user_id}")
        st.error(f"Erro ao atualizar senha no banco de dados: {e}")
        conn.rollback()
        return False
    finally:
        if conn:
            conn.close()

def deletar_usuario_db(user_id):
    """Deleta um usuário do banco de dados pelo ID."""
    db_path = db_utils.get_db_path("users")
    conn = db_utils.connect_db(db_path)
    if conn is None:
        st.error("Não foi possível conectar ao banco de dados de usuários.")
        return False

    try:
        cursor = conn.cursor()
        # Verifica se é o último admin antes de deletar (opcional, mas boa prática)
        cursor.execute("SELECT COUNT(*) FROM users WHERE is_admin = 1")
        admin_count = cursor.fetchone()[0]
        logger.debug(f"Contagem de administradores antes da exclusão: {admin_count}") # Debugging

        cursor.execute("SELECT id, is_admin FROM users WHERE id = ?", (user_id,))
        user_data_to_delete = cursor.fetchone() # Obter todos os dados do usuário a ser excluído

        if user_data_to_delete:
            user_is_admin = user_data_to_delete[1] # Acessar o campo is_admin pelo índice
            logger.debug(f"Usuário a ser excluído (ID: {user_id}) é admin: {bool(user_is_admin)}") # Debugging

            if user_is_admin == 1 and admin_count == 1: # Se for admin e for o único admin
                st.error("Não é possível excluir o último usuário administrador.")
                return False

        # Se passou pela verificação, procede com a exclusão
        cursor.execute("DELETE FROM users WHERE id = ?", (user_id,))
        conn.commit()
        if cursor.rowcount > 0:
            logger.info(f"Usuário com ID {user_id} deletado.")
            st.success(f"Usuário excluído com sucesso!")
            return True
        else:
            logger.warning(f"Tentativa de deletar usuário ID {user_id}, mas não foi encontrado.")
            st.error(f"Falha ao excluir usuário ID {user_id}.")
            return False
    except Exception as e:
        logger.exception(f"Erro ao deletar usuário com ID {user_id}")
        st.error(f"Erro ao deletar usuário do banco de dados: {e}")
        conn.rollback()
        return False
    finally:
        if conn:
            conn.close()


# --- Funções de UI (Streamlit) ---

def load_users_data():
    """Carrega os usuários do DB e atualiza o estado da sessão para exibição."""
    users_raw = obter_todos_usuarios_db()
    users_list = []
    if users_raw:
        for user in users_raw:
            # Converte Row para dicionário para facilitar acesso
            user_dict = {
                "id": int(user[0]),  # Explicitly cast to int here
                "username": user[1],
                "is_admin": "Sim" if user[2] == 1 else "Não",
                "allowed_screens": user[3] if user[3] else "" # Converte para string vazia se NULL
            }
            users_list.append(user_dict)
    st.session_state.users_data_for_display = users_list
    logger.info(f"Carregados {len(users_list)} usuários para exibição.")


def display_add_user_form():
    """Exibe o formulário para adicionar um novo usuário."""
    with st.form("add_user_form", clear_on_submit=True):
        st.markdown("### Adicionar Novo Usuário")
        new_username = st.text_input("Nome de Usuário", key="new_username_input")
        new_password = st.text_input("Senha", type="password", key="new_password_input")
        new_is_admin = st.checkbox("É Administrador", key="new_is_admin_checkbox")

        st.markdown("##### Permissões de Tela:")
        selected_screens = []
        for screen in AVAILABLE_SCREENS_LIST:
            if st.checkbox(screen, key=f"add_perm_{screen}"):
                selected_screens.append(screen)

        if st.form_submit_button("Adicionar Usuário"):
            if new_username and new_password:
                if adicionar_usuario_db(new_username, new_password, new_is_admin, selected_screens):
                    load_users_data() # Recarrega a lista de usuários
                    st.session_state.show_add_user_form = False # Opcional: fechar formulário após sucesso
                    st.rerun()
            else:
                st.warning("Nome de usuário e senha são obrigatórios.")


def display_edit_user_form():
    """Exibe o formulário para editar um usuário existente."""
    user_id_to_edit = st.session_state.get('editing_user_id')
    
    if user_id_to_edit is None:
        st.error("Nenhum usuário selecionado para edição.")
        st.session_state.show_edit_user_form = False
        return

    user_data = obter_usuario_por_id_db(user_id_to_edit)
    if user_data is None:
        st.error(f"Usuário com ID {user_id_to_edit} não encontrado no banco de dados.")
        st.session_state.show_edit_user_form = False
        return

    initial_id, initial_username, initial_is_admin, initial_allowed_screens_str = user_data
    initial_allowed_screens_list = initial_allowed_screens_str.split(',') if initial_allowed_screens_str else []

    with st.form(f"edit_user_form_{initial_id}"):
        st.markdown(f"### Editar Usuário: {initial_username}")
        
        edited_username = st.text_input("Nome de Usuário", value=initial_username, key=f"edit_username_{initial_id}")
        edited_password = st.text_input("Nova Senha (deixe em branco para não alterar)", type="password", key=f"edit_password_{initial_id}")
        edited_is_admin = st.checkbox("É Administrador", value=bool(initial_is_admin), key=f"edit_is_admin_{initial_id}")

        st.markdown("##### Permissões de Tela:")
        edited_screens = []
        for screen in AVAILABLE_SCREENS_LIST:
            # Pre-seleciona as checkboxes com base nas permissões atuais
            if st.checkbox(screen, value=(screen in initial_allowed_screens_list), key=f"edit_perm_{initial_id}_{screen}"):
                edited_screens.append(screen)

        col_save, col_cancel = st.columns(2)
        with col_save:
            if st.form_submit_button("Salvar Alterações"):
                if atualizar_usuario_db(initial_id, edited_username, edited_is_admin, edited_screens):
                    if edited_password: # Se uma nova senha foi fornecida
                        atualizar_senha_usuario_db(initial_id, edited_password, edited_username)
                    load_users_data() # Recarrega a lista de usuários
                    st.session_state.show_edit_user_form = False
                    st.session_state.editing_user_id = None
                    st.rerun()
        with col_cancel:
            if st.form_submit_button("Cancelar"):
                st.session_state.show_edit_user_form = False
                st.session_state.editing_user_id = None
                st.rerun()


def display_delete_user_confirm_popup():
    """Exibe um pop-up de confirmação para exclusão de usuário."""
    user_id_to_delete = st.session_state.get('delete_user_id_to_confirm')
    user_name_to_delete = st.session_state.get('delete_user_name_to_confirm')

    if user_id_to_delete is None:
        st.session_state.show_delete_user_confirm_popup = False
        return

    with st.form(key=f"delete_user_confirm_form_{user_id_to_delete}"):
        st.markdown(f"### Confirmar Exclusão de Usuário")
        st.warning(f"Tem certeza que deseja excluir o usuário '{user_name_to_delete}' (ID: {user_id_to_delete})?")
        
        col_yes, col_no = st.columns(2)
        with col_yes:
            if st.form_submit_button("Sim, Excluir"):
                if deletar_usuario_db(user_id_to_delete):
                    load_users_data() # Recarrega a lista de usuários
                    st.session_state.show_delete_user_confirm_popup = False
                    st.session_state.delete_user_id_to_confirm = None
                    st.session_state.delete_user_name_to_confirm = None
                    st.rerun()
        with col_no:
            if st.form_submit_button("Não, Cancelar"):
                st.session_state.show_delete_user_confirm_popup = False
                st.session_state.delete_user_id_to_confirm = None
                st.session_state.delete_user_name_to_confirm = None
                st.rerun()


def show_page():
    background_image_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'assets', 'logo_navio_atracado.png')
    set_background_image(background_image_path)
    
    st.title("Gerenciamento de Usuários")
    logger.debug("Executando show_page da user_management_page.") # Debugging

    # Inicialização de variáveis de estado da sessão para esta página
    if 'users_data_for_display' not in st.session_state:
        st.session_state.users_data_for_display = []
    if 'show_add_user_form' not in st.session_state:
        st.session_state.show_add_user_form = False
    if 'show_edit_user_form' not in st.session_state:
        st.session_state.show_edit_user_form = False
    if 'editing_user_id' not in st.session_state:
        st.session_state.editing_user_id = None
    if 'show_delete_user_confirm_popup' not in st.session_state:
        st.session_state.show_delete_user_confirm_popup = False
    if 'delete_user_id_to_confirm' not in st.session_state:
        st.session_state.delete_user_id_to_confirm = None
    if 'delete_user_name_to_confirm' not in st.session_state:
        st.session_state.delete_user_name_to_confirm = None
    if 'show_change_password_form' not in st.session_state: # Novo estado para o formulário de alteração de senha
        st.session_state.show_change_password_form = False
    if 'change_password_user_id' not in st.session_state:
        st.session_state.change_password_user_id = None
    if 'change_password_username' not in st.session_state:
        st.session_state.change_password_username = None


    # Exibir pop-ups se ativos
    if st.session_state.show_add_user_form:
        display_add_user_form()
        return # Impede que o restante da página seja renderizado enquanto o formulário está ativo
    
    if st.session_state.show_edit_user_form:
        display_edit_user_form()
        return # Impede que o restante da página seja renderizado enquanto o formulário está ativo

    if st.session_state.show_delete_user_confirm_popup:
        display_delete_user_confirm_popup()
        return # Impede que o restante da página seja renderizado enquanto o pop-up está ativo

    # NOVO: Formulário de alteração de senha
    if st.session_state.show_change_password_form:
        display_change_password_form()
        return # Impede que o restante da página seja renderizado


    # Botão para abrir o formulário de adição de usuário
    if st.button("Adicionar Novo Usuário", key="open_add_user_form_btn"):
        st.session_state.show_add_user_form = True
        st.session_state.editing_user_id = None # Garante que é um novo
        st.rerun()

    st.markdown("---")
    st.markdown("### Lista de Usuários")

    # Carregar dados dos usuários para exibição
    if not st.session_state.users_data_for_display:
        load_users_data()

    df_users = pd.DataFrame(st.session_state.users_data_for_display)

    if not df_users.empty:
        # Colunas a serem exibidas e configuradas
        # Removendo ButtonColumn pois não é suportado na versão atual do Streamlit
        column_config = {
            "id": st.column_config.NumberColumn("ID", width="small"), 
            "username": st.column_config.TextColumn("Usuário", width="medium"),
            "is_admin": st.column_config.TextColumn("Admin?", width="small"),
            "allowed_screens": st.column_config.TextColumn("Telas Permitidas", width="large")
        }

        # Reordenar as colunas do DataFrame para que 'id' seja a primeira
        df_users_display_ordered = df_users[["id", "username", "is_admin", "allowed_screens"]]

        # Exibir a tabela de usuários
        selected_user_row = st.dataframe(
            df_users_display_ordered, 
            column_config=column_config,
            hide_index=False, # Manter False para mostrar o checkbox de seleção
            use_container_width=True,
            selection_mode="single-row",
            key="users_table",
            on_select="rerun" # Força um rerun quando uma linha é selecionada
        )

        # Lógica para botões de edição/exclusão baseada na seleção da tabela
        # Estes botões aparecerão ABAIXO da tabela quando uma linha for selecionada
        if selected_user_row and selected_user_row.get('selection', {}).get('rows'):
            selected_index = selected_user_row['selection']['rows'][0]
            
            # Obter o username da linha selecionada na tabela exibida
            selected_username_from_display = df_users_display_ordered.iloc[selected_index]['username']
            
            # Usar o username para buscar o ID correspondente na lista de dados original (st.session_state.users_data_for_display)
            selected_original_user = next((u for u in st.session_state.users_data_for_display if u.get('username') == selected_username_from_display), None)

            if selected_original_user:
                selected_user_id = selected_original_user['id']
                selected_username = selected_original_user['username']

                st.write(f"DEBUG: Usuário selecionado na tabela - ID: {selected_user_id}, Nome: {selected_username}")
                
                # Botões de ação abaixo da tabela
                col1, col2, col3 = st.columns(3)
                with col1:
                    if st.button(f"Editar Usuário: {selected_username}", key=f"edit_user_{selected_user_id}"):
                        st.session_state.editing_user_id = selected_user_id
                        st.session_state.show_edit_user_form = True
                        st.rerun()
                with col2:
                    if st.button(f"Excluir Usuário: {selected_username}", key=f"delete_user_{selected_user_id}"):
                        st.session_state.delete_user_id_to_confirm = selected_user_id
                        st.session_state.delete_user_name_to_confirm = selected_username
                        st.session_state.show_delete_user_confirm_popup = True
                        st.rerun()
                with col3:
                    if st.button(f"Alterar Senha: {selected_username}", key=f"change_password_{selected_user_id}"):
                        st.session_state.change_password_user_id = selected_user_id
                        st.session_state.change_password_username = selected_username
                        st.session_state.show_change_password_form = True
                        st.rerun()
        else:
            st.info("Selecione um usuário na tabela para editar, excluir ou alterar a senha.")

    else:
        st.info("Nenhum usuário cadastrado. Adicione um novo usuário.")

    st.markdown("---")
    st.write("Esta tela permite gerenciar usuários da aplicação, incluindo suas permissões de acesso às diferentes telas.")

# NOVO: Função para exibir o formulário de alteração de senha
def display_change_password_form():
    user_id = st.session_state.get('change_password_user_id')
    username = st.session_state.get('change_password_username')

    if user_id is None or username is None:
        st.error("Nenhum usuário selecionado para alterar a senha.")
        st.session_state.show_change_password_form = False
        return

    with st.form(key=f"change_password_form_{user_id}"):
        st.markdown(f"### Alterar Senha para: {username}")
        new_password = st.text_input("Nova Senha", type="password", key=f"new_password_input_{user_id}")
        confirm_password = st.text_input("Confirmar Nova Senha", type="password", key=f"confirm_password_input_{user_id}")

        col_save, col_cancel = st.columns(2)
        with col_save:
            if st.form_submit_button("Salvar Nova Senha"):
                if new_password and confirm_password:
                    if new_password == confirm_password:
                        if atualizar_senha_usuario_db(user_id, new_password, username):
                            st.session_state.show_change_password_form = False
                            st.session_state.change_password_user_id = None
                            st.session_state.change_password_username = None
                            st.rerun()
                        # Mensagem de erro já é tratada por atualizar_senha_usuario_db
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
