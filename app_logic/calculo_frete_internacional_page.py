import streamlit as st
import os
import base64
from datetime import datetime
import logging
import streamlit.components.v1 as components # Importar components para HTML/JS

# Importar funções de utilidade do módulo utils
from app_logic.utils import set_background_image, get_dolar_cotacao

logger = logging.getLogger(__name__)

# --- Função para formatar moeda ---
def _format_currency(value, prefix="R$ "):
    """
    Formata um valor numérico para o formato de moeda, trocando '.' por ','.
    Adiciona 4 casas decimais para valores monetários e um prefixo padrão.
    """
    try:
        # Tenta converter para float. Se 'N/A' ou similar, tratar como 0.0
        val = float(str(value).replace(',', '.')) if isinstance(value, str) else float(value)
        # Formata com 4 casas decimais, troca ponto por hash, depois hash por vírgula para PT-BR
        return f"{prefix}{val:,.2f}".replace('.', '#').replace(',', '.').replace('#', ',')
    except (ValueError, TypeError):
        return f"{prefix}0,0000"

# --- Função de callback para limpar os campos Aéreo ---
def _clear_aereo_fields():
    """
    Reseta os valores dos campos relacionados ao frete aéreo no session_state.
    """
    st.session_state.taxa_awb_aereo = 0.0
    st.session_state.dta_aereo = 0.0
    st.session_state.agency_fee_aereo = 150.0
    st.session_state.chd_aereo = 40.0
    st.session_state.total_comparacao_aereo = 0.0

# --- Função para copiar texto para a área de transferência usando JavaScript ---
def _copy_to_clipboard(text_to_copy, button_key):
    """
    Copia o texto fornecido para a área de transferência do usuário.
    Usa um hack com st.components.v1.html para executar JavaScript no navegador.
    """
    js_code = f"""
    <script>
        var text = `{text_to_copy}`;
        var textArea = document.createElement("textarea");
        textArea.value = text;
        document.body.appendChild(textArea);
        textArea.select();
        try {{
            document.execCommand('copy');
            alert('Conteúdo copiado!');
        }} catch (err) {{
            alert('Não foi possível copiar: ' + err);
        }}
        document.body.removeChild(textArea);
    </script>
    """
    components.html(js_code, height=0, width=0) # height e width 0 para não ocupar espaço

# --- Função para obter a saudação conforme o horário ---
def _get_greeting():
    """
    Retorna uma saudação apropriada baseada na hora atual.
    """
    current_hour = datetime.now().hour
    if 6 <= current_hour < 12:
        return "Bom dia"
    elif 12 <= current_hour < 18:
        return "Boa tarde"
    else:
        return "Boa noite"

def show_calculo_frete_internacional_page():
    """
    Exibe a página de cálculo de Frete Internacional, com opções para Aéreo e Marítimo.
    """
    # Define o caminho da imagem de fundo
    background_image_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'assets', 'logo_navio_atracado.png')
    set_background_image(background_image_path)

    st.subheader("Cálculo Frete Internacional")

    # Fetch dollar rates
    dolar_data = get_dolar_cotacao()
    
    # Cotações para exibição geral e cálculo Marítimo (PTAX Venda)
    dolar_venda_ptax = 0.0
    dolar_ptax_3_percent = 0.0
    if dolar_data and dolar_data['ptax_venda'] != 'N/A':
        try:
            dolar_venda_ptax = float(dolar_data['ptax_venda'].replace(',', '.'))
            dolar_ptax_3_percent = dolar_venda_ptax * 1.03
        except ValueError:
            st.warning("Não foi possível converter a cotação PTAX do dólar para cálculo. Usando 0.0.")
    
    # Cotações para cálculo Aéreo (Abertura Venda)
    dolar_venda_abertura = 0.0
    dolar_abertura_3_percent = 0.0
    if dolar_data and dolar_data['abertura_venda'] != 'N/A':
        try:
            dolar_venda_abertura = float(dolar_data['abertura_venda'].replace(',', '.'))
            dolar_abertura_3_percent = dolar_venda_abertura * 1.03
        except ValueError:
            st.warning("Não foi possível converter a cotação de Abertura do dólar para cálculo. Usando 0.0.")

    # Exibir cotações do dólar no topo (APENAS ABERTURA)
    st.markdown("#### Cotação do Dólar para Cálculos")
    col_dv_abertura, col_dv3_abertura = st.columns(2)
    with col_dv_abertura:
        st.metric(label="Dólar Venda (Abertura)", 
              value=f"{dolar_venda_abertura:,.4f}".replace('.', '#').replace(',', '.').replace('#', ','))
    with col_dv3_abertura:
        st.metric(label="Dólar + 3% (Abertura)", 
              value=f"{dolar_abertura_3_percent:,.4f}".replace('.', '#').replace(',', '.').replace('#', ','))
    st.markdown("---")

    # Campo de referência PCH-*****
    # Pré-preencher o campo de referência
    if 'referencia_pch' not in st.session_state:
        st.session_state.referencia_pch = "PCH-"
    col1, col2 = st.columns([1, 3])  # Proporção 1:2
    with col1:
        st.text_input(
        "Referência (Ex: PCH-*****)", 
        key="referencia_pch", 
        value=st.session_state.referencia_pch,
        
    )


    # Select box for freight type
    col1, col2 = st.columns([1, 3])  # Proporção 1:2
    with col1:
        frete_type = st.selectbox(
        "Selecione o Tipo de Frete",
        ("Aéreo", "Marítimo"),
        key="frete_type_select"
    )

    if frete_type == "Aéreo":
        st.markdown("##### Detalhes do Frete Aéreo")
        
        # Inicializa valores no session state se ainda não existirem, com valores padrão
        if 'taxa_awb_aereo' not in st.session_state:
            st.session_state.taxa_awb_aereo = 0.0
        if 'dta_aereo' not in st.session_state:
            st.session_state.dta_aereo = 0.0
        if 'agency_fee_aereo' not in st.session_state:
            st.session_state.agency_fee_aereo = 150.0 # Pré-preenchido
        if 'chd_aereo' not in st.session_state:
            st.session_state.chd_aereo = 40.0 # Pré-preenchido
        # IOF não precisa ser inicializado como input, pois é calculado
        if 'total_comparacao_aereo' not in st.session_state:
            st.session_state.total_comparacao_aereo = 0.0

        # LAYOUT: Detalhes do Frete Aéreo (esquerda) e Resumo do Cálculo Aéreo (direita)
        col_details_aereo,col2 ,col_summary_aereo = st.columns([0.2,0.2, 0.6]) # Ajustado o ratio

        with col_details_aereo:
            st.markdown("###### Custos (USD)")
            st.number_input(
                "Taxa AWB ($)", 
                min_value=0.0, 
                format="%.2f", 
                key="taxa_awb_aereo", 
                value=st.session_state.taxa_awb_aereo,
            )
            st.number_input(
                "DTA ($)", 
                min_value=0.0, 
                format="%.2f", 
                key="dta_aereo", 
                value=st.session_state.dta_aereo,
            )
            st.number_input(
                "CHD ($)", 
                min_value=0.0, 
                format="%.2f", 
                key="chd_aereo", 
                value=st.session_state.chd_aereo,
            )
            iof_aereo_calculated = st.session_state.taxa_awb_aereo * 0.035
            

            st.markdown("###### Outros Custos (R$)")
            st.number_input(
                "Agency Fee (R$)", 
                min_value=0.0, 
                format="%.2f", 
                key="agency_fee_aereo", 
                value=st.session_state.agency_fee_aereo,
            )
            st.markdown("###### Total para Comparação (R$)")
            # AJUSTE: Renomear "Total Referência (R$)" para "DIFERENÇA (R$)"
            st.number_input(
                "DIFERENÇA (R$)", 
                 
                format="%.2f", 
                key="total_comparacao_aereo", # Este key agora representa a 'diferença' para comparação
                value=st.session_state.total_comparacao_aereo,
            )
           
        with col_summary_aereo:
            st.markdown("##### Resumo do Cálculo Aéreo")
            
            # Cálculos para Aéreo
            taxa_awb_brl = st.session_state.taxa_awb_aereo * dolar_abertura_3_percent
            dta_brl = st.session_state.dta_aereo * dolar_abertura_3_percent
            chd_brl = st.session_state.chd_aereo * dolar_abertura_3_percent
            iof_brl = iof_aereo_calculated * dolar_abertura_3_percent

            total_aereo_brl_calculated = (taxa_awb_brl + dta_brl + iof_brl + chd_brl) + st.session_state.agency_fee_aereo
            
            diferenca_aereo = total_aereo_brl_calculated - st.session_state.total_comparacao_aereo

            # Exibir valores calculados (AGORA EM DÓLAR, exceto Agency Fee e Totais Finais)
            st.write(f"**Dólar + 3%:** {_format_currency(dolar_abertura_3_percent, prefix='$ ')}")
            st.write(f"Taxa AWB : {_format_currency(st.session_state.taxa_awb_aereo, prefix='$ ')}")
            st.write(f"DTA : {_format_currency(st.session_state.dta_aereo, prefix='$ ')}")
            st.write(f"CHD : {_format_currency(st.session_state.chd_aereo, prefix='$ ')}")
            st.write(f"IOF : {_format_currency(iof_aereo_calculated, prefix='$ ')}")
            st.write(f"Agency Fee (R$) : {_format_currency(st.session_state.agency_fee_aereo, prefix='R$ ')}")

            st.markdown("---")
            
            # AJUSTE: Renomear "DIFERENÇA (R$)" para "TOTAL (R$)"
            st.metric(label="TOTAL (R$)", value=_format_currency(diferenca_aereo, prefix="R$ "))

            col_buttons_aereo = st.columns(2)
            with col_buttons_aereo[0]:
                # Usa a função de callback _clear_aereo_fields para resetar os valores
                st.button("LIMPAR Aéreo", key="clear_aereo", on_click=_clear_aereo_fields)

            # Controlar a abertura do expander
            if 'email_expander_open' not in st.session_state:
                st.session_state.email_expander_open = False

            with col_buttons_aereo[1]:
                if st.button("Enviar Frete Internacional Aéreo", key="send_aereo"):
                    st.session_state.email_expander_open = True
                    st.rerun() # Necessário para abrir o expander imediatamente
        
            # Expander para copiar o conteúdo do e-mail
            # Usar st.session_state.email_expander_open para controlar o estado do expander
            with st.expander("Conteúdo do E-mail", expanded=st.session_state.email_expander_open):
                
                
                # Assunto do E-mail
                referencia_digitada = st.session_state.get('referencia_pch', 'PCH-XXXXX-XX')
                email_subject_content = f"{referencia_digitada} - Pagamento de frete internacional Ethima"
                email_subject = st.text_area("Assunto do E-mail", value=email_subject_content, height=70, key="email_subject_aereo") 
                if st.button("Copiar Assunto", key="copy_subject_aereo"):
                    _copy_to_clipboard(email_subject, "copy_subject_aereo_js")

                

                # Corpo do E-mail
                saudacao = _get_greeting()
                # Obter o nome do usuário logado
                usuario_sistema = st.session_state.get('user_info', {}).get('username', 'Usuário do Sistema')

                email_body_content = f"""
{saudacao} Mayra,

Gentileza realizar depósito para a Ethima Logistics:
Processo: {referencia_digitada}
Valor total a depositar: {_format_currency(total_aereo_brl_calculated, prefix='R$ ')}
Serviço: Frete e taxas de embarque Aéreo.

Chave PIX: financeiro@ethima.com.br
Favorecido: Ethima Comercio Exterior LTDA
Banco: Itaú Unibanco S.A. - 341
Agência: 8262
Conta: 41461-1
CNPJ: 21.129.987/0001-19

Conforme instruções em anexo.
Obs.: Invoice da importação em anexo.

Esta cobrança é válida para pagamento hoje, devido à taxa de conversão diária. Caso esta cobrança não seja paga nesta data, gentileza
solicitar ao nosso setor financeiro taxa cambial atualizada na data do pagamento.

Obrigado(a),
{usuario_sistema}
                """
                
                email_body = st.text_area("Corpo do E-mail", value=email_body_content, height=300, key="email_body_aereo")
                
                btn_copy, btn_exit = st.columns(2)
                                    
                with btn_copy:
                    if st.button("Copiar Corpo", key="copy_body_aereo"):
                        _copy_to_clipboard(email_body, "copy_body_aereo_js")
                        
                        
                with btn_exit:
                    if st.button("Fechar E-mail", key="close_expander_aereo"):
                        st.session_state.email_expander_open = False
                        st.rerun() # Necessário para fechar o expander imediatamente       
                    

    elif frete_type == "Marítimo":
        st.markdown("##### Detalhes do Frete Marítimo")

        # Inicializa valores no session state se ainda não existirem
        if 'frete_bl_maritimo' not in st.session_state:
            st.session_state.frete_bl_maritimo = 0.0
        if 'thc_maritimo' not in st.session_state:
            st.session_state.thc_maritimo = 0.0
        if 'taxas_destino_dolar_maritimo' not in st.session_state:
            st.session_state.taxas_destino_dolar_maritimo = 0.0
        if 'taxas_destino_real_maritimo' not in st.session_state:
            st.session_state.taxas_destino_real_maritimo = 0.0
        if 'iof_maritimo' not in st.session_state:
            st.session_state.iof_maritimo = 0.0
        if 'agency_fee_maritimo' not in st.session_state:
            st.session_state.agency_fee_maritimo = 0.0

        col_bl_thc, col_taxas = st.columns(2)
        
        with col_bl_thc:
            st.markdown("###### Custos Principais (USD)")
            st.number_input("Frete BL ($)", min_value=0.0, format="%.4f", key="frete_bl_maritimo", value=st.session_state.frete_bl_maritimo, on_change=st.rerun)
            st.number_input("THC ($)", min_value=0.0, format="%.4f", key="thc_maritimo", value=st.session_state.thc_maritimo, on_change=st.rerun)

        with col_taxas:
            st.markdown("###### Taxas de Destino")
            st.number_input("Taxas Destino Dólar ($)", min_value=0.0, format="%.4f", key="taxas_destino_dolar_maritimo", value=st.session_state.taxas_destino_dolar_maritimo, on_change=st.rerun)
            st.number_input("Taxas Destino Real (R$)", min_value=0.0, format="%.2f", key="taxas_destino_real_maritimo", value=st.session_state.taxas_destino_real_maritimo, on_change=st.rerun)
            st.number_input("IOF ($)", min_value=0.0, format="%.4f", key="iof_maritimo", value=st.session_state.iof_maritimo, on_change=st.rerun)
            st.number_input("Agency Fee (R$)", min_value=0.0, format="%.2f", key="agency_fee_maritimo", value=st.session_state.agency_fee_maritimo, on_change=st.rerun)
        
        st.markdown("---")
        st.markdown("##### Resumo do Cálculo Marítimo")

        # Calculations for Marítimo - Valores lidos diretamente do st.session_state
        frete_bl_brl = st.session_state.frete_bl_maritimo * dolar_ptax_3_percent
        thc_brl = st.session_state.thc_maritimo * dolar_ptax_3_percent
        taxas_destino_dolar_brl = st.session_state.taxas_destino_dolar_maritimo * dolar_ptax_3_percent
        iof_maritimo_brl = st.session_state.iof_maritimo * dolar_ptax_3_percent

        total_maritimo_brl_calculated = frete_bl_brl + thc_brl + taxas_destino_dolar_brl + st.session_state.taxas_destino_real_maritimo + iof_maritimo_brl + st.session_state.agency_fee_maritimo

        # Displaying calculated values and inputs in a table-like format
        col_calc_maritimo_display_1, col_calc_maritimo_display_2 = st.columns([0.4, 0.6])

        with col_calc_maritimo_display_1:
            st.write(f"**Dólar + 3% (PTAX):**")
            st.write(f"**Frete BL ($):**")
            st.write(f"**THC ($):**")
            st.write(f"**Taxas Destino Dólar ($):**")
            st.write(f"**Taxas Destino Real (R$):**")
            st.write(f"**IOF ($):**")
            st.write(f"**Agency Fee (R$):**")

        with col_calc_maritimo_display_2:
            st.write(_format_currency(dolar_ptax_3_percent, prefix="$ "))
            st.write(_format_currency(st.session_state.frete_bl_maritimo, prefix="$ "))
            st.write(_format_currency(st.session_state.thc_maritimo, prefix="$ "))
            st.write(_format_currency(st.session_state.taxas_destino_dolar_maritimo, prefix="$ "))
            st.write(_format_currency(st.session_state.taxas_destino_real_maritimo, prefix="R$ "))
            st.write(_format_currency(st.session_state.iof_maritimo, prefix="$ "))
            st.write(_format_currency(st.session_state.agency_fee_maritimo, prefix="R$ "))

        st.markdown("---")
        st.metric(label="TOTAL (R$)", value=_format_currency(total_maritimo_brl_calculated, prefix="R$ "))

        col_buttons_maritimo = st.columns(2)
        with col_buttons_maritimo[0]:
            if st.button("LIMPAR Marítimo", key="clear_maritimo"):
                # Resetando os valores no session_state para limpar
                st.session_state.frete_bl_maritimo = 0.0
                st.session_state.thc_maritimo = 0.0
                st.session_state.taxas_destino_dolar_maritimo = 0.0
                st.session_state.taxas_destino_real_maritimo = 0.0
                st.session_state.iof_maritimo = 0.0
                st.session_state.agency_fee_maritimo = 0.0
                st.rerun() # Rerun to clear values

        with col_buttons_maritimo[1]:
            st.button("Enviar Frete Internacional Marítimo", key="send_maritimo")

    st.markdown("---")
    st.write("Esta tela permite calcular os custos de frete internacional (aéreo ou marítimo).")
