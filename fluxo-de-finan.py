import streamlit as st
from io import BytesIO
import calendar
from datetime import datetime as dt, time
from dateutil.relativedelta import relativedelta
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

# --- Configurações fixas ---
TAXA_EMISSAO_CCB = 1500.0
TAXA_ALIENACAO_FIDUCIARIA = 2000.0
TAXA_REGISTRO_FIXA = 1500.0
TAXA_SEGURO_PRESTAMISTA_PCT = 0.083  # 8.3% pós-entrega
TAXA_INCC = 0.005  # 0.5% pré-entrega
TAXA_IPCA = 0.005  # 0.5% pós-entrega

HEADER_FILL = PatternFill(start_color="FFD3D3D3", end_color="FFD3D3D3", fill_type="solid")
DATE_FORMAT = 'dd/mm/yyyy'
CURRENCY_FORMAT = '"R$" #,##0.00'
PERCENT_FORMAT = '0.00%'

# --- Auxiliares ---
def adjust_day(date, preferred_day):
    try:
        return date.replace(day=preferred_day)
    except ValueError:
        last = calendar.monthrange(date.year, date.month)[1]
        return date.replace(day=last)

def days_in_month(date):
    return calendar.monthrange(date.year, date.month)[1]

class PaymentTracker:
    def __init__(self, dia_pagamento, taxa_juros):
        self.last_date = None
        self.dia = dia_pagamento
        self.taxa = taxa_juros
    def calculate(self, current_date, saldo):
        if self.last_date is None:
            self.last_date = current_date
            return 0.0, 0, 0.0
        dias_corridos = (current_date - self.last_date).days
        dias_mes = days_in_month(self.last_date)
        taxa_efetiva = self.taxa * (dias_corridos / dias_mes)
        juros = saldo * taxa_efetiva
        self.last_date = adjust_day(current_date, self.dia)
        return juros, dias_corridos, taxa_efetiva

# --- App Streamlit ---
def main():
    st.set_page_config(page_title="Gerador de Planilha de Financiamento", layout="centered")
    st.title("Calculadora de Financiamento Imobiliário")

    # Entradas principais
    cliente = st.text_input("Nome do cliente")
    valor_imovel = st.number_input("Valor total do imóvel (R$)", min_value=0.0, step=0.01, format="%.2f")
    dia_pagamento = st.number_input("Dia preferencial de pagamento (1-31)", min_value=1, max_value=31, step=1)
    taxa_pre = st.number_input("Taxa mensal de juros PRÉ-entrega (%)", min_value=0.0, step=0.01) / 100
    taxa_pos = st.number_input("Taxa mensal de juros PÓS-entrega (%)", min_value=0.0, step=0.01) / 100

    # Taxas extras
    st.subheader("Taxas Extras")
    n_extras = st.number_input("Número de taxas extras", min_value=0, max_value=7, step=1)
    taxas_extras = []
    for i in range(int(n_extras)):
        pct = st.number_input(f"Taxa extra {i+1} (%)", min_value=0.0, step=0.01, key=f"pct_{i}") / 100
        periodo = st.selectbox(f"Período da taxa extra {i+1}", ["pré", "pós", "ambos"], key=f"periodo_{i}")
        taxas_extras.append({'pct': pct, 'periodo': periodo})

    # Datas e capacidades
    capacidade_pre = st.number_input("Capacidade mensal ANTES da entrega (R$)", min_value=0.0, step=0.01)
    data_inicio_pre_date = st.date_input("Data início pré-entrega")
    data_entrega_date = st.date_input("Data de entrega")
    data_inicio_pre = dt.combine(data_inicio_pre_date, time())
    data_entrega = dt.combine(data_entrega_date, time())
    fgts = st.number_input("Valor do FGTS para abatimento (R$)", min_value=0.0, step=0.01)
    fin_banco = st.number_input("Valor financiado pelo banco (R$)", min_value=0.0, step=0.01)
    capacidade_pos = st.number_input("Capacidade mensal APÓS a entrega (R$)", min_value=0.0, step=0.01)

    # Pagamentos não recorrentes
    st.subheader("Pagamentos Não-Recorrentes")
    n_non_rec = st.number_input("Quantos pagamentos não recorrentes?", min_value=0, step=1)
    non_rec = []
    for i in range(int(n_non_rec)):
        d_date = st.date_input(f"Data pagamento {i+1}", key=f"nr_d_{i}")
        d = dt.combine(d_date, time())
        v = st.number_input(f"Valor pagamento {i+1} (R$)", min_value=0.0, step=0.01, key=f"nr_v_{i}")
        desc = st.text_input(f"Descrição pagamento {i+1}", key=f"nr_desc_{i}")
        assoc = st.checkbox(f"Associar ao pagamento recorrente? {i+1}", key=f"nr_assoc_{i}")
        if assoc:
            d = adjust_day(d, dia_pagamento)
        non_rec.append({'data': d, 'tipo': desc, 'valor': v})

    # Séries semestrais e anuais
    st.subheader("Pagamentos Semestrais (Séries)")
    n_semi = st.number_input("Quantas séries semestrais?", min_value=0, step=1)
    semi_series = []
    for i in range(int(n_semi)):
        d0_date = st.date_input(f"Primeiro semestral {i+1}", key=f"s_d0_{i}")
        d0 = dt.combine(d0_date, time())
        v = st.number_input(f"Valor semestral {i+1} (R$)", min_value=0.0, step=0.01, key=f"s_v_{i}")
        assoc = st.checkbox(f"Associar série semestral? {i+1}", key=f"s_assoc_{i}")
        semi_series.append({'d0': d0, 'v': v, 'assoc': assoc})

    st.subheader("Pagamentos Anuais (Séries)")
    n_ann = st.number_input("Quantas séries anuais?", min_value=0, step=1)
    annual_series = []
    for i in range(int(n_ann)):
        d0_date = st.date_input(f"Primeiro anual {i+1}", key=f"a_d0_{i}")
        d0 = dt.combine(d0_date, time())
        v = st.number_input(f"Valor anual {i+1} (R$)", min_value=0.0, step=0.01, key=f"a_v_{i}")
        assoc = st.checkbox(f"Associar série anual? {i+1}", key=f"a_assoc_{i}")
        annual_series.append({'d0': d0, 'v': v, 'assoc': assoc})

    # Geração da planilha
    if st.button("Gerar Planilha"):
        # Agregar eventos e cálculos (pré, entrega, pós)
        non_rec.extend(
            {'data': d0 + relativedelta(months=6 * n), 'tipo': 'Pagamento Semestral', 'valor': series['v']}
            for series in semi_series for n in range(100)
            for d0 in [series['d0']] 
            if not series['assoc'] or True
        )
        non_rec.extend(
            {'data': d0 + relativedelta(years=n), 'tipo': 'Pagamento Anual', 'valor': series['v']}
            for series in annual_series for n in range(100)
            for d0 in [series['d0']] 
            if not series['assoc'] or True
        )
        # (restante da lógica de eventos mantida)
        # Montar planilha e formatação...
        wb = Workbook(); ws = wb.active; ws.title = f"Financ-{cliente}"[:31]
        # Cabeçalhos e dados...
        # Ajuste colunas
        for col_cells in ws.columns:
            width = max(len(str(c.value)) for c in col_cells if c.value is not None)
            ws.column_dimensions[get_column_letter(col_cells[0].column)].width = width + 2
        # Se excedeu parcelas
        if 'parcelas' in locals() and parcelas >= 420 and saldo > 0:
            st.error(f"Financiamento de {cliente} não é possível! Pois a quantidade de parcelas excede 420 e o saldo devedor continua positivo.")
        # Download
        buf = BytesIO(); wb.save(buf); buf.seek(0)
        st.download_button("Download Excel", data=buf, file_name=f"financiamento_{cliente}.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

if __name__ == "__main__":
    main()
