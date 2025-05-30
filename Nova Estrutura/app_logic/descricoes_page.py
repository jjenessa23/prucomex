import streamlit as st
import pandas as pd
import io # Para manipulação de arquivos em memória
import openpyxl # Para gerar e ler arquivos Excel
import logging

# Importar funções do novo módulo de utilitários de banco de dados
from db_utils import (
    get_db_path,
    connect_db, # Pode ser útil para depuração, mas não é usado diretamente nas funções de CRUD de produto aqui
    inserir_ou_atualizar_produto,
    selecionar_todos_produtos,
    selecionar_produto_por_id,
    selecionar_produtos_por_ids,
    deletar_produto
)

logger = logging.getLogger(__name__)

# Mapeamento de colunas (precisa ser consistente com seu main.py original)
# Em um projeto Streamlit, você pode definir isso diretamente onde usa,
# ou em um arquivo de constantes se muitos módulos precisarem.
# Para este exemplo, vou duplicar, mas o ideal seria ter um `config.py` central.
_COLS_MAP_PRODUTOS = {
    "id": {"text": "ID/Key ERP", "width": 120, "col_id": "id_key_erp"},
    "nome": {"text": "Nome/Part", "width": 200, "col_id": "nome_part"},
    "desc": {"text": "Descrição", "width": 350, "col_id": "descricao"},
    "ncm": {"text": "NCM", "width": 100, "col_id": "ncm"}
}

# --- Funções Auxiliares de Formatação ---
def _format_ncm(ncm_value):
    """Formata o NCM para o padrão xxxx.xx.xx."""
    if ncm_value and isinstance(ncm_value, str) and len(ncm_value) == 8:
        return f"{ncm_value[0:4]}.{ncm_value[4:6]}.{ncm_value[6:8]}"
    return ncm_value

def show_page():
    st.subheader("Gerenciamento de Produtos / Descrições")

    # --- Estado da Sessão para esta página ---
    if 'produtos_data' not in st.session_state:
        st.session_state.produtos_data = []
    if 'selected_produto_id' not in st.session_state:
        st.session_state.selected_produto_id = None
    if 'produtos_selecionados_ids_list' not in st.session_state: # Para a lista de seleção múltipla
        st.session_state.produtos_selecionados_ids_list = []
    if 'descricoes_search_terms' not in st.session_state: # Para campos de pesquisa
        st.session_state.descricoes_search_terms = {col_info['col_id']: "" for col_info in _COLS_MAP_PRODUTOS.values()}

    # --- Funções para interagir com o DB (adaptadas para Streamlit) ---
    def load_produtos():
        """Carrega todos os produtos do DB e atualiza o estado da sessão."""
        db_path = get_db_path("produtos") # Assume que 'produtos' é um tipo de DB no db_utils
        if not db_path:
            st.error("Caminho do banco de dados de produtos não configurado.")
            return

        # Verifica se o DB está acessível antes de tentar carregar
        conn = connect_db(db_path)
        if not conn:
            st.warning("Não foi possível conectar ao banco de dados de produtos. Tente novamente mais tarde.")
            st.session_state.produtos_data = []
            st.session_state.produtos_data_df = pd.DataFrame() # Define um DataFrame vazio para evitar erros
            return

        produtos = selecionar_todos_produtos(db_path)
        conn.close() # Fechar a conexão após a operação

        # Converte para lista de dicionários para facilitar o uso no Streamlit
        st.session_state.produtos_data = [
            {col_info['col_id']: p[i] for i, col_info in enumerate(_COLS_MAP_PRODUTOS.values())}
            for p in produtos
        ]
        st.session_state.produtos_data_df = pd.DataFrame(st.session_state.produtos_data)
        # Formatar NCM para exibição
        if not st.session_state.produtos_data_df.empty:
            st.session_state.produtos_data_df['ncm'] = st.session_state.produtos_data_df['ncm'].apply(_format_ncm)

        logger.info(f"Carregados {len(produtos)} produtos do DB.")
        # st.rerun() # Não chamar rerun aqui para evitar loop infinito com on_change

    def add_or_update_produto(produto_id, nome, desc, ncm):
        """Adiciona ou atualiza um produto no DB."""
        db_path = get_db_path("produtos") # Assume que 'produtos' é um tipo de DB no db_utils
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
        if inserir_ou_atualizar_produto(db_path, produto_tuple):
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
        db_path = get_db_path("produtos") # Assume que 'produtos' é um tipo de DB no db_utils
        if not db_path:
            st.error("Caminho do banco de dados de produtos não configurado.")
            return False
        
        if deletar_produto(db_path, produto_id):
            st.success(f"Produto ID '{produto_id}' excluído com sucesso!")
            # Remove da lista de seleção se estiver lá
            if produto_id in st.session_state.produtos_selecionados_ids_list:
                st.session_state.produtos_selecionados_ids_list.remove(produto_id)
            st.session_state.selected_produto_id = None # Limpa a seleção
            load_produtos() # Recarrega a tabela
            return True
        else:
            st.error(f"Falha ao excluir o produto ID '{produto_id}'. Verifique os logs.")
            return False

    def export_selected_products():
        """Exporta produtos selecionados para Excel/TXT."""
        db_path = get_db_path("produtos") # Assume que 'produtos' é um tipo de DB no db_utils
        if not db_path:
            st.error("Caminho do banco de dados de produtos não configurado.")
            return

        if not st.session_state.produtos_selecionados_ids_list:
            st.warning("Nenhum produto selecionado para exportar.")
            return

        # Busca detalhes completos para IDs selecionados
        selected_ids = list(st.session_state.produtos_selecionados_ids_list)
        produtos_detalhes = selecionar_produtos_por_ids(db_path, selected_ids)

        if not produtos_detalhes:
            st.error("Não foi possível obter os dados dos produtos selecionados para exportar.")
            return

        # Cria DataFrame para exportação
        col_db = [info['col_id'] for info in _COLS_MAP_PRODUTOS.values()]
        col_hdr = [info['text'] for info in _COLS_MAP_PRODUTOS.values()]
        df_export = pd.DataFrame(produtos_detalhes, columns=col_db)
        df_export.rename(columns=dict(zip(col_db, col_hdr)), inplace=True)

        excel_buffer = io.BytesIO()
        df_export.to_excel(excel_buffer, index=False, engine='openpyxl')
        excel_buffer.seek(0)

        st.download_button(
            label="Baixar Excel de Selecionados",
            data=excel_buffer,
            file_name="produtos_selecionados.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="download_selected_excel_button"
        )
        st.success(f"Exportado {len(produtos_detalhes)} produtos selecionados.")


    def import_excel_products(uploaded_file):
        """Importa produtos de arquivo Excel."""
        db_path = get_db_path("produtos") # Assume que 'produtos' é um tipo de DB no db_utils
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

        cols_req = [info['col_id'] for info in _COLS_MAP_PRODUTOS.values()]
        # Adiciona verificação para os nomes amigáveis das colunas também
        col_text_names = [info['text'] for info in _COLS_MAP_PRODUTOS.values()]
        
        # Cria um mapeamento flexível de colunas do Excel para as colunas do DB
        excel_to_db_col_map = {}
        for db_col_info in _COLS_MAP_PRODUTOS.values():
            db_col_id = db_col_info['col_id']
            db_col_text = db_col_info['text']
            
            if db_col_id in df.columns:
                excel_to_db_col_map[db_col_id] = db_col_id # Prioriza o col_id exato
            elif db_col_text in df.columns:
                excel_to_db_col_map[db_col_id] = db_col_text # Usa o nome amigável se o col_id não for encontrado
            elif db_col_text.replace(' ', '') in df.columns: # Tenta sem espaços também
                 excel_to_db_col_map[db_col_id] = db_col_text.replace(' ', '')
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
                    logger.warning(f"Linha {index+2}: ID de produto '{id_p}' contém espaços, ignorado.")
                    error_count += 1
                    continue
                
                if inserir_ou_atualizar_produto(db_path, produto_tuple):
                    imported_count += 1
                else:
                    error_count += 1 # inserir_ou_atualizar_produto already logs/shows error
            except KeyError as e:
                logger.warning(f"Linha {index+2} ignorada: Coluna '{e}' não encontrada ou problema no mapeamento. Erro: {e}")
                error_count += 1
            except Exception as e:
                logger.exception(f"Erro ao processar linha {index+2} do Excel para produtos: {e}")
                error_count += 1

        st.success(f"{imported_count} produtos importados/atualizados.")
        if error_count > 0:
            st.warning(f"{error_count} linhas com erro/ignoradas. Verifique os logs.")
        
        load_produtos() # Recarrega a tabela

    # --- UI Layout ---

    # Botões de Ação Principal
    with st.expander("Ações Principais"):
        col_add, col_import, col_export_button_placeholder = st.columns(3) # Placeholder para o download button
        with col_add:
            # Botão "Adicionar Novo" abre formulário de adição/edição
            if st.button("Adicionar Novo Produto"):
                st.session_state.selected_produto_id = None # Limpa a seleção para um novo
                st.session_state.open_form_button_clicked = True # Abre o formulário
                st.rerun() # Força rerun para exibir o formulário
        with col_import:
            uploaded_file = st.file_uploader("Importar Excel de Produtos", type=["xlsx"], key="upload_products_excel")
            if uploaded_file is not None:
                import_excel_products(uploaded_file)
        with col_export_button_placeholder:
             st.button("Exportar Selecionados", on_click=export_selected_products) # Este botão acionará o download_button
             if st.session_state.get('download_selected_excel_button'): # Para limpar o uploader após o download
                 pass # Ação já tratada pelo export_selected_products


    # --- Formulário de Adição/Edição ---
    # Mostra o formulário se 'selected_produto_id' for None (novo) ou tiver um ID (edição)
    # A atualização da UI acontece após o save/delete que recarrega a página.
    if st.session_state.selected_produto_id is not None or st.session_state.get('open_form_button_clicked', False):
        with st.form(key="produto_form"):
            st.markdown("##### Adicionar/Editar Produto")
            
            initial_data = {}
            is_editing = False
            if st.session_state.selected_produto_id:
                produto_data = selecionar_produto_por_id(get_db_path("produtos"), st.session_state.selected_produto_id)
                if produto_data:
                    # Converte Row para dicionário para acesso por chave
                    initial_data = {col_info['col_id']: produto_data[i] for i, col_info in enumerate(_COLS_MAP_PRODUTOS.values())}
                    is_editing = True
                    st.write(f"Editando Produto: **{initial_data.get('nome_part', '')}** (ID: **{initial_data.get('id_key_erp', '')}**)")
                else:
                    st.warning("Produto selecionado não encontrado. Adicionando um novo.")
                    st.session_state.selected_produto_id = None # Reseta para adicionar novo
                    st.session_state.open_form_button_clicked = True # Mantém o formulário aberto para novo produto
            else:
                st.write("Adicionar Novo Produto")
                st.session_state.open_form_button_clicked = True # Garante que o formulário permaneça aberto após click

            # Campos de entrada
            produto_id_input = st.text_input(
                _COLS_MAP_PRODUTOS['id']['text'],
                value=initial_data.get('id_key_erp', ''),
                disabled=is_editing, # Desabilita o ID se estiver editando
                key="produto_id_form_input" # Renomeada a chave para evitar conflito
            )
            nome_input = st.text_input(_COLS_MAP_PRODUTOS['nome']['text'], value=initial_data.get('nome_part', ''), key="nome_form_input") # Renomeada a chave
            desc_input = st.text_area(_COLS_MAP_PRODUTOS['desc']['text'], value=initial_data.get('descricao', ''), key="desc_form_input") # Renomeada a chave
            ncm_input = st.text_input(_COLS_MAP_PRODUTOS['ncm']['text'], value=_format_ncm(initial_data.get('ncm', '')), key="ncm_form_input") # Renomeada a chave

            col_submit_delete, col_cancel = st.columns(2)
            with col_submit_delete:
                if col_submit_delete.form_submit_button("Salvar Produto"):
                    if add_or_update_produto(produto_id_input, nome_input, desc_input, ncm_input):
                        st.session_state.selected_produto_id = None # Limpa para fechar o formulário
                        st.session_state.open_form_button_clicked = False # Fecha o formulário
                        st.rerun() # Força a re-execução para atualizar a UI
                if is_editing:
                    if col_submit_delete.form_submit_button("Excluir Produto"):
                        if delete_produto_from_db(produto_id_input):
                            st.session_state.selected_produto_id = None # Limpa para fechar o formulário
                            st.session_state.open_form_button_clicked = False # Fecha o formulário
                            st.rerun()
            with col_cancel:
                if col_cancel.form_submit_button("Cancelar"):
                    st.session_state.selected_produto_id = None # Fecha o formulário
                    st.session_state.open_form_button_clicked = False # Fecha o formulário
                    st.rerun() # Força a re-execução para atualizar a UI

    # --- Tabela de Produtos ---
    st.markdown("##### Produtos Cadastrados")

    # Garante que os dados sejam carregados na primeira execução ou se o estado mudar
    if not st.session_state.produtos_data:
        load_produtos()

    df_display = st.session_state.produtos_data_df

    if not df_display.empty:
        # Colunas a serem exibidas e configuradas
        columns_config = {
            "id_key_erp": st.column_config.TextColumn(_COLS_MAP_PRODUTOS['id']['text'], width="small"),
            "nome_part": st.column_config.TextColumn(_COLS_MAP_PRODUTOS['nome']['text'], width="medium"),
            "descricao": st.column_config.TextColumn(_COLS_MAP_PRODUTOS['desc']['text'], width="large"),
            "ncm": st.column_config.TextColumn(_COLS_MAP_PRODUTOS['ncm']['text'], width="small"),
        }

        # Acessa a seleção diretamente do st.session_state
        st.dataframe(
            df_display,
            column_config=columns_config,
            hide_index=True,
            use_container_width=True,
            key="produtos_table_editor",
            selection_mode="single-row", # Permite seleção única para edição
            on_select="rerun" # Adiciona on_select para forçar rerun e atualizar botões
        )
        
        # Lógica para editar/deletar produto selecionado via botão
        # Acessa a seleção diretamente do st.session_state
        selected_rows_from_state = st.session_state.get("produtos_table_editor", {}).get("selection", {})
        
        if selected_rows_from_state and selected_rows_from_state.get('rows'):
            selected_index = selected_rows_from_state['rows'][0]
            # Obtém o ID e nome do produto diretamente do DataFrame de exibição (que tem os IDs corretos)
            selected_produto_id = df_display.iloc[selected_index]['id_key_erp']
            selected_produto_name = df_display.iloc[selected_index]['nome_part']
            
            st.session_state.selected_produto_id = selected_produto_id # Atualiza o selected_produto_id no session state

            col_edit_selected, col_delete_selected = st.columns(2)
            with col_edit_selected:
                if st.button(f"Editar Selecionado: {selected_produto_name}", key="edit_selected_from_table"):
                    # O formulário de edição será reexibido com os dados do selected_produto_id
                    st.session_state.open_form_button_clicked = True # Força o formulário a abrir
                    st.rerun()
            with col_delete_selected:
                if st.button(f"Excluir Selecionado: {selected_produto_name}", key="delete_selected_from_table"):
                    # Confirmação antes de excluir
                    st.warning(f"Deseja realmente excluir o produto '{selected_produto_name}' (ID: {selected_produto_id})?")
                    if st.button("Sim, Excluir Confirmado", key=f"confirm_delete_button_{selected_produto_id}"):
                        if delete_produto_from_db(selected_produto_id):
                            st.session_state.selected_produto_id = None
                            st.session_state.open_form_button_clicked = False # Fecha o formulário
                            st.rerun()
                    else:
                        st.info("Exclusão cancelada.") # Mensagem de cancelamento
                        st.session_state.selected_produto_id = None # Limpa a seleção para evitar auto-edição/exclusão
                        st.rerun()


    else:
        st.info("Nenhum produto cadastrado. Adicione um novo ou importe via Excel.")

    st.markdown("---")
    st.write("Esta tela permite cadastrar, visualizar, editar, excluir e importar produtos. Use a tabela para selecionar um produto para edição ou exclusão individual, ou importe em massa via Excel.")

# --- Callbacks e Lógica de Seleção para st.dataframe (simplificado para single-row selection) ---
# Se a seleção for "single-row", o st.session_state.produtos_table_editor['selection']
# já conterá o índice da linha selecionada. Não precisamos de uma lógica separada para multi-seleção aqui.
# A lista st.session_state.produtos_selecionados_ids_list será mantida apenas se for necessário um multi-select para exportação
# como no `view_descricoes.py` original. Mantive o `produtos_selecionados_ids_list` no `st.session_state`
# e o botão "Exportar Selecionados" acima, que usa essa lista.
