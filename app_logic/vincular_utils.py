from typing import List, Dict, Any, Tuple
import streamlit as st
from app_logic import db_utils
import logging
from google.cloud.firestore_v1.base_query import FieldFilter # Importar FieldFilter

logger = logging.getLogger(__name__)

def vincular_processos_consolidados(processo_principal_id: str, processos_a_vincular_agora: List[str]):
    '''
    Atualiza o processo principal e os processos vinculados no Firestore.
    Todos os processos no grupo consolidado (principal + os explicitamente vinculados)
    terão 'Consolidado' = 'Sim' e 'Processos_Vinculados' contendo todos os *outros* IDs do grupo.
    '''
    processos_ref = db_utils.get_firestore_collection_ref("followup_processos")
    if not processos_ref:
        st.error("Não foi possível acessar a coleção de processos.")
        return False

    try:
        # Obter dados do processo principal para saber seus vinculados atuais (se houver)
        principal_doc = processos_ref.document(processo_principal_id).get()
        if not principal_doc.exists:
            st.error(f"Erro: Processo principal '{processo_principal_id}' não encontrado.")
            return False
        principal_data = principal_doc.to_dict()
        
        # O conjunto de TODOS os processos que farão parte do grupo consolidado.
        # Inclui o principal, seus vinculados já existentes (se houver) e os novos a serem vinculados.
        all_processes_in_new_group_set = {processo_principal_id}
        all_processes_in_new_group_set.update(principal_data.get("Processos_Vinculados", []))
        all_processes_in_new_group_set.update(processos_a_vincular_agora)

        # Remove quaisquer processos "Nenhum" ou vazios da lista (apenas para limpeza)
        all_processes_in_new_group_set = {pid for pid in all_processes_in_new_group_set if pid and str(pid).strip() != 'Nenhum'}

        all_processes_in_new_group_list = list(all_processes_in_new_group_set)
        
        # Validar se os processos a vincular realmente existem no DB
        existing_pids = []
        for pid in all_processes_in_new_group_list:
            if processos_ref.document(pid).get().exists:
                existing_pids.append(pid)
            else:
                logger.warning(f"Processo '{pid}' não encontrado no DB durante a consolidação. Ignorado.")
        
        if not existing_pids:
            st.warning("Nenhum processo válido para vincular/consolidar encontrado.")
            return False

        all_processes_in_new_group_list = existing_pids # Usa apenas os IDs que existem
        
        batch = db_utils.db_firestore.batch()

        # Para cada processo no grupo, atualize seu 'Consolidado' para 'Sim'
        # e 'Processos_Vinculados' para incluir todos os OUTROS membros do grupo.
        for process_id_in_group in all_processes_in_new_group_list:
            # Lista de processos a serem vinculados para o processo atual (excluindo ele mesmo)
            linked_list_for_current_process = sorted([
                p_id for p_id in all_processes_in_new_group_list if p_id != process_id_in_group
            ])
            
            # Prepara a atualização para cada documento
            update_data = {
                "Consolidado": "Sim",
                "Processos_Vinculados": linked_list_for_current_process
            }
            batch.update(processos_ref.document(process_id_in_group), update_data)
        
        batch.commit()
        logger.info(f"Processos {all_processes_in_new_group_list} consolidados com sucesso.")
        return True
    except Exception as e:
        logger.exception(f"Erro ao vincular processos: {e}")
        st.error(f"Erro ao vincular processos: {e}")
        return False

def desvincular_processos_consolidados(process_ids_to_unlink: List[str]) -> bool:
    '''
    Desvincula um ou mais processos, definindo 'Consolidado' para 'Não' e limpando
    'Processos_Vinculados'. Isso pode afetar outros processos no mesmo grupo.
    '''
    processos_ref = db_utils.get_firestore_collection_ref("followup_processos")
    if not processos_ref:
        st.error("Não foi possível acessar a coleção de processos.")
        return False

    try:
        batch = db_utils.db_firestore.batch()
        
        # Primeiro, obter todos os processos que serão afetados e seus grupos atuais
        affected_processes_data = {}
        for pid in process_ids_to_unlink:
            doc = processos_ref.document(pid).get()
            if doc.exists:
                affected_processes_data[pid] = doc.to_dict()
            else:
                logger.warning(f"Processo '{pid}' não encontrado para desvinculação. Ignorado.")

        # Para cada processo a ser desvinculado
        for pid_to_unlink in process_ids_to_unlink:
            if pid_to_unlink not in affected_processes_data:
                continue

            # Desvincular o processo diretamente
            update_data_unlink = {
                "Consolidado": "Não", # Define como "Não" ao desvincular
                "Processos_Vinculados": [] # Limpa a lista de vinculados
            }
            batch.update(processos_ref.document(pid_to_unlink), update_data_unlink)
            logger.info(f"Processo '{pid_to_unlink}' marcado para desvinculação e limpeza de vinculados.")

            # Se este processo estava em um grupo, precisamos atualizar os outros membros desse grupo.
            # Percorre os outros processos que estavam vinculados a este processo que está sendo desvinculado.
            original_linked_ids = affected_processes_data[pid_to_unlink].get("Processos_Vinculados", [])
            for other_pid_in_group in original_linked_ids:
                if other_pid_in_group not in process_ids_to_unlink: # Se o outro processo não está sendo desvinculado AGORA
                    other_doc_ref = processos_ref.document(other_pid_in_group)
                    other_doc = other_doc_ref.get()
                    if other_doc.exists:
                        current_linked = other_doc.to_dict().get("Processos_Vinculados", [])
                        
                        # Remove o processo que está sendo desvinculado da lista dos outros.
                        updated_linked = [p_id for p_id in current_linked if p_id != pid_to_unlink]
                        
                        update_other_data = {
                            "Processos_Vinculados": updated_linked
                        }
                        # Se não há mais processos vinculados, ele também deve ser marcado como Não Consolidado
                        if not updated_linked:
                            update_other_data["Consolidado"] = "Não"
                            logger.info(f"Processo '{other_pid_in_group}' também marcado como Não Consolidado.")
                        
                        batch.update(other_doc_ref, update_other_data)
                        logger.info(f"Processo '{other_pid_in_group}' atualizado para remover vinculação com '{pid_to_unlink}'.")

        batch.commit()
        logger.info(f"Desvinculação de processos {process_ids_to_unlink} concluída com sucesso.")
        return True
    except Exception as e:
        logger.exception(f"Erro ao desvincular processos: {e}")
        st.error(f"Erro ao desvincular processos: {e}")
        return False


def listar_grupos_consolidados() -> List[Dict[str, Any]]:
    '''
    Retorna uma lista de grupos de processos consolidados únicos.
    Cada grupo é identificado por uma representação canônica dos seus membros.
    '''
    processos_ref = db_utils.get_firestore_collection_ref("followup_processos")
    if not processos_ref:
        return []
    
    unique_groups = {} # Use um dicionário para armazenar grupos únicos {canonical_key: group_info}

    try:
        # Busca todos os processos que estão marcados como Consolidado='Sim'
        # Adiciona também a condição para não buscar os que estão 'Status_Arquivado' == 'Arquivado'
        # ou se 'Status_Arquivado' campo não existe / é None / é 'Não Arquivado'
        # (Para garantir que apenas grupos ativos sejam listados para desvinculação na UI)
        query = processos_ref.where(filter=FieldFilter("Consolidado", "==", "Sim")) \
                             .where(filter=FieldFilter("Status_Arquivado", "in", [None, "Não Arquivado"]))
        
        for doc in query.stream():
            data = doc.to_dict()
            process_id = doc.id
            linked_processes = data.get("Processos_Vinculados", [])
            
            # Constrói o conjunto completo de membros deste grupo (incluindo ele mesmo)
            current_group_members_set = {process_id}
            current_group_members_set.update(linked_processes)
            
            # Cria uma representação canônica do grupo (um tuple ordenado de IDs)
            canonical_group_key = tuple(sorted(list(current_group_members_set)))
            
            # Se este grupo ainda não foi processado, adiciona-o à lista de grupos únicos
            if canonical_group_key not in unique_groups:
                # O "principal" para o display pode ser o primeiro ID no tuple canônico
                principal_display_id = canonical_group_key[0] if canonical_group_key else None
                
                # Fetch detailed data for all members for richer display later
                members_data = []
                for member_id in canonical_group_key:
                    member_doc = processos_ref.document(member_id).get()
                    if member_doc.exists:
                        member_info = member_doc.to_dict()
                        member_info['id'] = member_doc.id # Add Firestore doc ID
                        members_data.append(member_info)
                
                # Sort members_data by Processo_Novo for consistent display
                members_data = sorted(members_data, key=lambda x: x.get('Processo_Novo', ''))

                unique_groups[canonical_group_key] = {
                    "canonical_key": canonical_group_key,
                    "principal_id": principal_display_id, # Optional: representative for display
                    "members_ids": list(canonical_group_key),
                    "members_data": members_data # Detailed data for rendering
                }
        
        # Retorna os grupos únicos como uma lista de dicionários
        return list(unique_groups.values())
    except Exception as e:
        logger.exception(f"Erro ao listar grupos consolidados: {e}")
        return []

def get_non_consolidated_modal_consolidado_processes() -> List[Dict[str, Any]]:
    '''
    Busca no Firestore todos os processos que NÃO estão consolidados (Consolidado != 'Sim')
    e que possuem o campo 'Modal' como 'Consolidado'.
    '''
    processos_ref = db_utils.get_firestore_collection_ref("followup_processos")
    if not processos_ref:
        logger.error("Não foi possível acessar a coleção de processos para buscar não consolidados.")
        return []

    non_consolidated_processes = []
    try:
        logger.debug("Iniciando busca por processos não consolidados do Modal 'Consolidado'...")
        # Busca todos os documentos da coleção
        docs = processos_ref.stream()
        
        found_docs_count = 0
        for doc in docs:
            found_docs_count += 1
            data = doc.to_dict()
            data['id'] = doc.id # Adiciona o ID do documento aos dados
            
            # Log dos dados de cada documento para depuração
            logger.debug(f"Processando documento: ID={data.get('id')}, Modal={data.get('Modal')}, Consolidado={data.get('Consolidado')}, Status_Arquivado={data.get('Status_Arquivado')}")

            # Filtra os processos:
            # 1. Não estão marcados como "Consolidado": "Sim" (ou o campo não existe/é diferente)
            # 2. Têm o campo "Modal" como "Consolidado" (case-insensitive)
            # 3. Não estão arquivados (Status_Arquivado não é 'Arquivado' ou não existe)
            
            # Correção para o AttributeError: 'NoneType' object has no attribute 'upper'
            modal_value = data.get('Modal')
            is_modal_consolidado = (modal_value or '').upper() == 'CONSOLIDADO'
            
            is_not_consolidated = data.get('Consolidado') != 'Sim'
            is_not_archived = data.get('Status_Arquivado') != 'Arquivado' and data.get('Status_Arquivado') is not None # Explicitamente verifica None também

            if is_modal_consolidado and is_not_consolidated and is_not_archived:
                non_consolidated_processes.append(data)
                logger.debug(f"Adicionado: ID={data.get('id')}")
            else:
                logger.debug(f"Filtrado: ID={data.get('id')}. Condições: Modal Consolidado={is_modal_consolidado}, Não Consolidado={is_not_consolidated}, Não Arquivado={is_not_archived}")
        
        logger.debug(f"Total de documentos processados: {found_docs_count}")
        logger.debug(f"Processos não consolidados do Modal 'Consolidado' encontrados (final): {[p.get('Processo_Novo') or p.get('id') for p in non_consolidated_processes]}")
        return non_consolidated_processes
    except Exception as e:
        logger.exception(f"Erro ao buscar processos não consolidados do Modal 'Consolidado': {e}")
        return []

