import streamlit as st
import pandas as pd
import io # Para manipulação de arquivos em memória
import openpyxl # Para gerar e ler arquivos Excel
import logging
from datetime import datetime # Importar datetime para uso em datas
import os # Importar os para manipulação de caminhos
import base64 # Importar base64 para codificar imagens

# Importar funções do novo módulo de utilitários de banco de dados
# Assumimos que db_utils.py existe e está no PYTHONPATH ou no mesmo diretório/subdiretório 'app_logic'
# Como db_utils está no diretório pai, ajustamos o import
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import db_utils


logger = logging.getLogger(__name__)

# Mapeamento de colunas (precisa ser consistente com seu main.py original)
_COLS_MAP_PRODUTOS = {
    "id": {"text": "ID/Key ERP", "width": 120, "col_id": "id_key_erp"},
    "nome": {"text": "Nome/Part", "width": 200, "col_id": "nome_part"},
    "desc": {"text": "Descrição", "width": 350, "col_id": "descricao"},
    "ncm": {"text": "NCM", "width": 100, "col_id": "ncm"}
}

# --- Função para definir imagem de fundo com opacidade (copiada de app_main.py) ---
def set_background_image(image_path):
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


# --- Funções Auxiliares de Formatação ---
def _format_ncm(ncm_value):
    """Formata o NCM para o padrão xxxx.xx.xx."""
    if ncm_value and isinstance(ncm_value, str) and len(ncm_value) == 8:
        return f"{ncm_value[0:4]}.{ncm_value[4:6]}.{ncm_value[6:8]}"
    return ncm_value

# --- Funções para interagir com o DB (adaptadas para Streamlit) ---
def load_produtos():
    """Carrega todos os produtos do DB e atualiza o estado da sessão."""
    db_path = db_utils.get_db_path("produtos") # Assume que 'produtos' é um tipo de DB no db_utils
    if not db_path:
        st.error("Caminho do banco de dados de produtos não configurado. Por favor, verifique a configuração de 'db_utils'.")
        st.session_state.produtos_data = []
        # Garante que o DataFrame de sessão tenha as colunas esperadas, mesmo que vazio
        st.session_state.produtos_data_df = pd.DataFrame(columns=[col_info['col_id'] for col_info in _COLS_MAP_PRODUTOS.values()])
        return

    conn = db_utils.connect_db(db_path)
    if conn is None: # connect_db retorna None em caso de falha
        st.error("Não foi possível conectar ao banco de dados de produtos. Verifique os logs para detalhes da conexão.")
        st.session_state.produtos_data = []
        # Garante que o DataFrame de sessão tenha as colunas esperadas, mesmo que vazio
        st.session_state.produtos_data_df = pd.DataFrame(columns=[col_info['col_id'] for col_info in _COLS_MAP_PRODUTOS.values()])
        return

    try:
        produtos = db_utils.selecionar_todos_produtos(db_path)
        conn.close() # Fechar a conexão após a operação

        # Converte para lista de dicionários para facilitar o uso no Streamlit
        # Garante que as chaves do dicionário correspondem aos col_id do _COLS_MAP_PRODUTOS
        produtos_dicts = []
        for p_tuple in produtos:
            p_dict = {}
            for i, col_info in enumerate(_COLS_MAP_PRODUTOS.values()):
                p_dict[col_info['col_id']] = p_tuple[i]
            produtos_dicts.append(p_dict)

        st.session_state.produtos_data = produtos_dicts
        
        # --- NOVO: Inicialização robusta do DataFrame de sessão ---
        expected_cols = [col_info['col_id'] for col_info in _COLS_MAP_PRODUTOS.values()]
        if produtos_dicts:
            st.session_state.produtos_data_df = pd.DataFrame(st.session_state.produtos_data)
        else:
            # Cria um DataFrame vazio, mas com as colunas definidas
            st.session_state.produtos_data_df = pd.DataFrame(columns=expected_cols)
        # --- Fim da Inicialização robusta ---
        
        # Formatar NCM para exibição (apenas se o DataFrame não estiver vazio após a criação)
        if not st.session_state.produtos_data_df.empty:
            st.session_state.produtos_data_df['ncm'] = st.session_state.produtos_data_df['ncm'].apply(_format_ncm)

        logger.info(f"Carregados {len(produtos)} produtos do DB.")
        if not produtos:
            st.info("Nenhum produto encontrado no banco de dados. Adicione um novo ou importe via Excel.")
    except Exception as e:
        st.error(f"Erro ao carregar produtos do banco de dados: {e}. Verifique a estrutura da tabela e os dados.")
        logger.exception("Erro durante o carregamento de produtos.")
        st.session_state.produtos_data = []
        # Garante o DataFrame com colunas definidas MESMO em caso de erro
        st.session_state.produtos_data_df = pd.DataFrame(columns=[col_info['col_id'] for col_info in _COLS_MAP_PRODUTOS.values()])
    finally:
        if conn:
            conn.close()


def add_or_update_produto(produto_id, nome, desc, ncm):
    """Adiciona ou atualiza um produto no DB."""
    db_path = db_utils.get_db_path("produtos") # Assume que 'produtos' é um tipo de DB no db_utils
    if not db_path:
        st.error("Caminho do banco de dados de produtos não configurado.")
        return False

    # Validação básica
    if not produto_id or not nome or not desc or not ncm:
        st.error("Todos os campos (ID/Key ERP, Nome, Descrição, NCM) são obrigatórios.")
        return False
    if ' ' in str(produto_id):
        st.error("ID/Key ERP não pode conter espaços.")
        return False

    produto_tuple = (str(produto_id), nome, desc, ncm)
    if db_utils.inserir_ou_atualizar_produto(db_path, produto_tuple):
        st.success(f"Produto '{nome}' (ID: {produto_id}) salvo com sucesso!")
        load_produtos() # Recarrega a tabela
        return True
    else:
        # A função db_utils.inserir_ou_atualizar_produto já loga o erro,
        # mas podemos dar um feedback genérico ao usuário aqui.
        st.error(f"Falha ao salvar produto '{nome}' (ID: {produto_id}). Verifique os logs para detalhes.")
        return False

def delete_produto_from_db(produto_id):
    """Deleta um produto do DB."""
    db_path = db_utils.get_db_path("produtos") # Assume que 'produtos' é um tipo de DB no db_utils
    if not db_path:
        st.error("Caminho do banco de dados de produtos não configurado.")
        return False
    
    if db_utils.deletar_produto(db_path, produto_id):
        st.success(f"Produto ID '{produto_id}' excluído com sucesso!")
        # Remove da lista de seleção se estiver lá
        # st.session_state.produtos_selecionados_ids_list é para multi-seleção/exportação
        if produto_id in st.session_state.get('produtos_selecionados_ids_list', []):
            st.session_state.produtos_selecionados_ids_list.remove(produto_id)
        st.session_state.selected_produto_id = None # Limpa a seleção
        load_produtos() # Recarrega a tabela
        return True
    else:
        st.error(f"Falha ao excluir o produto ID '{produto_id}'. Verifique os logs.")
        return False

def export_selected_products():
    """Exporta produtos selecionados para Excel/TXT, incluindo IDs não encontrados."""
    db_path = db_utils.get_db_path("produtos")
    if not db_path:
        st.error("Caminho do banco de dados de produtos não configurado.")
        return

    if not st.session_state.get('produtos_selecionados_ids_list'):
        st.warning("Nenhum produto selecionado para exportar.")
        return

    # Prepare a dictionary for quick lookup of existing products from the session state
    # Garante que st.session_state.produtos_data exista e seja uma lista de dicionários
    all_products_dict_by_id = {p.get('id_key_erp'): p for p in st.session_state.get('produtos_data', []) if p.get('id_key_erp')}

    products_to_export = []
    not_found_count = 0

    for prod_id in st.session_state.produtos_selecionados_ids_list:
        if prod_id in all_products_dict_by_id:
            products_to_export.append(all_products_dict_by_id[prod_id])
        else:
            # Create a "Não encontrado" entry for missing IDs
            not_found_item = {col_info['col_id']: "" for col_info in _COLS_MAP_PRODUTOS.values()}
            not_found_item['id_key_erp'] = prod_id
            not_found_item['nome_part'] = "Não encontrado"
            not_found_item['descricao'] = "Produto não encontrado no banco de dados."
            not_found_item['ncm'] = "" # Ensure NCM is empty for not found
            products_to_export.append(not_found_item)
            not_found_count += 1

    if not products_to_export:
        st.error("Não foi possível obter os dados dos produtos selecionados para exportar.")
        return

    # Create DataFrame for export
    col_db = [info['col_id'] for info in _COLS_MAP_PRODUTOS.values()]
    col_hdr = [info['text'] for info in _COLS_MAP_PRODUTOS.values()]
    df_export = pd.DataFrame(products_to_export, columns=col_db)
    df_export.rename(columns=dict(zip(col_db, col_hdr)), inplace=True)

    excel_buffer = io.BytesIO()
    df_export.to_excel(excel_buffer, index=False, engine='openpyxl')
    excel_buffer.seek(0)

    st.download_button(
        label="Baixar Excel de Selecionados",
        data=excel_buffer,
        file_name="Produtos Exportados.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key="download_selected_excel_button"
    )
    success_message = f"Exportado {len(products_to_export)} produtos selecionados."
    if not_found_count > 0:
        success_message += f" ({not_found_count} não encontrados)."
    st.success(success_message)


def import_excel_products(uploaded_file):
    """Importa produtos de arquivo Excel."""
    db_path = db_utils.get_db_path("produtos") # Assume que 'produtos' é um tipo de DB no db_utils
    if not db_path:
        st.error("Caminho do banco de dados de produtos não configurado.")
        return

    try:
        df = pd.read_excel(uploaded_file, dtype=str)
        df.fillna('', inplace=True)
    except Exception as e:
        st.error(f"Erro ao ler arquivo Excel: {e}")
        logger.exception("Erro leitura Excel de produtos.")
        return

    # Pré-processamento: Remover espaços dos nomes das colunas para facilitar a busca.
    df.columns = df.columns.str.replace(' ', '', regex=False)

    # Cria um mapeamento flexível de colunas do Excel para as colunas do DB
    excel_to_db_col_map = {}
    for db_col_info in _COLS_MAP_PRODUTOS.values():
        db_col_id = db_col_info['col_id']
        db_col_text = db_col_info['text']
        
        # Prioriza o col_id exato, depois o nome amigável (sem espaços), depois o nome amigável
        if db_col_id in df.columns:
            excel_to_db_col_map[db_col_id] = db_col_id
        elif db_col_text.replace(' ', '') in df.columns:
             excel_to_db_col_map[db_col_id] = db_col_text.replace(' ', '')
        elif db_col_text in df.columns:
            excel_to_db_col_map[db_col_id] = db_col_text
        else:
            st.error(f"Coluna obrigatória '{db_col_text}' (ou '{db_col_id}') não encontrada no arquivo Excel.")
            return

    imported_count = 0
    error_count = 0
    
    for index, row in df.iterrows():
        try:
            # Mapeia os dados da linha do Excel para o formato do produto esperado pelo DB
            # Garante que a ordem e o tipo sejam consistentes
            prod_data_from_excel = {
                db_col_info['col_id']: str(row[excel_to_db_col_map[db_col_info['col_id']]]).strip()
                for db_col_info in _COLS_MAP_PRODUTOS.values()
            }
            
            # Converte para tupla na ordem correta para inserir_ou_atualizar_produto
            produto_tuple = (
                prod_data_from_excel[_COLS_MAP_PRODUTOS['id']['col_id']],
                prod_data_from_excel[_COLS_MAP_PRODUTOS['nome']['col_id']],
                prod_data_from_excel[_COLS_MAP_PRODUTOS['desc']['col_id']],
                prod_data_from_excel[_COLS_MAP_PRODUTOS['ncm']['col_id']]
            )
            
            # Basic validation (ID not empty, no spaces in ID)
            id_p = produto_tuple[0]
            if not id_p:
                logger.warning(f"Linha {index+2}: ID de produto vazio, ignorado.")
                error_count += 1
                continue
            if ' ' in id_p:
                st.warning(f"Linha {index+2}: ID de produto '{id_p}' contém espaços, ignorado.")
                error_count += 1
                continue
            
            if db_utils.inserir_ou_atualizar_produto(db_path, produto_tuple):
                imported_count += 1
            else:
                error_count += 1 # inserir_ou_atualizar_produto already logs/shows error
        except KeyError as e:
            st.warning(f"Linha {index+2} ignorada: Coluna '{e}' não encontrada ou problema no mapeamento. Erro: {e}")
            error_count += 1
        except Exception as e:
            st.error(f"Erro ao processar linha {index+2} do Excel para produtos: {e}")
            error_count += 1

    st.success(f"{imported_count} produtos importados/atualizados.")
    if error_count > 0:
        st.warning(f"{error_count} linhas com erro/ignoradas. Verifique os logs.")
    
    load_produtos() # Recarrega a tabela

def show_page():
    # --- Configuração da Imagem de Fundo para a página Descrições ---
    # Certifique-se de que o caminho para a imagem esteja correto
    background_image_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'assets', 'logo_navio_atracado.png')
    set_background_image(background_image_path)
    # --- Fim da Configuração da Imagem de Fundo ---

    st.subheader("Gerenciamento de Produtos / Descrições")

    # --- Estado da Sessão para esta página ---
    if 'produtos_data' not in st.session_state:
        st.session_state.produtos_data = []
    # NOVO: Garante que produtos_data_df seja um DataFrame vazio com colunas
    if 'produtos_data_df' not in st.session_state:
        st.session_state.produtos_data_df = pd.DataFrame(columns=[col_info['col_id'] for col_info in _COLS_MAP_PRODUTOS.values()])
    if 'selected_produto_id' not in st.session_state:
        st.session_state.selected_produto_id = None
    if 'produtos_selecionados_ids_list' not in st.session_state: # Para a lista de seleção múltipla
        st.session_state.produtos_selecionados_ids_list = []
    if 'descricoes_search_terms' not in st.session_state: # Para campos de pesquisa
        st.session_state.descricoes_search_terms = {col_info['col_id']: "" for col_info in _COLS_MAP_PRODUTOS.values()}
    if 'open_form_button_clicked' not in st.session_state:
        st.session_state.open_form_button_clicked = False # Flag para controlar a abertura do formulário
    if 'selected_produto_for_removal_from_list' not in st.session_state: # Para remover da lista de selecionados
        st.session_state.selected_produto_for_removal_from_list = None
    # Novo estado para forçar a re-renderização do dataframe principal
    if 'produtos_table_editor_key_counter' not in st.session_state:
        st.session_state.produtos_table_editor_key_counter = 0
    # Novo estado para a seleção na tabela de produtos selecionados
    if 'selected_products_list_selection' not in st.session_state:
        st.session_state.selected_products_list_selection = {'rows': []}
    # Novo estado para controlar a visibilidade do expander de pesquisa múltipla
    if 'show_multi_search_expander' not in st.session_state: # Alterado para expander
        st.session_state.show_multi_search_expander = False
    # Novo estado para armazenar os resultados da pesquisa múltipla
    if 'multi_search_results_df' not in st.session_state:
        st.session_state.multi_search_results_df = pd.DataFrame()
    # Novo estado para controlar a key do text_area de IDs múltiplos
    if 'multi_id_search_input_key' not in st.session_state:
        st.session_state.multi_id_search_input_key = 0
    # NOVO: Estado para armazenar o valor do text_area de pesquisa múltipla
    if 'multi_id_search_input_value' not in st.session_state:
        st.session_state.multi_id_search_input_value = ""


    # Garante que os dados sejam carregados na primeira execução ou se o estado mudar
    # Apenas carrega se os dados ainda não estiverem presentes ou se o DB não foi inicializado
    # (mas a inicialização do DB é mais robusta agora em app_main)
    if not st.session_state.produtos_data_df.empty: # Se o DataFrame já foi populado com dados
        pass # Não recarrega, mantém o estado atual
    else: # Se o DataFrame está vazio (primeira carga ou erro anterior)
        load_produtos() # Chamar load_produtos para carregar os dados
        # Após a carga, ainda pode estar vazio se não houver produtos no DB

    # --- UI Layout ---

    # --- Seção de Pesquisa ---
    st.markdown("#### Pesquisar Produtos")
    with st.expander("Filtros de Pesquisa"):
        search_col1, search_col2, search_col3, search_col4 = st.columns(4)
        with search_col1:
            st.session_state.descricoes_search_terms['id_key_erp'] = st.text_input("ID/Key ERP", value=st.session_state.descricoes_search_terms.get('id_key_erp', ''), key="search_id_key_erp")
        with search_col2:
            st.session_state.descricoes_search_terms['nome_part'] = st.text_input("Nome/Part", value=st.session_state.descricoes_search_terms.get('nome_part', ''), key="search_nome_part")
        with search_col3:
            st.session_state.descricoes_search_terms['descricao'] = st.text_input("Descrição", value=st.session_state.descricoes_search_terms.get('descricao', ''), key="search_descricao")
        with search_col4:
            st.session_state.descricoes_search_terms['ncm'] = st.text_input("NCM", value=st.session_state.descricoes_search_terms.get('ncm', ''), key="search_ncm")

        search_button_col, clear_search_button_col = st.columns(2)
        with search_button_col:
            if st.button("Aplicar Pesquisa", key="apply_search_button"):
                # Rerun para aplicar filtros
                st.rerun()
        with clear_search_button_col:
            if st.button("Limpar Pesquisa", key="clear_search_button"):
                st.session_state.descricoes_search_terms = {col_info['col_id']: "" for col_info in _COLS_MAP_PRODUTOS.values()}
                st.session_state.produtos_table_editor_key_counter += 1 # Força a re-renderização do dataframe principal
                st.rerun()

    # Aplicar filtros à exibição do DataFrame
    filtered_df_display = st.session_state.produtos_data_df.copy()

    # --- NOVO: Bloco de proteção extra: Garante que as colunas de pesquisa existam no DataFrame ---
    expected_search_cols = [col_info['col_id'] for col_info in _COLS_MAP_PRODUTOS.values()]
    for col in expected_search_cols:
        if col not in filtered_df_display.columns:
            # Adiciona a coluna com valores nulos (NaN/NaT) se não existir para evitar KeyError
            filtered_df_display[col] = pd.NA 
    # --- Fim do bloco de proteção extra ---

    for col_id, search_term in st.session_state.descricoes_search_terms.items():
        if search_term:
            # Verifica se a coluna existe ANTES de tentar filtrá-la
            if col_id in filtered_df_display.columns:
                # Converte para string e aplica o filtro de contém (case-insensitive)
                # O parâmetro 'na=False' garante que valores NaN/None não causem erro no .str.contains
                filtered_df_display = filtered_df_display[
                    filtered_df_display[col_id].astype(str).str.contains(search_term, case=False, na=False)
                ]
            else:
                # Loga um aviso se uma coluna de pesquisa não for encontrada (útil para depuração)
                logger.warning(f"Coluna de pesquisa '{col_id}' não encontrada em filtered_df_display para filtragem. Ignorando este filtro.")


    # Botões de Ação Principal
    col_add = st.columns(1)[0] # Apenas uma coluna para o botão "Adicionar Novo Produto"
    with col_add:
        if st.button("Adicionar Novo Produto", key="add_new_produto_button"):
            st.session_state.selected_produto_id = None
            st.session_state.open_form_button_clicked = True
            st.rerun()
    
    # --- Formulário de Adição/Edição ---
    if st.session_state.selected_produto_id is not None or st.session_state.get('open_form_button_clicked', False):
        with st.form(key="produto_form"):
            st.markdown("##### Adicionar/Editar Produto")
            
            initial_data = {}
            is_editing = False
            if st.session_state.selected_produto_id:
                produto_data_row = db_utils.selecionar_produto_por_id(db_utils.get_db_path("produtos"), st.session_state.selected_produto_id)
                if produto_data_row:
                    initial_data = {col_info['col_id']: produto_data_row[i] for i, col_info in enumerate(_COLS_MAP_PRODUTOS.values())}
                    is_editing = True
                    st.write(f"Editando Produto: **{initial_data.get('nome_part', '')}** (ID: **{initial_data.get('id_key_erp', '')}**)")
                else:
                    st.warning("Produto selecionado não encontrado. Adicionando um novo.")
                    st.session_state.selected_produto_id = None
                    st.session_state.open_form_button_clicked = True
            else:
                st.write("Adicionar Novo Produto")
                st.session_state.open_form_button_clicked = True

            produto_id_input = st.text_input(
                _COLS_MAP_PRODUTOS['id']['text'],
                value=initial_data.get('id_key_erp', ''),
                disabled=is_editing,
                key="produto_id_form_input"
            )
            nome_input = st.text_input(_COLS_MAP_PRODUTOS['nome']['text'], value=initial_data.get('nome_part', ''), key="nome_form_input")
            desc_input = st.text_area(_COLS_MAP_PRODUTOS['desc']['text'], value=initial_data.get('descricao', ''), key="desc_form_input")
            ncm_input = st.text_input(_COLS_MAP_PRODUTOS['ncm']['text'], value=_format_ncm(initial_data.get('ncm', '')), key="ncm_form_input")

            col_submit_delete, col_cancel = st.columns(2)
            with col_submit_delete:
                if st.form_submit_button("Salvar Produto"):
                    if add_or_update_produto(produto_id_input, nome_input, desc_input, ncm_input):
                        st.session_state.selected_produto_id = None
                        st.session_state.open_form_button_clicked = False
                        st.rerun()
                if is_editing:
                    if col_submit_delete.form_submit_button("Excluir Produto"):
                        # NOVO: Adiciona um checkbox de confirmação para exclusão de item único
                        confirm_single_delete = st.checkbox("Confirmar exclusão deste produto?", key=f"confirm_single_delete_product_{produto_id_input}")
                        if confirm_single_delete:
                            if delete_produto_from_db(produto_id_input):
                                st.session_state.selected_produto_id = None
                                st.session_state.open_form_button_clicked = False
                                del st.session_state[f'confirm_single_delete_product_{produto_id_input}'] # Limpa o estado da confirmação
                                st.rerun()
                            else:
                                st.error("Falha ao excluir o produto.")
                        else:
                            st.warning(f"Marque a caixa para confirmar a exclusão de '{nome_input}'.")

            with col_cancel:
                if col_cancel.form_submit_button("Cancelar"):
                    st.session_state.selected_produto_id = None
                    st.session_state.open_form_button_clicked = False
                    # Limpa os estados de confirmação se o formulário for cancelado
                    if f'confirm_single_delete_product_{produto_id_input}' in st.session_state:
                         del st.session_state[f'confirm_single_delete_product_{produto_id_input}']
                    st.rerun()

    # --- Tabela de Produtos ---
    st.markdown("##### Produtos Cadastrados")

    if not filtered_df_display.empty:
        columns_config = {
            "id_key_erp": st.column_config.TextColumn(_COLS_MAP_PRODUTOS['id']['text'], width="small"),
            "nome_part": st.column_config.TextColumn(_COLS_MAP_PRODUTOS['nome']['text'], width="medium"),
            "descricao": st.column_config.TextColumn(_COLS_MAP_PRODUTOS['desc']['text'], width="large"),
            "ncm": st.column_config.TextColumn(_COLS_MAP_PRODUTOS['ncm']['text'], width="small"),
        }

        selected_rows_data = st.dataframe(
            filtered_df_display,
            column_config=columns_config,
            hide_index=True,
            use_container_width=True,
            key=f"produtos_table_editor_{st.session_state.produtos_table_editor_key_counter}",
            selection_mode="multi-row",
            on_select="rerun" # Mantém rerun para ação imediata dos botões abaixo
        )
        
        # --- NOVO: Sincronização da lista de selecionados com a seleção da tabela principal ---
        # Recria a lista de produtos selecionados com base na seleção atual da tabela principal
        current_main_table_selected_ids = {filtered_df_display.iloc[idx]['id_key_erp'] for idx in selected_rows_data.get('selection', {}).get('rows', [])}
        st.session_state.produtos_selecionados_ids_list = list(current_main_table_selected_ids)
        # --- Fim da sincronização ---
            
        col_edit_main_table, col_delete_main_table = st.columns(2)
        with col_edit_main_table:
            edit_disabled = len(st.session_state.produtos_selecionados_ids_list) != 1
            if st.button("Editar Selecionado", key="edit_selected_main_table", disabled=edit_disabled):
                st.session_state.selected_produto_id = st.session_state.produtos_selecionados_ids_list[0]
                st.session_state.open_form_button_clicked = True
                st.rerun()
        with col_delete_main_table:
            delete_disabled = len(st.session_state.produtos_selecionados_ids_list) == 0
            if st.button("Excluir Selecionado", key="delete_selected_main_table", disabled=delete_disabled):
                # NOVO: Pop-up de confirmação para exclusão em massa
                if len(st.session_state.produtos_selecionados_ids_list) > 0:
                    with st.popover("Confirmar Exclusão Múltipla"):
                        st.warning(f"Tem certeza que deseja excluir {len(st.session_state.produtos_selecionados_ids_list)} produtos selecionados?")
                        if st.button("Sim, Excluir Todos Confirmado", key="confirm_delete_all_button_popover"):
                            for prod_id in st.session_state.produtos_selecionados_ids_list:
                                delete_produto_from_db(prod_id)
                            st.session_state.produtos_selecionados_ids_list = [] # Limpa a lista após exclusão
                            st.session_state.produtos_table_editor_key_counter += 1 # Força reload
                            st.rerun()
                        if st.button("Cancelar", key="cancel_delete_all_button_popover"):
                            pass # Apenas fecha o popover
                else:
                    st.warning("Selecione produtos para excluir.")
    else:
        st.info("Nenhum produto cadastrado. Adicione um novo ou importe via Excel.")

    st.markdown("---")

    # --- Expander de Pesquisa Múltipla (agora acima de Produtos Selecionados) ---
    with st.expander("Pesquisar Múltiplos Produtos por ID", expanded=st.session_state.show_multi_search_expander):
        st.write("Insira os IDs dos produtos (um por linha):")

        # Usando a key dinâmica para permitir a limpeza do text_area
        st.session_state.multi_id_search_input_value = st.text_area("IDs dos Produtos", value=st.session_state.multi_id_search_input_value, height=150, key=f"multi_id_search_input_expander_{st.session_state.multi_id_search_input_key}")

        col_search_expander, col_add_expander, col_close_expander = st.columns(3)

        with col_search_expander:
            if st.button("Buscar Produtos", key="search_multi_ids_button_expander"):
                search_ids = [id.strip() for id in st.session_state.multi_id_search_input_value.split('\n') if id.strip()]
                if search_ids:
                    db_path = db_utils.get_db_path("produtos")
                    
                    # Get all products to check against
                    all_products_in_db_raw = db_utils.selecionar_todos_produtos(db_path)
                    # Converte para dicionários para facilitar a busca
                    all_products_dict = {p[0]: {col_info['col_id']: p[i] for i, col_info in enumerate(_COLS_MAP_PRODUTOS.values())} for p in all_products_in_db_raw}

                    results_for_display = []
                    found_count = 0
                    for s_id in search_ids:
                        if s_id in all_products_dict:
                            results_for_display.append(all_products_dict[s_id])
                            found_count += 1
                        else:
                            # Add "Não encontrado" for missing IDs
                            not_found_item = {col_info['col_id']: "" for col_info in _COLS_MAP_PRODUTOS.values()}
                            not_found_item['id_key_erp'] = s_id
                            not_found_item['nome_part'] = "Não encontrado" # Marcar como não encontrado
                            not_found_item['descricao'] = "Produto não encontrado no banco de dados."
                            not_found_item['ncm'] = ""
                            results_for_display.append(not_found_item)

                    df_found = pd.DataFrame(results_for_display)
                    if not df_found.empty:
                        df_found['ncm'] = df_found['ncm'].apply(_format_ncm)
                    st.session_state.multi_search_results_df = df_found
                    st.success(f"Busca concluída. {found_count} produtos encontrados.")
                else:
                    st.session_state.multi_search_results_df = pd.DataFrame()
                    st.warning("Por favor, insira IDs para buscar.")
        
        if not st.session_state.multi_search_results_df.empty:
            st.markdown("---")
            st.write("Resultados da Pesquisa:")
            st.dataframe(
                st.session_state.multi_search_results_df[[col_info['col_id'] for col_info in _COLS_MAP_PRODUTOS.values()]],
                column_config={
                    "id_key_erp": st.column_config.TextColumn(_COLS_MAP_PRODUTOS['id']['text'], width="small"),
                    "nome_part": st.column_config.TextColumn(_COLS_MAP_PRODUTOS['nome']['text'], width="medium"),
                    "descricao": st.column_config.TextColumn(_COLS_MAP_PRODUTOS['desc']['text'], width="large"),
                    "ncm": st.column_config.TextColumn(_COLS_MAP_PRODUTOS['ncm']['text'], width="small"),
                },
                hide_index=True,
                use_container_width=True,
                key="multi_search_results_table_expander"
            )
            with col_add_expander:
                if st.button("Adicionar Resultados à Lista", key="add_multi_search_to_list_button_expander"):
                    added_count = 0
                    # Itera sobre os resultados da pesquisa, adicionando APENAS IDs encontrados à lista
                    for _, row in st.session_state.multi_search_results_df.iterrows():
                        prod_id = row['id_key_erp']
                        if prod_id != "Não encontrado" and prod_id not in st.session_state.produtos_selecionados_ids_list:
                            st.session_state.produtos_selecionados_ids_list.append(prod_id)
                            added_count += 1
                    st.success(f"{added_count} produtos adicionados à lista de selecionados.")
                    st.session_state.show_multi_search_expander = False # Fecha o expander
                    st.session_state.multi_id_search_input_value = "" # Limpa o campo de texto
                    st.session_state.multi_id_search_input_key += 1 # Força a re-renderização
                    st.rerun()
        
        with col_close_expander:
            if st.button("Fechar Pesquisa Múltipla", key="close_multi_search_expander_button"):
                st.session_state.show_multi_search_expander = False
                st.session_state.multi_search_results_df = pd.DataFrame() # Limpa resultados ao fechar
                st.session_state.multi_id_search_input_value = "" # Limpa o valor do campo de texto
                st.session_state.multi_id_search_input_key += 1 # Incrementa a key para forçar a re-renderização do text_area
                st.rerun()

    st.markdown("---")
    
    # --- Campo de Produtos Selecionados ---
    st.markdown("##### Produtos Selecionados")

    if st.session_state.produtos_selecionados_ids_list:
        selected_products_details = []
        # Para cada ID na lista de selecionados, busca os detalhes (do cache ou do DB)
        for prod_id in st.session_state.produtos_selecionados_ids_list:
            found_product = next((p for p in st.session_state.produtos_data if p.get('id_key_erp') == prod_id), None)
            if found_product:
                selected_products_details.append(found_product)
            else:
                # Caso o produto tenha sido excluído do banco mas ainda esteja na lista de selecionados
                # Ou caso seja um ID que foi adicionado e não encontrado na pesquisa múltipla
                not_found_item = {col_info['col_id']: "" for col_info in _COLS_MAP_PRODUTOS.values()}
                not_found_item['id_key_erp'] = prod_id
                not_found_item['nome_part'] = "Não encontrado (removido do DB ou inválido)"
                not_found_item['descricao'] = ""
                not_found_item['ncm'] = ""
                selected_products_details.append(not_found_item)
        
        df_selected_products = pd.DataFrame(selected_products_details)
        if not df_selected_products.empty:
            df_selected_products['ncm'] = df_selected_products['ncm'].apply(_format_ncm)

        selected_list_data = st.dataframe(
            df_selected_products[[col_info['col_id'] for col_info in _COLS_MAP_PRODUTOS.values()]],
            column_config={
                "id_key_erp": st.column_config.TextColumn(_COLS_MAP_PRODUTOS['id']['text'], width="small"),
                "nome_part": st.column_config.TextColumn(_COLS_MAP_PRODUTOS['nome']['text'], width="medium"),
                "descricao": st.column_config.TextColumn(_COLS_MAP_PRODUTOS['desc']['text'], width="large"),
                "ncm": st.column_config.TextColumn(_COLS_MAP_PRODUTOS['ncm']['text'], width="small"),
            },
            hide_index=True,
            use_container_width=True,
            key="selected_products_list_editor",
            selection_mode="multi-row",
            on_select="rerun"
        )

        col_remove_selected, col_clear_selection, col_export_selected_list = st.columns(3) 

        with col_remove_selected:
            if st.button("Remover Itens Selecionados", key="remove_selected_from_list_button"):
                if selected_list_data and selected_list_data['selection']['rows']:
                    indices_to_remove = selected_list_data['selection']['rows']
                    # Cria um conjunto de IDs a serem removidos, para eficiência
                    ids_to_remove_from_list_set = {df_selected_products.iloc[idx]['id_key_erp'] for idx in indices_to_remove}
                    
                    # Reconstroi a lista de selecionados, excluindo os IDs marcados para remoção
                    new_selected_ids_list = [
                        prod_id for prod_id in st.session_state.produtos_selecionados_ids_list 
                        if prod_id not in ids_to_remove_from_list_set
                    ]
                    # NOVO: Se a intenção é remover apenas UMA instância de um ID duplicado,
                    # a lógica abaixo é mais complexa, mas a atual remove todas as ocorrências
                    # se o ID for selecionado para remoção.
                    
                    st.session_state.produtos_selecionados_ids_list = new_selected_ids_list
                    st.session_state.selected_products_list_selection = {'rows': []} # Limpa a seleção visual na tabela de selecionados
                    st.rerun()
                else:
                    st.warning("Nenhum item selecionado para remover da lista.")

        with col_clear_selection:
            if st.button("Limpar Seleção Completa", key="clear_all_selected_products_button_bottom"):
                st.session_state.produtos_selecionados_ids_list = []
                st.session_state.selected_products_list_selection = {'rows': []}
                st.session_state.produtos_table_editor_key_counter += 1 # Força a re-renderização do dataframe principal
                st.rerun()
        
        with col_export_selected_list:
            if st.button("Exportar Selecionados", key="export_selected_products_button_bottom_right"):
                export_selected_products()

    else:
        st.info("Nenhum produto selecionado para exibir.")

    st.markdown("---")
    st.write("Esta tela permite cadastrar, visualizar, editar, excluir e importar produtos. Use a tabela para selecionar um produto para edição ou exclusão individual, ou importe em massa via Excel.")

    # --- Seção para Importar Excel de Produtos (movida para o final) ---
    st.markdown("#### Importar Produtos via Excel")
    uploaded_file = st.file_uploader("Selecione um arquivo Excel para importar produtos", type=["xlsx"], key="upload_products_excel_bottom")
    if uploaded_file is not None:
        import_excel_products(uploaded_file)
