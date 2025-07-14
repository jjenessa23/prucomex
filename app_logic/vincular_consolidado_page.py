import streamlit as st
from app_logic.vincular_utils import vincular_processos_consolidados, listar_grupos_consolidados, desvincular_processos_consolidados
from app_logic import db_utils # Importação adicionada
import pandas as pd # Importação adicionada
import logging # Importar logging para depuração

logger = logging.getLogger(__name__) # Inicializar o logger para este módulo

def show_vincular_consolidado_page(process_id=None):
    st.header("Vincular Processos Consolidados")
    st.info("Selecione os processos que deseja vincular ao processo consolidado.")

    # Exibe o processo principal (se houver um selecionado da tela de Follow-up)
    processo_principal_selecionado = st.session_state.get("process_id_to_vincular", None)
    if processo_principal_selecionado:
        st.subheader(f"Processo Principal: **{processo_principal_selecionado}**")
        st.write("Este será o processo ao qual os outros serão vinculados.")
    else:
        st.warning("Nenhum processo principal selecionado. Por favor, selecione um processo na tela de Follow-up para vincular.")
        if st.button("Voltar para Follow-up"):
            st.session_state.current_page = "Follow-up Importação"
            st.rerun()
        return

    # Iniciar um conjunto para coletar todos os IDs de processos consolidados que são candidatos a serem opções.
    all_candidate_processes_for_options = set()
    
    logger.debug(f"Estado de session_state.followup_processes_data_non_consolidated: {st.session_state.get('followup_processes_data_non_consolidated', 'Não encontrado')}")

    # Adicionar processos não consolidados que são do Modal 'Consolidado'
    if 'followup_processes_data_non_consolidated' in st.session_state and st.session_state.followup_processes_data_non_consolidated:
        for proc in st.session_state['followup_processes_data_non_consolidated']:
            proc_id = proc.get('Processo_Novo') or proc.get('processo_novo') or proc.get('id')
            # MODIFICADO: Filtrar por 'Consolidado' em vez de 'LCL'
            if proc.get('Modal', '').upper() == 'CONSOLIDADO':
                all_candidate_processes_for_options.add(proc_id)
        logger.debug(f"Processos não consolidados do Modal 'Consolidado' adicionados como opções: {all_candidate_processes_for_options}")
    else:
        logger.debug("Nenhum processo não consolidado encontrado ou lista vazia.")
    
    existing_linked_processes = []
    principal_data = None
    if processo_principal_selecionado:
        try:
            principal_data = db_utils.get_firestore_collection_ref("followup_processos").document(processo_principal_selecionado).get().to_dict()
            if principal_data:
                existing_linked_processes = principal_data.get("Processos_Vinculados", [])
                logger.debug(f"Processos já vinculados ao principal '{processo_principal_selecionado}': {existing_linked_processes}")
                # Garante que todos os processos já vinculados (que serão no 'default') também estejam nas opções
                for linked_pid in existing_linked_processes:
                    all_candidate_processes_for_options.add(linked_pid)
            else:
                logger.debug(f"Dados do processo principal '{processo_principal_selecionado}' não encontrados no Firestore.")
        except Exception as e:
            logger.error(f"Erro ao buscar dados do processo principal '{processo_principal_selecionado}': {e}")
            st.error(f"Erro ao carregar dados do processo principal: {e}")


    # Remove o processo principal da lista de opções, pois um processo não pode ser vinculado a si mesmo
    if processo_principal_selecionado in all_candidate_processes_for_options:
        all_candidate_processes_for_options.remove(processo_principal_selecionado)

    # Converte para lista e ordena para exibição consistente
    processos_disponiveis_para_selecao = sorted(list(all_candidate_processes_for_options))
    logger.debug(f"Opções finais para o multiselect: {processos_disponiveis_para_selecao}")

    # Filtra os valores padrão para garantir que existam nas opções disponíveis.
    filtered_default_values = [pid for pid in existing_linked_processes if pid in processos_disponiveis_para_selecao]
    logger.debug(f"Valores padrão filtrados para o multiselect: {filtered_default_values}")

    selecionados = st.multiselect(
        "Processos para vincular (Modal Consolidado):", # MODIFICADO: Atualizado o label do multiselect
        options=processos_disponiveis_para_selecao,
        default=filtered_default_values,
        placeholder="Nenhum processo Consolidado disponível para vincular." if not processos_disponiveis_para_selecao else "Selecione processos...", # MODIFICADO: Atualizado o placeholder
        help="Selecione processos Consolidado a serem vinculados ao processo principal." # MODIFICADO: Atualizado o help text
    )

    if st.button("Vincular/Atualizar"):
        if not processo_principal_selecionado:
            st.error("Por favor, selecione um processo principal antes de vincular.")
        elif vincular_processos_consolidados(processo_principal_selecionado, selecionados):
            st.success(f"Processos {selecionados} vinculados ao processo consolidado '{processo_principal_selecionado}' com sucesso!")
            # Recarrega a página para refletir as mudanças
            st.session_state.current_page = "Follow-up Importação" # Retorna para a tela de Follow-up
            st.rerun()
        else:
            st.error("Erro ao vincular processos. Verifique os logs para mais detalhes.")
            
    if st.button("Voltar"):
        st.session_state.current_page = "Follow-up Importação"
        st.rerun()

    st.markdown("---")
    st.subheader("Grupos de Processos Consolidados Existentes")
    grupos = listar_grupos_consolidados()
    if grupos:
        # Preparar dados para exibição em tabela
        consolidated_table_data = []
        for grupo in grupos:
            principal_display = grupo['principal_id']
            members_ids = grupo['members_ids']
            members_processes_display = [m.get('Processo_Novo', m.get('id', 'N/A')) for m in grupo['members_data']] # Fallback para 'id' se 'Processo_Novo' não existir

            consolidated_table_data.append({
                "Grupo Principal": principal_display,
                "Processos no Grupo": ", ".join(members_processes_display),
                "IDs dos Membros": members_ids
            })
        
        df_consolidated_groups = pd.DataFrame(consolidated_table_data)
        
        edited_df = st.data_editor(
            df_consolidated_groups,
            column_config={
                "IDs dos Membros": st.column_config.ListColumn("IDs dos Membros", help="IDs de todos os processos neste grupo"),
                "Grupo Principal": st.column_config.TextColumn("Grupo Principal", help="ID do processo principal deste grupo"),
                "Processos no Grupo": st.column_config.TextColumn("Processos no Grupo", help="Nomes dos processos que compõem o grupo"),
            },
            num_rows="fixed",
            hide_index=True,
            use_container_width=True,
            key="consolidated_groups_editor"
        )
        
        options_for_unlinking = [g['Grupo Principal'] for g in consolidated_table_data]
        selected_groups_for_unlinking = st.multiselect(
            "Selecione Grupos Consolidados para Desvincular Completamente:",
            options=options_for_unlinking,
            key="select_groups_to_unlink"
        )

        if st.button("Desvincular Grupos Selecionados"):
            if selected_groups_for_unlinking:
                process_ids_to_unlink = []
                for group_name_to_unlink in selected_groups_for_unlinking:
                    for group_info in consolidated_table_data:
                        if group_info["Grupo Principal"] == group_name_to_unlink:
                            process_ids_to_unlink.extend(group_info["IDs des Membros"]) # Corrigido aqui
                            break
                
                if process_ids_to_unlink:
                    process_ids_to_unlink = list(set(process_ids_to_unlink))
                    if desvincular_processos_consolidados(process_ids_to_unlink):
                        st.success(f"Grupos consolidados com os processos {process_ids_to_unlink} desvinculados com sucesso!")
                        st.session_state.current_page = "Follow-up Importação"
                        st.rerun()
                    else:
                        st.error("Erro ao desvincular grupos. Verifique os logs.")
                else:
                    st.warning("Nenhum processo encontrado nos grupos selecionados para desvincular.")
            else:
                st.warning("Por favor, selecione pelo menos um grupo para desvincular.")

    else:
        st.info("Nenhum grupo consolidado encontrado.")
