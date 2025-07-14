# Funções utilitárias para conversão e validação segura de dados
import streamlit as st
from datetime import datetime

def safe_float(value, default=0.0):
    try:
        if value is None or value == '':
            return default
        return float(str(value).replace(',', '.'))
    except Exception:
        return default

def safe_int(value, default=0):
    try:
        if value is None or value == '':
            return default
        return int(float(str(value).replace(',', '.')))
    except Exception:
        return default

def safe_date(value, fmt='%Y-%m-%d', default=None):
    try:
        if not value:
            return default
        if isinstance(value, datetime):
            return value
        return datetime.strptime(value, fmt)
    except Exception:
        return default

def validate_required_fields(data: dict, required_fields: list):
    missing = [field for field in required_fields if not data.get(field)]
    if missing:
        st.error(f'Campos obrigatórios não preenchidos: {", ".join(missing)}')
        return False
    return True
