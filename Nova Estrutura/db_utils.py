# -*- coding: utf-8 -*-
import sqlite3
import logging
import os
import xml.etree.ElementTree as ET
from datetime import datetime
import re
import pandas as pd # Will be useful for data handling
import hashlib # For user password hashing
from typing import Optional, Dict, Any, List, Tuple # Importa Optional, Dict, Any, List, Tuple

logger = logging.getLogger(__name__)

# Default DB path (adjust as needed for deployment)
# For now, assume it's in a 'data' folder relative to the main app.
_DEFAULT_DB_FOLDER = "data"
_XML_DI_DB_FILENAME = "analise_xml_di.db"
_USERS_DB_FILENAME = "users.db"
_PRODUTOS_DB_FILENAME = "banco_de_dados_descricao.db" # NOVO: Nome do DB de produtos
_NCM_DB_FILENAME = "banco_de_dados_ncm_draft_BL.db" # NOVO: Nome do DB de NCM
_PAGAMENTOS_DB_FILENAME = "pagamentos_container.db" # NOVO: Nome do DB de pagamentos
_FOLLOWUP_DB_FILENAME = "followup_importacao.db" # NOVO: Nome do DB de followup


# Determine base path for relative DB access
# This might need adjustment depending on how the Streamlit app is run or deployed
_base_path = os.path.dirname(os.path.abspath(__file__))
# Go up one level from 'app_logic' (if running from app_logic) or stay at root
_app_root_path = os.path.dirname(_base_path) if os.path.basename(_base_path) == 'app_logic' else _base_path

_DB_PATHS = {
    "xml_di": os.path.join(_app_root_path, _DEFAULT_DB_FOLDER, _XML_DI_DB_FILENAME),
    "users": os.path.join(_app_root_path, _DEFAULT_DB_FOLDER, _USERS_DB_FILENAME),
    "produtos": os.path.join(_app_root_path, _DEFAULT_DB_FOLDER, _PRODUTOS_DB_FILENAME), # NOVO
    "ncm": os.path.join(_app_root_path, _DEFAULT_DB_FOLDER, _NCM_DB_FILENAME), # NOVO
    "pagamentos": os.path.join(_app_root_path, _DEFAULT_DB_FOLDER, _PAGAMENTOS_DB_FILENAME), # NOVO
    "followup": os.path.join(_app_root_path, _DEFAULT_DB_FOLDER, _FOLLOWUP_DB_FILENAME), # NOVO
}


def get_db_path(db_type: str):
    """Returns the appropriate database path for a given type."""
    return _DB_PATHS.get(db_type)

def connect_db(db_path: str):
    """Conecta ao banco de dados."""
    if not db_path:
        logger.error("Caminho do DB não definido.")
        return None
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row # Allows accessing columns by name
        logger.debug(f"Conectado com sucesso ao DB: {db_path}")
        return conn
    except Exception as e:
        logger.error(f"Erro ao conectar ao DB {db_path}: {e}")
        return None

def create_tables():
    """Cria todas as tabelas necessárias para o aplicativo."""
    success = True
    
    # Ensure data directory exists
    data_dir = os.path.join(_app_root_path, _DEFAULT_DB_FOLDER)
    if not os.path.exists(data_dir):
        os.makedirs(data_dir)
        logger.info(f"Diretório de dados '{data_dir}' criado.")

    # Create XML DI tables
    conn_xml_di = connect_db(get_db_path("xml_di"))
    if conn_xml_di:
        try:
            cursor = conn_xml_di.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS xml_declaracoes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    numero_di TEXT UNIQUE,
                    data_registro TEXT,
                    valor_total_reais_xml REAL,
                    arquivo_origem TEXT,
                    data_importacao TEXT,
                    informacao_complementar TEXT,
                    vmle REAL,
                    frete REAL,
                    seguro REAL,
                    vmld REAL,
                    ipi REAL,
                    pis_pasep REAL,
                    cofins REAL,
                    icms_sc TEXT,
                    taxa_cambial_usd REAL,
                    taxa_siscomex REAL,
                    numero_invoice TEXT,
                    peso_bruto REAL,
                    peso_liquido REAL,
                    cnpj_importador TEXT,
                    importador_nome TEXT,
                    recinto TEXT,
                    embalagem TEXT,
                    quantidade_volumes INTEGER,
                    acrescimo REAL,
                    imposto_importacao REAL,
                    armazenagem REAL,
                    frete_nacional REAL
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS xml_itens (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    declaracao_id INTEGER,
                    numero_adicao TEXT,
                    numero_item_sequencial TEXT,
                    descricao_mercadoria TEXT,
                    quantidade REAL,
                    unidade_medida TEXT,
                    valor_unitario REAL,
                    valor_item_calculado REAL,
                    peso_liquido_item REAL,
                    ncm_item TEXT,
                    sku_item TEXT,
                    custo_unit_di_usd REAL,
                    ii_percent_item REAL,
                    ipi_percent_item REAL,
                    pis_percent_item REAL,
                    cofins_percent_item REAL,
                    icms_percent_item REAL,
                    codigo_erp_item TEXT,
                    FOREIGN KEY (declaracao_id) REFERENCES xml_declaracoes(id) ON DELETE CASCADE
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS processo_dados_custo (
                    declaracao_id INTEGER PRIMARY KEY,
                    afrmm REAL,
                    siscoserv REAL,
                    descarregamento REAL,
                    taxas_destino REAL,
                    multa REAL,
                    FOREIGN KEY (declaracao_id) REFERENCES xml_declaracoes(id) ON DELETE CASCADE
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS processo_contratos_cambio (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    declaracao_id INTEGER,
                    numero_contrato TEXT,
                    dolar_cambio REAL,
                    valor_usd REAL,
                    FOREIGN KEY (declaracao_id) REFERENCES xml_declaracoes(id) ON DELETE CASCADE
                )
            ''')
            conn_xml_di.commit()
            logger.info("Tabelas XML DI e Custo verificadas/criadas.")
        except Exception as e:
            logger.error(f"Erro ao criar tabelas XML DI/Custo: {e}")
            conn_xml_di.rollback()
            success = False
        finally:
            conn_xml_di.close()
    else:
        success = False

    # Create Produtos table
    conn_produtos = connect_db(get_db_path("produtos"))
    if conn_produtos:
        try:
            cursor = conn_produtos.cursor()
            # Mapeamento de colunas para a tabela de produtos (consistente com view_descricoes)
            _COLS_MAP_PRODUTOS = {
                "id": {"text": "ID/Key ERP", "width": 120, "col_id": "id_key_erp"},
                "nome": {"text": "Nome/Part", "width": 200, "col_id": "nome_part"},
                "desc": {"text": "Descrição", "width": 350, "col_id": "descricao"},
                "ncm": {"text": "NCM", "width": 100, "col_id": "ncm"}
            }
            cursor.execute(f'''
                CREATE TABLE IF NOT EXISTS produtos (
                    {_COLS_MAP_PRODUTOS['id']['col_id']} TEXT PRIMARY KEY,
                    {_COLS_MAP_PRODUTOS['nome']['col_id']} TEXT,
                    {_COLS_MAP_PRODUTOS['desc']['col_id']} TEXT,
                    {_COLS_MAP_PRODUTOS['ncm']['col_id']} TEXT
                )
            ''')
            conn_produtos.commit()
            logger.info("Tabela Produtos verificada/criada.")
        except Exception as e:
            logger.error(f"Erro ao criar tabela Produtos: {e}")
            conn_produtos.rollback()
            success = False
        finally:
            conn_produtos.close()
    else:
        success = False

    # Create NCM table
    conn_ncm = connect_db(get_db_path("ncm"))
    if conn_ncm:
        try:
            cursor = conn_ncm.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS ncm_items (
                    item_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    item_name TEXT NOT NULL,
                    item_ncm TEXT,
                    parent_id INTEGER,
                    FOREIGN KEY(parent_id) REFERENCES ncm_items(item_id) ON DELETE CASCADE
                )
            ''')
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_ncm_parent ON ncm_items (parent_id);")
            conn_ncm.commit()
            logger.info("Tabela NCM verificada/criada.")
        except Exception as e:
            logger.error(f"Erro ao criar tabela NCM: {e}")
            conn_ncm.rollback()
            success = False
        finally:
            conn_ncm.close()
    else:
        success = False

    # Create Pagamentos table
    conn_pagamentos = connect_db(get_db_path("pagamentos"))
    if conn_pagamentos:
        try:
            cursor = conn_pagamentos.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS pagamentos_container (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    DATA TEXT,
                    NOME TEXT,
                    QUANTIDADE INTEGER
                )
            ''')
            conn_pagamentos.commit()
            logger.info("Tabela Pagamentos verificada/criada.")
        except Exception as e:
            logger.error(f"Erro ao criar tabela Pagamentos: {e}")
            conn_pagamentos.rollback()
            success = False
        finally:
            conn_pagamentos.close()
    else:
        success = False

    # Create Follow-up tables
    # This part will now rely on followup_db_manager to create its tables
    # We just ensure the path is set for followup_db_manager
    import followup_db_manager
    followup_db_manager.set_followup_db_path(get_db_path("followup"))
    conn_followup = followup_db_manager.conectar_followup_db()
    if conn_followup:
        try:
            followup_db_manager.criar_tabela_followup(conn_followup)
            conn_followup.close()
            logger.info("Tabelas Follow-up verificadas/criadas via followup_db_manager.")
        except Exception as e:
            logger.error(f"Erro ao criar tabelas Follow-up via followup_db_manager: {e}")
            conn_followup.rollback()
            success = False
        finally:
            if conn_followup: conn_followup.close()
    else:
        success = False


    return success

def create_user_table():
    """Cria a tabela de usuários se não existir e insere um usuário admin padrão."""
    conn = connect_db(get_db_path("users"))
    if not conn: return False
    try:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                is_admin INTEGER DEFAULT 0,
                allowed_screens TEXT
            )
        ''')
        conn.commit()
        
        # Check if default admin user exists
        cursor.execute("SELECT COUNT(*) FROM users WHERE username = 'admin'")
        if cursor.fetchone()[0] == 0:
            admin_username = "admin"
            admin_password_hash = hash_password("admin", admin_username) # Use 'admin' as password
            # Default admin has access to all screens (mock list)
            all_screens_mock = "Home,Descrições,Listagem NCM,Follow-up Importação,Importar XML DI,Detalhes DI e Cálculos,Custo do Processo,Análise de Documentos,Pagamentos Container,Cálculo de Tributos TTCE,Gerenciamento de Usuários"
            cursor.execute("INSERT INTO users (username, password_hash, is_admin, allowed_screens) VALUES (?, ?, ?, ?)",
                           (admin_username, admin_password_hash, 1, all_screens_mock))
            conn.commit()
            logger.info("Usuário 'admin' padrão criado.")
        return True
    except Exception as e:
        logger.error(f"Erro ao criar tabela de usuários ou inserir admin: {e}")
        conn.rollback()
        return False
    finally:
        if conn: conn.close()

def hash_password(password: str, username: str) -> str:
    """Hashes a password with a username as salt."""
    password_salted = password + username
    return hashlib.sha256(password_salted.encode('utf-8')).hexdigest()

def verify_credentials(username: str, password: str) -> Optional[Dict[str, Any]]:
    """Verifies user credentials against the database."""
    conn = connect_db(get_db_path("users"))
    if not conn: return None
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT username, password_hash, is_admin, allowed_screens FROM users WHERE username = ?", (username,))
        user_data = cursor.fetchone()

        if user_data:
            db_username, stored_password_hash, is_admin, allowed_screens_str = user_data
            provided_password_hash = hash_password(password, db_username)

            if provided_password_hash == stored_password_hash:
                logger.info(f"Login bem-sucedido para o usuário: {username}")
                allowed_screens_list = allowed_screens_str.split(',') if allowed_screens_str else []
                return {'username': db_username, 'is_admin': bool(is_admin), 'allowed_screens': allowed_screens_list}
            else:
                logger.warning(f"Tentativa de login falhou para o usuário {username}: Senha incorreta.")
                return False
        else:
            logger.warning(f"Tentativa de login falhou: Usuário '{username}' não encontrado.")
            return False
    except Exception as e:
        logger.error(f"Erro ao verificar credenciais para o usuário {username}: {e}")
        return None
    finally:
        if conn: conn.close()

# --- XML DI Functions ---
def get_all_declaracoes():
    """Carrega e retorna todos os dados das declarações XML do banco de dados."""
    conn = connect_db(get_db_path("xml_di"))
    if not conn: return []
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, numero_di, data_registro, informacao_complementar, arquivo_origem, data_importacao
            FROM xml_declaracoes ORDER BY data_importacao DESC, numero_di DESC
        """)
        return cursor.fetchall()
    except Exception as e:
        logger.error(f"Erro DB ao carregar todas as declarações XML DI: {e}")
    finally:
        if conn: conn.close()
    return []

def get_declaracao_by_id(declaracao_id: int):
    conn = connect_db(get_db_path("xml_di"))
    if not conn: return None
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, numero_di, data_registro, valor_total_reais_xml, arquivo_origem, data_importacao,
                   informacao_complementar, vmle, frete, seguro, vmld, ipi, pis_pasep, cofins, icms_sc,
                   taxa_cambial_usd, taxa_siscomex, numero_invoice, peso_bruto, peso_liquido,
                   cnpj_importador, importador_nome, recinto, embalagem, quantidade_volumes, acrescimo,
                   imposto_importacao, armazenagem, frete_nacional
            FROM xml_declaracoes WHERE id = ?
        """, (declaracao_id,))
        return cursor.fetchone()
    except Exception as e:
        logger.error(f"Erro DB ao buscar declaração ID {declaracao_id}: {e}")
    finally:
        if conn: conn.close()
    return None

def get_declaracao_by_referencia(referencia: str):
    conn = connect_db(get_db_path("xml_di"))
    if not conn: return None
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, numero_di, data_registro, valor_total_reais_xml, arquivo_origem, data_importacao,
                   informacao_complementar, vmle, frete, seguro, vmld, ipi, pis_pasep, cofins, icms_sc,
                   taxa_cambial_usd, taxa_siscomex, numero_invoice, peso_bruto, peso_liquido,
                   cnpj_importador, importador_nome, recinto, embalagem, quantidade_volumes, acrescimo,
                   imposto_importacao, armazenagem, frete_nacional
            FROM xml_declaracoes WHERE informacao_complementar = ?
        """, (referencia,))
        return cursor.fetchone()
    except Exception as e:
        logger.error(f"Erro DB ao buscar declaração por referência '{referencia}': {e}")
    finally:
        if conn: conn.close()
    return None

def get_itens_by_declaracao_id(declaracao_id: int):
    conn = connect_db(get_db_path("xml_di"))
    if not conn: return []
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, declaracao_id, numero_adicao, numero_item_sequencial, descricao_mercadoria, quantidade, unidade_medida,
                   valor_unitario, valor_item_calculado, peso_liquido_item, ncm_item, sku_item,
                   custo_unit_di_usd, ii_percent_item, ipi_percent_item, pis_percent_item, cofins_percent_item, icms_percent_item,
                   codigo_erp_item
            FROM xml_itens WHERE declaracao_id = ?
            ORDER BY numero_adicao ASC, numero_item_sequencial ASC
        """, (declaracao_id,))
        return cursor.fetchall()
    except Exception as e:
        logger.error(f"Erro DB ao buscar itens para declaração ID {declaracao_id}: {e}")
    finally:
        if conn: conn.close()
    return []

def update_xml_item_erp_code(item_id: int, new_erp_code: str):
    conn = connect_db(get_db_path("xml_di"))
    if not conn: return False
    try:
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE xml_itens
            SET codigo_erp_item = ?
            WHERE id = ?
        ''', (new_erp_code, item_id))
        conn.commit()
        logger.info(f"Item ID {item_id} atualizado com Código ERP: {new_erp_code}.")
        return True
    except Exception as e:
        logger.error(f"Erro DB ao atualizar Código ERP para item ID {item_id}: {e}")
        conn.rollback()
        return False
    finally:
        if conn: conn.close()

def save_process_cost_data(declaracao_id: int, afrmm: float, siscoserv: float, descarregamento: float, taxas_destino: float, multa: float, contracts_df: pd.DataFrame):
    conn = connect_db(get_db_path("xml_di"))
    if not conn: return False
    try:
        cursor = conn.cursor()

        cursor.execute("SELECT declaracao_id FROM processo_dados_custo WHERE declaracao_id = ?", (declaracao_id,))
        if cursor.fetchone():
            cursor.execute('''
                UPDATE processo_dados_custo
                SET afrmm = ?, siscoserv = ?, descarregamento = ?, taxas_destino = ?, multa = ?
                WHERE declaracao_id = ?
            ''', (afrmm, siscoserv, descarregamento, taxas_destino, multa, declaracao_id))
            logger.info(f"Despesas atualizadas para DI ID {declaracao_id}.")
        else:
            cursor.execute('''
                INSERT INTO processo_dados_custo (declaracao_id, afrmm, siscoserv, descarregamento, taxas_destino, multa)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (declaracao_id, afrmm, siscoserv, descarregamento, taxas_destino, multa))
            logger.info(f"Despesas inseridas para DI ID {declaracao_id}.")
        conn.commit()

        cursor.execute("DELETE FROM processo_contratos_cambio WHERE declaracao_id = ?", (declaracao_id,))
        logger.debug(f"Contratos antigos deletados para DI ID {declaracao_id}.")

        for index, row in contracts_df.iterrows():
            num_contrato = row['Nº Contrato']
            dolar_cambio = row['Dólar']
            valor_contrato_usd = row['Valor (US$)']

            if dolar_cambio > 0 and valor_contrato_usd > 0 and num_contrato:
                cursor.execute('''
                    INSERT INTO processo_contratos_cambio (declaracao_id, numero_contrato, dolar_cambio, valor_usd)
                    VALUES (?, ?, ?, ?)
                ''', (declaracao_id, num_contrato, dolar_cambio, valor_contrato_usd))
        conn.commit()
        logger.info(f"Contratos de câmbio salvos para DI ID {declaracao_id}.")
        return True
    except Exception as e:
        logger.error(f"Erro ao salvar despesas/contratos para DI ID {declaracao_id}: {e}")
        conn.rollback()
        return False
    finally:
        if conn: conn.close()

def get_process_cost_data(declaracao_id: int):
    conn = connect_db(get_db_path("xml_di"))
    if not conn: return None, []
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT afrmm, siscoserv, descarregamento, taxas_destino, multa FROM processo_dados_custo WHERE declaracao_id = ?", (declaracao_id,))
        expenses_db = cursor.fetchone()
        
        cursor.execute("SELECT numero_contrato, dolar_cambio, valor_usd FROM processo_contratos_cambio WHERE declaracao_id = ? ORDER BY id ASC", (declaracao_id,))
        contracts_db = cursor.fetchall()

        return expenses_db, contracts_db
    except Exception as e:
        logger.error(f"Erro ao carregar dados de custo para DI ID {declaracao_id}: {e}")
    finally:
        if conn: conn.close()
    return None, []

def parse_xml_data_to_dict(xml_file_content: str) -> Tuple[Optional[Dict[str, Any]], Optional[List[Dict[str, Any]]]]:
    try:
        root = ET.fromstring(xml_file_content)
        numero_di_elem = root.find('.//declaracaoImportacao/numeroDI')
        numero_di = numero_di_elem.text.strip() if numero_di_elem is not None and numero_di_elem.text else None
        if not numero_di:
            logger.error("Não foi possível encontrar o número da DI no XML.")
            return None, None
        data_registro_elem = root.find('.//declaracaoImportacao/dataRegistro')
        data_registro_str = data_registro_elem.text.strip() if data_registro_elem is not None and data_registro_elem.text else None
        data_registro_db = None
        if data_registro_str and len(data_registro_str) == 8:
            try:
                data_registro_obj = datetime.strptime(data_registro_str, "%Y%m%d")
                data_registro_db = data_registro_obj.strftime("%Y-%m-%d")
            except ValueError:
                pass
        informacao_complementar_elem = root.find('.//declaracaoImportacao/informacaoComplementar')
        informacao_completa_str = informacao_complementar_elem.text.strip() if informacao_complementar_elem is not None and informacao_complementar_elem.text else ""
        referencia_extraida = "N/A"
        match_referencia = re.search(r'REFERENCIA:\s*([A-Z0-9-/]+)', informacao_completa_str)
        if match_referencia:
            referencia_extraida = match_referencia.group(1)
        vmle = float(root.find('.//declaracaoImportacao/localEmbarqueTotalReais').text.strip()) / 100 if root.find('.//declaracaoImportacao/localEmbarqueTotalReais') is not None and root.find('.//declaracaoImportacao/localEmbarqueTotalReais').text else 0.0
        frete = float(root.find('.//declaracaoImportacao/freteTotalReais').text.strip()) / 100 if root.find('.//declaracaoImportacao/freteTotalReais') is not None and root.find('.//declaracaoImportacao/freteTotalReais').text else 0.0
        seguro = float(root.find('.//declaracaoImportacao/seguroTotalReais').text.strip()) / 100 if root.find('.//declaracaoImportacao/seguroTotalReais') is not None and root.find('.//declaracaoImportacao/seguroTotalReais').text else 0.0
        vmld = float(root.find('.//declaracaoImportacao/localDescargaTotalReais').text.strip()) / 100 if root.find('.//declaracaoImportacao/localDescargaTotalReais') is not None and root.find('.//declaracaoImportacao/localDescargaTotalReais').text else 0.0
        ipi = float(root.find(".//pagamento[codigoReceita='1038']/valorReceita").text.strip()) / 100 if root.find(".//pagamento[codigoReceita='1038']/valorReceita") is not None and root.find(".//pagamento[codigoReceita='1038']/valorReceita").text else 0.0
        pis_pasep = float(root.find(".//pagamento[codigoReceita='5602']/valorReceita").text.strip()) / 100 if root.find(".//pagamento[codigoReceita='5602']/valorReceita") is not None and root.find(".//pagamento[codigoReceita='5602']/valorReceita").text else 0.0
        cofins = float(root.find(".//pagamento[codigoReceita='5629']/valorReceita").text.strip()) / 100 if root.find(".//pagamento[codigoReceita='5629']/valorReceita") is not None and root.find(".//pagamento[codigoReceita='5629']/valorReceita").text else 0.0
        icms_sc = re.search(r'ICMS-SC IMPORTAÇÃO....:\s*(.+?)[\n\r]', informacao_completa_str).group(1).strip() if re.search(r'ICMS-SC IMPORTAÇÃO....:\s*(.+?)[\n\r]', informacao_completa_str) else "N/A"
        taxa_cambial_usd = float(re.search(r'TAXA CAMBIAL\(USD\):\s*([\d\.,]+)', informacao_completa_str).group(1).replace(',', '.')) if re.search(r'TAXA CAMBIAL\(USD\):\s*([\d\.,]+)', informacao_completa_str) else 0.0
        taxa_siscomex = float(root.find(".//pagamento[codigoReceita='7811']/valorReceita").text.strip()) / 100 if root.find(".//pagamento[codigoReceita='7811']/valorReceita") is not None and root.find(".//pagamento[codigoReceita='7811']/valorReceita").text else 0.0
        numero_invoice = "N/A"
        documentos_despacho = root.findall(".//documentoInstrucaoDespacho")
        for doc in documentos_despacho:
            nome_doc_elem = doc.find("nomeDocumentoDespacho")
            numero_doc_elem = doc.find("numeroDocumentoDespacho")
            if nome_doc_elem is not None and numero_doc_elem is not None:
                nome_doc = nome_doc_elem.text.strip().upper()
                if "FATURA COMERCIAL" in nome_doc:
                    numero_invoice = numero_doc_elem.text.strip()
                    break
        peso_bruto = float(root.find('.//declaracaoImportacao/cargaPesoBruto').text.strip()) / 100000.0 if root.find('.//declaracaoImportacao/cargaPesoBruto') is not None and root.find('.//declaracaoImportacao/cargaPesoBruto').text else 0.0
        peso_liquido = float(root.find('.//declaracaoImportacao/cargaPesoLiquido').text.strip()) / 100000.0 if root.find('.//declaracaoImportacao/cargaPesoLiquido') is not None and root.find('.//declaracaoImportacao/cargaPesoLiquido').text else 0.0
        cnpj_importador = root.find('.//declaracaoImportacao/importadorNumero').text.strip() if root.find('.//declaracaoImportacao/importadorNumero') is not None and root.find('.//declaracaoImportacao/importadorNumero').text else "N/A"
        importador_nome = root.find('.//declaracaoImportacao/importadorNome').text.strip() if root.find('.//declaracaoImportacao/importadorNome') is not None and root.find('.//declaracaoImportacao/importadorNome').text else "N/A"
        recinto = root.find('.//declaracaoImportacao/armazenamentoRecintoAduaneiroNome').text.strip() if root.find('.//declaracaoImportacao/armazenamentoRecintoAduaneiroNome') is not None and root.find('.//declaracaoImportacao/armazenamentoRecintoAduaneiroNome').text else "N/A"
        embalagem = root.find('.//declaracaoImportacao/embalagem/nomeEmbalagem').text.strip() if root.find('.//declaracaoImportacao/embalagem/nomeEmbalagem') is not None and root.find('.//declaracaoImportacao/embalagem/nomeEmbalagem').text else "N/A"
        quantidade_volumes = int(root.find('.//declaracaoImportacao/embalagem/quantidadeVolume').text.strip()) if root.find('.//declaracaoImportacao/embalagem/quantidadeVolume') is not None and root.find('.//declaracaoImportacao/embalagem/quantidadeVolume').text and root.find('.//declaracaoImportacao/embalagem/quantidadeVolume').text.isdigit() else 0
        acrescimo = sum(float(elem.text.strip()) / 100 for elem in root.findall('.//declaracaoImportacao/adicao/acrescimo/valorReais') if elem.text)
        imposto_importacao = sum(float(elem.text.strip()) / 100 for elem in root.findall(".//pagamento[codigoReceita='0086']/valorReceita") if elem.text)
        armazenagem_val = 0.0
        frete_nacional_val = 0.0
        valor_total_reais_xml = vmle
        arquivo_origem = "XML_Importado"
        data_importacao = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        di_data = {
            "numero_di": numero_di, "data_registro": data_registro_db, "valor_total_reais_xml": valor_total_reais_xml,
            "arquivo_origem": arquivo_origem, "data_importacao": data_importacao,
            "informacao_complementar": referencia_extraida, "vmle": vmle, "frete": frete, "seguro": seguro,
            "vmld": vmld, "ipi": ipi, "pis_pasep": pis_pasep, "cofins": cofins, "icms_sc": icms_sc,
            "taxa_cambial_usd": taxa_cambial_usd, "taxa_siscomex": taxa_siscomex, "numero_invoice": numero_invoice,
            "peso_bruto": peso_bruto, "peso_liquido": peso_liquido, "cnpj_importador": cnpj_importador,
            "importador_nome": importador_nome, "recinto": recinto, "embalagem": embalagem,
            "quantidade_volumes": quantidade_volumes, "acrescimo": acrescimo, "imposto_importacao": imposto_importacao,
            "armazenagem": armazenagem_val, "frete_nacional": frete_nacional_val
        }

        itens_data = []
        adicoes = root.findall('.//declaracaoImportacao/adicao')
        for adicao in adicoes:
            numero_adicao = adicao.find('numeroAdicao').text.strip() if adicao.find('numeroAdicao') is not None and adicao.find('numeroAdicao').text else "N/A"
            peso_liquido_total_adicao = float(adicao.find('dadosMercadoriaPesoLiquido').text.strip()) / 100000.0 if adicao.find('dadosMercadoriaPesoLiquido') is not None and adicao.find('dadosMercadoriaPesoLiquido').text else 0.0
            
            quantidade_total_adicao_from_items = 0.0
            mercadorias_in_current_adicao = adicao.findall('mercadoria')
            for mercadoria_elem_in_adicao in mercadorias_in_current_adicao:
                quantidade_item_str = mercadoria_elem_in_adicao.find('quantidade').text.strip() if mercadoria_elem_in_adicao.find('quantidade') is not None else "0"
                try:
                    quantidade_total_adicao_from_items += float(quantidade_item_str) / 10**5
                except ValueError:
                    pass

            peso_unitario_medio_adicao = peso_liquido_total_adicao / quantidade_total_adicao_from_items if quantidade_total_adicao_from_items > 0 else 0.0

            ii_perc_adicao = float(adicao.find('iiAliquotaAdValorem').text.strip()) / 10000.0 if adicao.find('iiAliquotaAdValorem') is not None and adicao.find('iiAliquotaAdValorem').text else 0.0
            ipi_perc_adicao = float(adicao.find('ipiAliquotaAdValorem').text.strip()) / 10000.0 if adicao.find('ipiAliquotaAdValorem') is not None and adicao.find('ipiAliquotaAdValorem').text else 0.0
            pis_perc_adicao = float(adicao.find('pisPasepAliquotaAdValorem').text.strip()) / 10000.0 if adicao.find('pisPasepAliquotaAdValorem') is not None and adicao.find('pisPasepAliquotaAdValorem').text else 0.0
            cofins_perc_adicao = float(adicao.find('cofinsAliquotaAdValorem').text.strip()) / 10000.0 if adicao.find('cofinsAliquotaAdValorem') is not None and adicao.find('cofinsAliquotaAdValorem').text else 0.0
            icms_perc_adicao = 0.0

            mercadorias = adicao.findall('mercadoria')
            item_counter_in_adicao = 1
            for mercadoria_elem in mercadorias:
                descricao = mercadoria_elem.find('descricaoMercadoria').text.strip() if mercadoria_elem.find('descricaoMercadoria') is not None and mercadoria_elem.find('descricaoMercadoria').text else "N/A"
                quantidade_str = mercadoria_elem.find('quantidade').text.strip() if mercadoria_elem.find('quantidade') is not None and mercadoria_elem.find('quantidade').text else "0"
                unidade_medida = mercadoria_elem.find('unidadeMedida').text.strip() if mercadoria_elem.find('unidadeMedida') is not None and mercadoria_elem.find('unidadeMedida').text else "N/A"
                valor_unitario_str = mercadoria_elem.find('valorUnitario').text.strip() if mercadoria_elem.find('valorUnitario') is not None and mercadoria_elem.find('valorUnitario').text else "0"
                numero_item = mercadoria_elem.find('numeroSequencialItem').text.strip() if mercadoria_elem.find('numeroSequencialItem') is not None and mercadoria_elem.find('numeroSequencialItem').text else str(item_counter_in_adicao)
                codigo_ncm = adicao.find('dadosMercadoriaCodigoNcm').text.strip() if adicao.find('dadosMercadoriaCodigoNcm') is not None and adicao.find('dadosMercadoriaCodigoNcm').text else "N/A"

                quantidade = float(quantidade_str) / 10**5 if quantidade_str else 0.0
                valor_unitario_fob_usd = float(valor_unitario_str) / 10**7 if valor_unitario_str else 0.0
                valor_item_calculado_fob_brl = quantidade * valor_unitario_fob_usd * taxa_cambial_usd

                sku_item = re.match(r'([A-Z0-9-]+)', descricao).group(1) if re.match(r'([A-Z0-9-]+)', descricao) else "N/A"
                peso_liquido_item = peso_unitario_medio_adicao * quantidade
                custo_unit_di_usd = valor_unitario_fob_usd

                itens_data.append({
                    "id": f"temp_{numero_di}_{numero_adicao}_{numero_item}",
                    "declaracao_id": None,
                    "numero_adicao": numero_adicao,
                    "numero_item_sequencial": numero_item,
                    "descricao_mercadoria": descricao,
                    "quantidade": quantidade,
                    "unidade_medida": unidade_medida,
                    "valor_unitario": valor_unitario_fob_usd,
                    "valor_item_calculado": valor_item_calculado_fob_brl,
                    "peso_liquido_item": peso_liquido_item,
                    "ncm_item": codigo_ncm,
                    "sku_item": sku_item,
                    "custo_unit_di_usd": custo_unit_di_usd,
                    "ii_percent_item": ii_perc_adicao,
                    "ipi_percent_item": ipi_perc_adicao,
                    "pis_percent_item": pis_perc_adicao,
                    "cofins_percent_item": cofins_perc_adicao,
                    "icms_percent_item": icms_perc_adicao,
                    "codigo_erp_item": ""
                })
                item_counter_in_adicao += 1

        return di_data, itens_data

    except ET.ParseError as pe:
        logger.error(f"Erro ao analisar o conteúdo XML: {pe}")
        return None, None
    except Exception as e:
        logger.exception(f"Erro inesperado ao processar o XML: {e}")
        return None, None

def save_parsed_di_data(di_data: Dict[str, Any], itens_data: List[Dict[str, Any]]):
    conn = connect_db(get_db_path("xml_di"))
    if not conn: return False

    try:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO xml_declaracoes (
                numero_di, data_registro, valor_total_reais_xml, arquivo_origem, data_importacao,
                informacao_complementar, vmle, frete, seguro, vmld, ipi, pis_pasep, cofins, icms_sc,
                taxa_cambial_usd, taxa_siscomex, numero_invoice, peso_bruto, peso_liquido,
                cnpj_importador, importador_nome, recinto, embalagem, quantidade_volumes, acrescimo,
                imposto_importacao, armazenagem, frete_nacional
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            di_data.get('numero_di'), di_data.get('data_registro'), di_data.get('vmle'), di_data.get('arquivo_origem'), di_data.get('data_importacao'),
            di_data.get('informacao_complementar'), di_data.get('vmle'), di_data.get('frete'), di_data.get('seguro'), di_data.get('vmld'),
            di_data.get('ipi'), di_data.get('pis_pasep'), di_data.get('cofins'), di_data.get('icms_sc'),
            di_data.get('taxa_cambial_usd'), di_data.get('taxa_siscomex'), di_data.get('numero_invoice'), di_data.get('peso_bruto'), di_data.get('peso_liquido'),
            di_data.get('cnpj_importador'), di_data.get('importador_nome'), di_data.get('recinto'), di_data.get('embalagem'),
            di_data.get('quantidade_volumes'), di_data.get('acrescimo'), di_data.get('imposto_importacao'),
            di_data.get('armazenagem'), di_data.get('frete_nacional')
        ))
        declaracao_id = cursor.lastrowid
        
        itens_a_salvar_tuples = []
        for item in itens_data:
            itens_a_salvar_tuples.append((
                declaracao_id,
                item.get('numero_adicao'), item.get('numero_item_sequencial'), item.get('descricao_mercadoria'),
                item.get('quantidade'), item.get('unidade_medida'), item.get('valor_unitario'),
                item.get('valor_item_calculado'), item.get('peso_liquido_item'), item.get('ncm_item'),
                item.get('sku_item'), item.get('custo_unit_di_usd'), item.get('ii_percent_item'),
                item.get('ipi_percent_item'), item.get('pis_percent_item'), item.get('cofins_percent_item'),
                item.get('icms_percent_item'), item.get('codigo_erp_item')
            ))
        
        if itens_a_salvar_tuples:
            cursor.executemany('''
                INSERT INTO xml_itens (
                    declaracao_id, numero_adicao, numero_item_sequencial, descricao_mercadoria, quantidade, unidade_medida,
                    valor_unitario, valor_item_calculado, peso_liquido_item, ncm_item, sku_item,
                    custo_unit_di_usd, ii_percent_item, ipi_percent_item, pis_percent_item, cofins_percent_item, icms_percent_item,
                    codigo_erp_item
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', itens_a_salvar_tuples)
        
        conn.commit()
        return True

    except sqlite3.IntegrityError as e:
        logger.error(f"Erro de integridade: A DI {di_data.get('numero_di')} já existe. {e}")
        return False
    except Exception as e:
        logger.error(f"Erro ao salvar DI e itens no banco de dados: {e}")
        conn.rollback()
        return False
    finally:
        if conn: conn.close()

def delete_declaracao(declaracao_id: int):
    conn = connect_db(get_db_path("xml_di"))
    if not conn: return False
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM xml_declaracoes WHERE id = ?", (declaracao_id,))
        conn.commit()
        logger.info(f"Declaração ID {declaracao_id} e dados relacionados excluídos com sucesso.")
        return True
    except Exception as e:
        logger.error(f"Erro ao excluir declaração ID {declaracao_id}: {e}")
        conn.rollback()
        return False
    finally:
        if conn: conn.close()

def update_declaracao(declaracao_id: int, di_data: Dict[str, Any]):
    conn = connect_db(get_db_path("xml_di"))
    if not conn: return False
    try:
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE xml_declaracoes
            SET
                numero_di = ?,
                data_registro = ?,
                valor_total_reais_xml = ?,
                arquivo_origem = ?,
                data_importacao = ?,
                informacao_complementar = ?,
                vmle = ?,
                frete = ?,
                seguro = ?,
                vmld = ?,
                ipi = ?,
                pis_pasep = ?,
                cofins = ?,
                icms_sc = ?,
                taxa_cambial_usd = ?,
                taxa_siscomex = ?,
                numero_invoice = ?,
                peso_bruto = ?,
                peso_liquido = ?,
                cnpj_importador = ?,
                importador_nome = ?,
                recinto = ?,
                embalagem = ?,
                quantidade_volumes = ?,
                acrescimo = ?,
                imposto_importacao = ?,
                armazenagem = ?,
                frete_nacional = ?
            WHERE id = ?
        ''', (
            di_data.get('numero_di'), di_data.get('data_registro'), di_data.get('valor_total_reais_xml'),
            di_data.get('arquivo_origem'), di_data.get('data_importacao'), di_data.get('informacao_complementar'),
            di_data.get('vmle'), di_data.get('frete'), di_data.get('seguro'), di_data.get('vmld'),
            di_data.get('ipi'), di_data.get('pis_pasep'), di_data.get('cofins'), di_data.get('icms_sc'),
            di_data.get('taxa_cambial_usd'), di_data.get('taxa_siscomex'), di_data.get('numero_invoice'),
            di_data.get('peso_bruto'), di_data.get('peso_liquido'), di_data.get('cnpj_importador'),
            di_data.get('importador_nome'), di_data.get('recinto'), di_data.get('embalagem'),
            di_data.get('quantidade_volumes'), di_data.get('acrescimo'), di_data.get('imposto_importacao'),
            di_data.get('armazenagem'), di_data.get('frete_nacional'),
            declaracao_id
        ))
        conn.commit()
        logger.info(f"Declaração ID {declaracao_id} atualizada com sucesso.")
        return True
    except Exception as e:
        logger.error(f"Erro ao atualizar declaração ID {declaracao_id}: {e}")
        conn.rollback()
        return False
    finally:
        if conn: conn.close()

def inserir_ou_atualizar_produto(db_path: str, produto: Tuple[str, str, str, str]):
    conn = connect_db(db_path)
    if not conn: return False
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id_key_erp FROM produtos WHERE id_key_erp = ?", (produto[0],))
        if cursor.fetchone():
            cursor.execute('''
                UPDATE produtos
                SET nome_part = ?, descricao = ?, ncm = ?
                WHERE id_key_erp = ?
            ''', (produto[1], produto[2], produto[3], produto[0]))
            logger.info(f"Produto com ID/Key ERP '{produto[0]}' atualizado com sucesso.")
        else:
            cursor.execute('''
                INSERT INTO produtos (id_key_erp, nome_part, descricao, ncm)
                VALUES (?, ?, ?, ?)
            ''', produto)
            logger.info(f"Novo produto com ID/Key ERP '{produto[0]}' inserido com sucesso.")
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Erro ao inserir/atualizar produto com ID/Key ERP '{produto[0]}': {e}")
        conn.rollback()
        return False
    finally:
        if conn: conn.close()

def selecionar_todos_produtos(db_path: str):
    conn = connect_db(db_path)
    if not conn: return []
    try:
        cursor = conn.cursor()
        # Use col_ids diretamente se necessário, ou fetch all e mapeie
        cursor.execute("SELECT id_key_erp, nome_part, descricao, ncm FROM produtos ORDER BY nome_part ASC")
        return cursor.fetchall()
    except Exception as e:
        logger.error(f"Erro ao buscar todos os produtos: {e}")
        return []
    finally:
        if conn: conn.close()

def selecionar_produto_por_id(db_path: str, id_key_erp: str):
    conn = connect_db(db_path)
    if not conn: return None
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id_key_erp, nome_part, descricao, ncm FROM produtos WHERE id_key_erp = ?", (id_key_erp,))
        return cursor.fetchone()
    except Exception as e:
        logger.error(f"Erro ao buscar produto com ID/Key ERP '{id_key_erp}': {e}")
        return None
    finally:
        if conn: conn.close()

def selecionar_produtos_por_ids(db_path: str, ids: List[str]):
    if not ids: return []
    conn = connect_db(db_path)
    if not conn: return []
    try:
        cursor = conn.cursor()
        placeholders = ', '.join('?' * len(ids))
        query = f"SELECT id_key_erp, nome_part, descricao, ncm FROM produtos WHERE id_key_erp IN ({placeholders}) ORDER BY INSTR(',{','.join(ids)},', ',' || id_key_erp || ',')"
        cursor.execute(query, tuple(ids))
        # Reordena explicitamente para garantir a ordem da lista 'ids'
        produtos_dict = {p['id_key_erp']: p for p in cursor.fetchall()}
        produtos_ordenados = [produtos_dict[id] for id in ids if id in produtos_dict]
        return produtos_ordenados
    except Exception as e:
        logger.error(f"Erro ao buscar produtos por IDs: {e}")
        return []
    finally:
        if conn: conn.close()

def deletar_produto(db_path: str, id_key_erp: str):
    conn = connect_db(db_path)
    if not conn: return False
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM produtos WHERE id_key_erp = ?", (id_key_erp,))
        conn.commit()
        if cursor.rowcount > 0:
            logger.info(f"Produto com ID/Key ERP '{id_key_erp}' excluído com sucesso.")
            return True
        else:
            logger.warning(f"Produto com ID/Key ERP '{id_key_erp}' não encontrado para exclusão.")
            return False
    except Exception as e:
        logger.error(f"Erro ao excluir produto com ID/Key ERP '{id_key_erp}': {e}")
        conn.rollback()
        return False
    finally:
        if conn: conn.close()
