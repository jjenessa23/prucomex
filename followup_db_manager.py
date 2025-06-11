# -*- coding: utf-8 -*-
import sqlite3
import streamlit as st
import pandas as pd
import os
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List, Tuple
import json # Importar json para lidar com target_users

# Importar db_utils para obter a lista de usuários
# Assumindo que db_utils está no mesmo nível que followup_db_manager
import db_utils


# Configuração de logging para o módulo de banco de dados
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO) # Define o nível de logging para INFO

# Variável global para armazenar o caminho do banco de dados de follow-up
followup_db_path: Optional[str] = None

# Lista fixa de opções de status (mantida aqui, mas usada na UI para consistência)
STATUS_OPTIONS = ["", "Processo Criado","Verificando","Em produção","Pré Embarque","Embarcado","Chegada Recinto","Registrado","Liberado","Agendado","Chegada Pichau","Encerrado"]

# --- Lógica de inicialização do caminho do DB ao carregar o módulo ---
# Isso garante que o caminho padrão seja definido e o diretório 'data' criado
# assim que o followup_db_manager for importado.
_base_path = os.path.dirname(os.path.abspath(__file__))
# Determina o caminho raiz da aplicação. Se o módulo estiver em 'app_logic', sobe um nível.
_app_root_path = os.path.dirname(_base_path) if os.path.basename(_base_path) == 'app_logic' else _base_path
_DEFAULT_DB_FOLDER = "data"
_FOLLOWUP_DB_FILENAME = "followup_importacao.db"
_default_followup_db_full_path = os.path.join(_app_root_path, _DEFAULT_DB_FOLDER, _FOLLOWUP_DB_FILENAME)

# Garante que o diretório 'data' exista antes de tentar criar o DB
_data_dir = os.path.join(_app_root_path, _DEFAULT_DB_FOLDER)
if not os.path.exists(_data_dir):
    os.makedirs(_data_dir)
    logger.info(f"Diretório de dados '{_data_dir}' criado para Follow-up DB.")

# Define o caminho padrão do DB ao carregar o módulo
followup_db_path = _default_followup_db_full_path
logger.info(f"[followup_db_manager] Caminho padrão do DB definido na inicialização do módulo: {followup_db_path}")

# --- Fim da lógica de inicialização do DB ---


def set_followup_db_path(path: str):
    """Define o caminho do banco de dados de follow-up."""
    global followup_db_path
    followup_db_path = path
    logger.info(f"[followup_db_manager] Caminho do DB definido para: {followup_db_path}")


def get_followup_db_path() -> Optional[str]:
    """Retorna o caminho atual do banco de dados de follow-up."""
    return followup_db_path


def conectar_followup_db():
    """
    Estabelece uma conexão com o banco de dados SQLite de follow-up.
    Retorna o objeto de conexão ou None em caso de erro.
    """
    global followup_db_path
    logger.debug(f"[conectar_followup_db] Tentando conectar a: {followup_db_path}")
    
    # Verifica se o caminho do DB está definido. Se não, algo deu errado na inicialização.
    if not followup_db_path:
        logger.error("Caminho do DB de Follow-up não definido. Não é possível conectar.")
        return None
    try:
        conn = sqlite3.connect(followup_db_path)
        conn.row_factory = sqlite3.Row # Retorna linhas como dicionários-like para fácil acesso
        conn.execute("PRAGMA foreign_keys = ON;") # Garante a integridade referencial
        logger.debug(f"[conectar_followup_db] Conectado com sucesso a: {followup_db_path}")
        return conn
    except Exception as e:
        logger.exception(f"Erro ao conectar ao DB de Follow-up em {followup_db_path}")
        return None

def adicionar_coluna_se_nao_existe(conn, column_name, column_type, default_value=None):
    """Adiciona uma coluna à tabela 'processos' se ela não existir."""
    try:
        cursor = conn.cursor()
        cursor.execute(f"PRAGMA table_info(processos)")
        columns = [info[1] for info in cursor.fetchall()]
        if column_name not in columns:
            if default_value is not None:
                cursor.execute(f'ALTER TABLE processos ADD COLUMN "{column_name}" {column_type} DEFAULT "{default_value}"')
            else:
                cursor.execute(f'ALTER TABLE processos ADD COLUMN "{column_name}" {column_type}')
            conn.commit()
            logger.info(f'Coluna "{column_name}" ({column_type}) adicionada à tabela "processos".')
        else:
            logger.debug(f'Coluna "{column_name}" já existe na tabela "processos".')
    except Exception as e:
        logger.error(f"Erro ao adicionar coluna '{column_name}': {e}")


def criar_tabela_followup(conn):
    """
    Cria as tabelas 'processos', 'historico_processos', 'process_items' e 'notifications' se não existirem,
    e adiciona novas colunas se necessário.
    """
    try:
        cursor = conn.cursor()
        # Tabela principal 'processos'
        cursor.execute('''CREATE TABLE IF NOT EXISTS processos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            Processo_Novo TEXT UNIQUE,
            Observacao TEXT,
            Tipos_de_item TEXT,
            Data_Embarque TEXT,
            Previsao_Pichau TEXT,
            Documentos_Revisados TEXT,
            Conhecimento_Embarque TEXT,
            Descricao_Feita TEXT,
            Descricao_Enviada TEXT,
            Fornecedor TEXT,
            N_Invoice TEXT,
            Quantidade INTEGER,
            Valor_USD REAL,
            Pago TEXT,
            N_Ordem_Compra TEXT,
            Data_Compra TEXT,
            Estimativa_Impostos_BR REAL,
            Estimativa_Frete_USD REAL,
            Agente_de_Carga_Novo TEXT,
            Status_Geral TEXT,
            Modal TEXT,
            Navio TEXT,
            Origem TEXT,
            Destino TEXT,
            INCOTERM TEXT,
            Comprador TEXT,
            Status_Arquivado TEXT DEFAULT 'Não Arquivado',
            Caminho_da_pasta TEXT,
            Estimativa_Dolar_BRL REAL,
            Estimativa_Seguro_BRL REAL,
            Estimativa_II_BR REAL,
            Estimativa_IPI_BR REAL,
            Estimativa_PIS_BR REAL,
            Estimativa_COFINS_BR REAL,
            Estimativa_ICMS_BR REAL,
            Nota_feita TEXT,
            Conferido TEXT,
            Ultima_Alteracao_Por TEXT,
            Ultima_Alteracao_Em TEXT,
            Estimativa_Impostos_Total REAL -- Nova coluna para o total de impostos
        )''')
        conn.commit()
        logger.info("Tabela 'processos' verificada/criada com sucesso com novas colunas.")

        # Tabela 'historico_processos' para rastrear alterações
        cursor.execute('''CREATE TABLE IF NOT EXISTS historico_processos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            processo_id INTEGER,
            campo_alterado TEXT,
            valor_antigo TEXT,
            valor_novo TEXT,
            timestamp TEXT,
            usuario TEXT,
            FOREIGN KEY(processo_id) REFERENCES processos(id) ON DELETE CASCADE
        )''')
        conn.commit()
        logger.info("Tabela 'historico_processos' verificada/criada com sucesso.")

        # --- NOVA TABELA: process_items para armazenar os itens de cada processo ---
        cursor.execute('''CREATE TABLE IF NOT EXISTS process_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            processo_id INTEGER NOT NULL,
            codigo_interno TEXT,
            ncm TEXT,
            cobertura TEXT,
            sku TEXT,
            quantidade REAL,
            peso_unitario REAL,
            valor_unitario REAL,
            valor_total_item REAL,
            estimativa_ii_br REAL,
            estimativa_ipi_br REAL,
            estimativa_pis_br REAL,
            estimativa_cofins_br REAL,
            estimativa_icms_br REAL,
            frete_rateado_usd REAL,
            seguro_rateado_brl REAL,
            vlmd_item REAL,
            denominacao_produto TEXT,
            detalhamento_complementar_produto TEXT,
            FOREIGN KEY(processo_id) REFERENCES processos(id) ON DELETE CASCADE
        )''')
        conn.commit()
        logger.info("Tabela 'process_items' verificada/criada com sucesso.")

        # Lógica para adicionar novas colunas a 'processos' se a tabela já existia sem elas
        adicionar_coluna_se_nao_existe(conn, 'ETA_Recinto', 'TEXT')
        adicionar_coluna_se_nao_existe(conn, 'Data_Registro', 'TEXT')
        adicionar_coluna_se_nao_existe(conn, 'DI_ID_Vinculada', 'INTEGER')
        adicionar_coluna_se_nao_existe(conn, 'Estimativa_Dolar_BRL', 'REAL')
        adicionar_coluna_se_nao_existe(conn, 'Estimativa_Seguro_BRL', 'REAL')
        adicionar_coluna_se_nao_existe(conn, 'Estimativa_II_BR', 'REAL')
        adicionar_coluna_se_nao_existe(conn, 'Estimativa_IPI_BR', 'REAL')
        adicionar_coluna_se_nao_existe(conn, 'Estimativa_PIS_BR', 'REAL')
        adicionar_coluna_se_nao_existe(conn, 'Estimativa_COFINS_BR', 'REAL')
        adicionar_coluna_se_nao_existe(conn, 'Estimativa_ICMS_BR', 'REAL')
        adicionar_coluna_se_nao_existe(conn, 'Nota_feita', 'TEXT')
        adicionar_coluna_se_nao_existe(conn, 'Conferido', 'TEXT')
        adicionar_coluna_se_nao_existe(conn, 'Ultima_Alteracao_Por', 'TEXT')
        adicionar_coluna_se_nao_existe(conn, 'Ultima_Alteracao_Em', 'TEXT')
        adicionar_coluna_se_nao_existe(conn, 'Estimativa_Impostos_Total', 'REAL') # Adicionando a nova coluna aqui também


        # Lógica para adicionar a coluna 'usuario' à tabela 'historico_processos' se não existir
        cursor.execute("PRAGMA table_info(historico_processos)")
        colunas_history_existentes = [info[1] for info in cursor.fetchall()]
        if 'usuario' not in colunas_history_existentes:
             try:
                  cursor.execute('ALTER TABLE historico_processos ADD COLUMN usuario TEXT')
                  logger.info('Coluna "usuario" (TEXT) adicionada à tabela "historico_processos".')
             except sqlite3.Error as e:
                  logger.error(f'Erro SQLite ao adicionar coluna "usuario" à historico_processos: {e}')
             except Exception as e:
                  logger.exception('Erro inesperado ao adicionar coluna "usuario" à historico_processos')
        else:
             logger.debug('Coluna "usuario" já existe na historico_processos.')

        # --- Novas tabelas para Notificações ---
        cursor.execute('''CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            message TEXT NOT NULL,
            target_users TEXT, -- Agora armazena um único username ou "ALL"
            created_at TEXT NOT NULL,
            created_by TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active' -- 'active', 'deleted'
        )''')
        conn.commit()
        logger.info("Tabela 'notifications' verificada/criada com sucesso.")

        cursor.execute('''CREATE TABLE IF NOT EXISTS notification_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            notification_id INTEGER,
            action TEXT NOT NULL, -- 'deleted', 'restored'
            action_by TEXT NOT NULL,
            action_at TEXT NOT NULL,
            original_message TEXT,
            FOREIGN KEY(notification_id) REFERENCES notifications(id) ON DELETE CASCADE
        )''')
        conn.commit()
        logger.info("Tabela 'notification_history' verificada/criada com sucesso.")

    except Exception as e:
        logger.exception("Erro ao criar ou atualizar as tabelas do Follow-up e Notificações")
        conn.rollback() # Reverte as alterações em caso de erro

# --- Funções para manipulação de ITENS DE PROCESSO ---

def obter_ultimo_processo_id() -> Optional[int]:
    """Obtém o ID do último processo inserido na tabela 'processos'."""
    conn = conectar_followup_db()
    if conn is None:
        return None
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT MAX(id) FROM processos")
        last_id = cursor.fetchone()[0]
        logger.debug(f"Último ID de processo obtido: {last_id}")
        return last_id
    except Exception as e:
        logger.exception("Erro ao obter o último ID de processo.")
        return None
    finally:
        if conn:
            conn.close()

def deletar_itens_processo(processo_id: int) -> bool:
    """Deleta todos os itens associados a um processo específico."""
    conn = conectar_followup_db()
    if conn is None:
        return False
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM process_items WHERE processo_id = ?", (processo_id,))
        conn.commit()
        logger.info(f"Itens do processo ID {processo_id} deletados com sucesso.")
        return True
    except Exception as e:
        logger.exception(f"Erro ao deletar itens do processo ID {processo_id}.")
        conn.rollback()
        return False
    finally:
        if conn:
            conn.close()

def inserir_item_processo(
    processo_id: int,
    codigo_interno: Optional[str],
    ncm: Optional[str],
    cobertura: Optional[str],
    sku: Optional[str],
    quantidade: Optional[float],
    peso_unitario: Optional[float],
    valor_unitario: Optional[float],
    valor_total_item: Optional[float],
    estimativa_ii_br: Optional[float],
    estimativa_ipi_br: Optional[float],
    estimativa_pis_br: Optional[float],
    estimativa_cofins_br: Optional[float],
    estimativa_icms_br: Optional[float],
    frete_rateado_usd: Optional[float],
    seguro_rateado_brl: Optional[float],
    vlmd_item: Optional[float],
    denominacao_produto: Optional[str],
    detalhamento_complementar_produto: Optional[str]
) -> bool:
    """Insere um novo item associado a um processo na tabela process_items."""
    conn = conectar_followup_db()
    if conn is None:
        return False
    try:
        cursor = conn.cursor()
        cursor.execute('''INSERT INTO process_items (
                            processo_id, codigo_interno, ncm, cobertura, sku,
                            quantidade, peso_unitario, valor_unitario, valor_total_item,
                            estimativa_ii_br, estimativa_ipi_br, estimativa_pis_br,
                            estimativa_cofins_br, estimativa_icms_br,
                            frete_rateado_usd, seguro_rateado_brl, vlmd_item,
                            denominacao_produto, detalhamento_complementar_produto
                          ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                       (
                           processo_id, codigo_interno, ncm, cobertura, sku,
                           quantidade, peso_unitario, valor_unitario, valor_total_item,
                           estimativa_ii_br, estimativa_ipi_br, estimativa_pis_br,
                           estimativa_cofins_br, estimativa_icms_br,
                           frete_rateado_usd, seguro_rateado_brl, vlmd_item,
                           denominacao_produto, detalhamento_complementar_produto
                       ))
        conn.commit()
        logger.debug(f"Item inserido para o processo ID {processo_id}.")
        return True
    except Exception as e:
        logger.exception(f"Erro ao inserir item para o processo ID {processo_id}.")
        conn.rollback()
        return False
    finally:
        if conn:
            conn.close()

def obter_itens_processo(processo_id: int) -> List[Dict[str, Any]]:
    """Obtém todos os itens associados a um processo específico."""
    conn = conectar_followup_db()
    if conn is None:
        return []
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM process_items WHERE processo_id = ?", (processo_id,))
        itens = cursor.fetchall()
        return [dict(item) for item in itens]
    except Exception as e:
        logger.exception(f"Erro ao obter itens do processo ID {processo_id}.")
        return []
    finally:
        if conn:
            conn.close()

def obter_processos_filtrados(status_filtro="Todos", termos_pesquisa=None):
    """Busca processos do banco de dados aplicando filtros de status e termos de pesquisa."""
    conn = conectar_followup_db()
    if conn is None:
        return [] # Conexão falhou

    try:
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(processos);")
        colunas_info = cursor.fetchall()
        col_names = [info[1] for info in colunas_info]

        query = "SELECT * FROM processos WHERE 1"
        params = []

        if status_filtro == "Arquivados":
            query += ' AND "Status_Arquivado" = ?'
            params.append("Arquivado")
        elif status_filtro != "Todos":
            query += ' AND "Status_Geral" = ? AND ("Status_Arquivado" IS NULL OR "Status_Arquivado" = "Não Arquivado")'
            params.append(status_filtro)
        else:
            pass
            
        if termos_pesquisa:
            for col, termo in termos_pesquisa.items():
                if termo and col in col_names:
                    query += f' AND "{col}" LIKE ?'
                    params.append(f'%{termo}%')

        query += ' ORDER BY "Status_Geral" ASC, "Modal" ASC'

        logger.debug(f"Query de busca: {query}")
        logger.debug(f"Parâmetros da query: {params}")

        cursor.execute(query, tuple(params))
        processos = cursor.fetchall()
        logger.debug(f"Obtidos {len(processos)} processos do DB com filtros/pesquisa.")
        return processos

    except Exception as e:
        logger.exception("Erro ao obter processos filtrados do DB")
        return []
    finally:
        if conn:
            conn.close()

def obter_todos_processos():
    """Busca todos os processos do banco de dados."""
    conn = conectar_followup_db()
    if conn is None:
        return []
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM processos")
        processos = cursor.fetchall()
        logger.debug(f"Obtidos {len(processos)} processos do DB.")
        return processos
    except Exception as e:
        logger.exception("Erro ao obter todos os processos do DB")
        return []
    finally:
        if conn:
            conn.close()

def obter_processo_por_id(processo_id: int):
    """Busca um processo específico pelo ID."""
    conn = conectar_followup_db()
    if conn is None:
        return None
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM processos WHERE id = ?", (processo_id,))
        processo = cursor.fetchone()
        logger.debug(f"Obtido processo com ID {processo_id}: {processo is not None}")
        return processo
    except Exception as e:
        logger.exception(f"Erro ao obter processo com ID {processo_id}")
        return None
    finally:
        if conn:
            conn.close()

def obter_processo_by_processo_novo(processo_novo: str):
    """Busca um processo específico pela sua referência (Processo_Novo)."""
    conn = conectar_followup_db()
    if conn is None:
        return None
    try:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM processos WHERE "Processo_Novo" = ?', (processo_novo,))
        processo = cursor.fetchone()
        logger.debug(f"Obtido processo com Processo_Novo '{processo_novo}': {processo is not None}")
        return processo
    except Exception as e:
        logger.exception(f"Erro ao obter processo com Processo_Novo '{processo_novo}'")
        return None
    finally:
        if conn:
            conn.close()

def inserir_processo(dados: tuple):
    """Insere um novo processo no banco de dados."""
    conn = conectar_followup_db()
    if conn is None:
        return False
    try:
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(processos);")
        colunas_info = cursor.fetchall()
        colunas = [info[1] for info in colunas_info if info[1] != 'id']

        if len(dados) != len(colunas):
            logger.error(f"Número de dados ({len(dados)}) não corresponde ao número de colunas no DB ({len(colunas)}).")
            return False

        # Cria a string de colunas e placeholders para a query INSERT
        cols_str = ', '.join([f'"{c}"' for c in colunas])
        placeholders = ', '.join(['?'] * len(colunas))
        query = f"INSERT INTO processos ({cols_str}) VALUES ({placeholders})"

        cursor.execute(query, dados)
        conn.commit()
        logger.info("Novo processo inserido com sucesso.")
        return True
    except Exception as e:
        logger.exception("Erro ao inserir novo processo")
        conn.rollback()
        return False
    finally:
        if conn:
            conn.close()

def atualizar_processo(processo_id: int, dados: tuple):
    """Atualiza um processo existente no banco de dados."""
    conn = conectar_followup_db()
    if conn is None:
        return False
    try:
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(processos);")
        colunas_info = cursor.fetchall()
        colunas = [info[1] for info in colunas_info if info[1] != 'id']

        if len(dados) != len(colunas):
            logger.error(f"Número de dados ({len(dados)}) para atualização não corresponde ao número de colunas no DB ({len(colunas)}).")
            return False

        set_clause = ', '.join([f'"{c}" = ?' for c in colunas])
        query = "UPDATE processos SET {} WHERE id = ?".format(set_clause)
        cursor.execute(query, dados + (processo_id,))
        conn.commit()
        logger.info(f"Processo com ID {processo_id} atualizado com sucesso.")
        return True
    except Exception as e:
        logger.exception(f"Erro ao atualizar processo com ID {processo_id}")
        conn.rollback()
        return False
    finally:
        if conn:
            conn.close()

def excluir_processo(processo_id: int):
    """Exclui um processo do banco de dados."""
    conn = conectar_followup_db()
    if conn is None:
        return False
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM processos WHERE id = ?", (processo_id,))
        conn.commit()
        logger.info(f"Processo com ID {processo_id} excluído com sucesso.")
        return True
    except Exception as e:
        logger.exception(f"Erro ao excluir processo com ID {processo_id}")
        conn.rollback()
        return False
    finally:
        if conn:
            conn.close()

def arquivar_processo(processo_id: int):
    """Marca um processo como arquivado no banco de dados."""
    conn = conectar_followup_db()
    if conn is None:
        return False
    try:
        cursor = conn.cursor()
        cursor.execute('UPDATE processos SET "Status_Arquivado" = ? WHERE id = ?', ('Arquivado', processo_id))
        conn.commit()
        logger.info(f"Processo com ID {processo_id} arquivado com sucesso.")
        return True
    except Exception as e:
        logger.exception(f"Erro ao arquivar processo com ID {processo_id}")
        conn.rollback()
        return False
    finally:
        if conn:
            conn.close()

def desarquivar_processo(processo_id: int):
    """Marca um processo como não arquivado (define Status_Arquivado para NULL)."""
    conn = conectar_followup_db()
    if conn is None:
        return False
    try:
        cursor = conn.cursor()
        cursor.execute('UPDATE processos SET "Status_Arquivado" = NULL WHERE id = ?', (processo_id,))
        conn.commit()
        logger.info(f"Processo com ID {processo_id} desarquivado com sucesso.")
        return True
    except Exception as e:
        logger.exception(f"Erro ao desarquivar processo com ID {processo_id}")
        conn.rollback()
        return False
    finally:
        if conn:
            conn.close()

def atualizar_status_processo(processo_id: int, novo_status: Optional[str]):
    """Atualiza o Status_Geral de um processo específico."""
    conn = conectar_followup_db()
    if conn is None:
        return False
    try:
        cursor = conn.cursor()
        original_process_data = obter_processo_por_id(processo_id) # Buscar dados originais aqui
        original_status = original_process_data['Status_Geral'] if original_process_data else None
        
        cursor.execute('UPDATE processos SET "Status_Geral" = ? WHERE id = ?', (novo_status, processo_id))
        conn.commit()
        logger.info(f"Status do processo ID {processo_id} atualizado para '{novo_status}'.")

        user_info = st.session_state.get('user_info', {'username': 'Desconhecido'})
        username = user_info.get('username')
        inserir_historico_processo(processo_id, "Status_Geral", original_status, novo_status, username)
        
        return True
    except Exception as e:
        logger.exception(f"Erro ao atualizar status do processo ID {processo_id}")
        conn.rollback()
        return False
    finally:
        if conn:
            conn.close()

def inserir_historico_processo(processo_id: int, field_name: str, old_value: Optional[str], new_value: Optional[str], username: Optional[str]):
    """Insere um registro na tabela historico_processos."""
    conn = conectar_followup_db()
    if conn is None:
        return False
    try:
        cursor = conn.cursor()
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute('''INSERT INTO historico_processos (processo_id, campo_alterado, valor_antigo, valor_novo, timestamp, usuario)
                          VALUES (?, ?, ?, ?, ?, ?)''',
                       (processo_id, field_name, str(old_value) if old_value is not None else "Vazio", str(new_value) if new_value is not None else "Vazio", timestamp, username if username is not None else "Desconhecido"))
        conn.commit()
        logger.debug(f"Histórico registrado para processo {processo_id}, campo '{field_name}' por '{username}'.")
        return True
    except Exception as e:
        logger.exception(f"Erro ao inserir histórico para processo {processo_id}, campo '{field_name}' por '{username}'")
        conn.rollback()
        return False
    finally:
        if conn:
            conn.close()

def obter_historico_processo(processo_id: int):
    """Busca o histórico de alterações para um processo específico."""
    conn = conectar_followup_db()
    if conn is None:
        return []
    try:
        cursor = conn.cursor()
        cursor.execute('''SELECT campo_alterado, valor_antigo, valor_novo, timestamp, usuario
                          FROM historico_processos
                          WHERE processo_id = ?
                          ORDER BY timestamp ASC''', (processo_id,))
        historico = cursor.fetchall()
        logger.debug(f"Obtido {len(historico)} registros de histórico para processo {processo_id}.")
        return historico
    except Exception as e:
        logger.exception(f"Erro ao obter histórico para processo {processo_id}")
        return []
    finally:
        if conn:
            conn.close()

def obter_status_gerais_distintos():
    """Busca todos os valores distintos da coluna Status_Geral no banco de dados."""
    conn = conectar_followup_db()
    if conn is None:
        return []
    try:
        cursor = conn.cursor()
        cursor.execute('SELECT DISTINCT "Status_Geral" FROM processos WHERE "Status_Geral" IS NOT NULL AND "Status_Geral" != "" ORDER BY "Status_Geral"')
        status_do_db = [row[0] for row in cursor.fetchall()]
        logger.debug(f"Obtidos {len(status_do_db)} status gerais distintos do DB.")
        return status_do_db
    except Exception as e:
        logger.exception("Erro ao obter status gerais distintos do DB")
        return []
    finally:
        if conn:
            conn.close()

def obter_nomes_colunas_db():
    """Retorna uma lista com os nomes das colunas da tabela processos."""
    conn = conectar_followup_db()
    if conn is None:
        return []
    try:
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(processos);")
        colunas_info = cursor.fetchall()
        col_names = [info[1] for info in colunas_info]
        logger.debug(f"Obtidos {len(col_names)} nomes de colunas do DB.")
        return col_names
    except Exception as e:
        logger.exception("Erro ao obter nomes de colunas do DB")
        return []
    finally:
        if conn:
            conn.close()

# --- Funções de gerenciamento de Notificações ---

def add_notification(message: str, target_user: str, created_by: str, status: str = 'active'):
    """Adiciona uma nova notificação ao banco de dados para um único usuário ou 'ALL'."""
    conn = conectar_followup_db()
    if conn is None:
        return False
    try:
        cursor = conn.cursor()
        created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        # target_user já é uma string (username ou "ALL")
        cursor.execute('''INSERT INTO notifications (message, target_users, created_at, created_by, status)
                          VALUES (?, ?, ?, ?, ?)''',
                       (message, target_user, created_at, created_by, status))
        conn.commit()
        logger.info(f"Notificação adicionada por {created_by} para {target_user}.")
        return True
    except Exception as e:
        logger.exception("Erro ao adicionar notificação.")
        conn.rollback()
        return False
    finally:
        if conn:
            conn.close()

def get_active_notifications(username: Optional[str] = None):
    """
    Busca notificações ativas. Se username for fornecido, busca notificações para esse usuário
    ou notificações destinadas a 'ALL'.
    """
    conn = conectar_followup_db()
    if conn is None:
        return []
    try:
        cursor = conn.cursor()
        # Buscar todas as notificações ativas
        query = "SELECT * FROM notifications WHERE status = 'active' ORDER BY created_at DESC"
        cursor.execute(query)
        all_active_notifications = cursor.fetchall()

        filtered_notifications = []
        for notif in all_active_notifications:
            target_user_str = notif['target_users'] # target_users é uma string simples (username ou "ALL")
            
            # Lógica de filtragem aprimorada
            if username is None: # Admin view: mostra todas as ativas
                filtered_notifications.append(dict(notif))
            elif target_user_str == "ALL": # Notificação para todos
                filtered_notifications.append(dict(notif))
            elif target_user_str == username: # Notificação para o usuário específico
                filtered_notifications.append(dict(notif))
        
        return filtered_notifications
    except Exception as e:
        logger.exception("Erro ao obter notificações ativas.")
        return []
    finally:
        if conn:
            conn.close()

def mark_notification_as_deleted(notification_id: int, deleted_by: str):
    """Marca uma notificação como excluída e registra no histórico."""
    conn = conectar_followup_db()
    if conn is None:
        return False
    try:
        cursor = conn.cursor()
        
        # Obter a mensagem original da notificação antes de marcar como excluída
        cursor.execute("SELECT message FROM notifications WHERE id = ?", (notification_id,))
        original_message = cursor.fetchone()
        if original_message:
            original_message_text = original_message['message']
        else:
            original_message_text = "Mensagem original não encontrada."

        cursor.execute("UPDATE notifications SET status = 'deleted' WHERE id = ?", (notification_id,))
        
        action_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute('''INSERT INTO notification_history (notification_id, action, action_by, action_at, original_message)
                          VALUES (?, ?, ?, ?, ?)''',
                       (notification_id, 'deleted', deleted_by, action_at, original_message_text))
        conn.commit()
        logger.info(f"Notificação ID {notification_id} marcada como excluída por {deleted_by}.")
        return True
    except Exception as e:
        logger.exception(f"Erro ao marcar notificação ID {notification_id} como excluída.")
        conn.rollback()
        return False
    finally:
        if conn:
            conn.close()

def get_deleted_notifications():
    """Busca notificações excluídas do histórico."""
    conn = conectar_followup_db()
    if conn is None:
        return []
    try:
        cursor = conn.cursor()
        # Corrigido: Buscar a coluna 'original_message' diretamente do histórico
        # Adicionado o 'nh.id as history_entry_id' para ter uma chave única para os botões no Streamlit
        query = "SELECT nh.id as history_entry_id, nh.notification_id as original_notification_id, nh.original_message, nh.action_at, nh.action_by FROM notification_history nh WHERE nh.action = 'deleted' ORDER BY nh.action_at DESC"
        cursor.execute(query)
        notifications = cursor.fetchall()
        return [dict(n) for n in notifications]
    except Exception as e:
        logger.exception("Erro ao obter notificações excluídas.")
        return []
    finally:
        if conn:
            conn.close()

def restore_notification(notification_id: int, restored_by: str):
    """Restaura uma notificação excluída (status para 'active') e registra no histórico."""
    conn = conectar_followup_db()
    if conn is None:
        return False
    try:
        cursor = conn.cursor()
        
        # Obter a mensagem original da notificação antes de restaurar
        cursor.execute("SELECT message FROM notifications WHERE id = ?", (notification_id,))
        original_message = cursor.fetchone()
        if original_message:
            original_message_text = original_message['message']
        else:
            original_message_text = "Mensagem original não encontrada."

        cursor.execute("UPDATE notifications SET status = 'active' WHERE id = ?", (notification_id,))
        
        action_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute('''INSERT INTO notification_history (notification_id, action, action_by, action_at, original_message)
                          VALUES (?, ?, ?, ?, ?)''',
                       (notification_id, 'restored', restored_by, action_at, original_message_text))
        conn.commit()
        logger.info(f"Notificação ID {notification_id} restaurada por {restored_by}.")
        return True
    except Exception as e:
        logger.exception(f"Erro ao restaurar notificação ID {notification_id}.")
        conn.rollback()
        return False
    finally:
        if conn:
            conn.close()

def delete_history_entry_permanently(history_entry_id: int, deleted_by: str):
    """
    Exclui permanentemente uma entrada do histórico de notificações.
    """
    conn = conectar_followup_db()
    if conn is None:
        return False
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM notification_history WHERE id = ?", (history_entry_id,))
        conn.commit()
        logger.info(f"Entrada do histórico ID {history_entry_id} excluída permanentemente por {deleted_by}.")
        return True
    except Exception as e:
        logger.exception(f"Erro ao excluir permanentemente a entrada do histórico ID {history_entry_id}.")
        conn.rollback()
        return False
    finally:
        if conn:
            conn.close()

def get_all_users_from_db():
    """
    Obtém todos os usuários do banco de dados principal através de db_utils.
    """
    try:
        # Chama a função get_all_users do módulo db_utils
        users = db_utils.get_all_users()
        logger.info(f"Obtidos {len(users)} usuários via db_utils.get_all_users().")
        return users
    except AttributeError:
        logger.error("db_utils.get_all_users() não encontrada. Verifique o módulo db_utils.")
        # Fallback para usuários simulados se a função não existir em db_utils
        return [
            {'id': 1, 'username': 'admin'},
            {'id': 2, 'username': 'usuario1'},
            {'id': 3, 'username': 'usuario2'}
        ]
    except Exception as e:
        logger.exception("Erro inesperado ao obter usuários via db_utils.")
        return [
            {'id': 1, 'username': 'admin'},
            {'id': 2, 'username': 'usuario1'},
            {'id': 3, 'username': 'usuario2'}
        ]
