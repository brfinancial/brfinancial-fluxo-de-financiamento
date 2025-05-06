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
    st.title("Bem-vindo ao gerador de financiamento da Br Financial!")

    # Entradas principais
    cliente = st.text_input("tQual o nome do cliente?")
    valor_imovel = st.number_input("Qual o valor total do imóvel (R$)", min_value=0.0, step=0.01, format="%.2f")
    dia_pagamento = st.number_input("Qual o dia preferencial de pagamento das parcelas mensais? (1-31)", min_value=1, max_value=31, step=1)
    taxa_pre = st.number_input("Taxa mensal de juros ANTES da entrega das chaves (%)", min_value=0.0, step=0.01) / 100
    taxa_pos = st.number_input("Taxa mensal de juros DEPOIS da entrega das chaves (%)", min_value=0.0, step=0.01) / 100

    # Taxas extras
    st.subheader("Taxas Extras")
    n_extras = st.number_input("Quantas taxas quer incluir nas parcelas? (Caso não tenha taxas extras, deixe em branco)", min_value=0, max_value=7, step=1)
    taxas_extras = []
    for i in range(int(n_extras)):
        pct = st.number_input(f"Taxa extra {i+1} (%)", min_value=0.0, step=0.01, key=f"pct_{i}") / 100
        periodo = st.selectbox(f"Período da taxa extra {i+1}", ["pré-entrega da chave", "pós-entrega da chave", "ambos"], key=f"periodo_{i}")
        taxas_extras.append({'pct': pct, 'periodo': periodo})

    # Datas e capacidades
    capacidade_pre = st.number_input("Qual a capacidade de pagamento do cliente nas parcelas mensais ANTES da entrega das chaves? (R$)", min_value=0.0, step=0.01)
    data_inicio_pre_date = st.date_input("Data início dos pagamentos mensais pré-entrega")
    data_entrega_date = st.date_input("Data de ENTREGA das chaves")
    data_inicio_pre = dt.combine(data_inicio_pre_date, time())
    data_entrega = dt.combine(data_entrega_date, time())
    fgts = st.number_input("Valor do FGTS para abatimento do saldo devedor (R$)", min_value=0.0, step=0.01)
    fin_banco = st.number_input("Valor financiado pelo banco (abatimento no saldo devedor) (R$)", min_value=0.0, step=0.01)
    capacidade_pos = st.number_input("Qual a capacidade de pagamento do cliente nas parcelas mensais DEPOIS da entrega das chaves? (R$)", min_value=0.0, step=0.01)

    # Pagamentos não recorrentes
    st.subheader("Pagamentos Não-Recorrentes")
    n_non_rec = st.number_input("Quantos pagamentos não recorrentes terão? (Caso não haja, deixe zerado)", min_value=0, step=1)
    non_rec = []
    for i in range(int(n_non_rec)):
        d_date = st.date_input(f"Data do pagamento {i+1}", key=f"nr_d_{i}")
        d = dt.combine(d_date, time())
        v = st.number_input(f"Valor pagamento {i+1} (R$)", min_value=0.0, step=0.01, key=f"nr_v_{i}")
        desc = st.text_input(f"Descrição do pagamento {i+1}", key=f"nr_desc_{i}")
        assoc = st.checkbox(f"Atribuir a parcela mais próxima? {i+1}", key=f"nr_assoc_{i}")
        if assoc:
            d = adjust_day(d, dia_pagamento)
        non_rec.append({'data': d, 'tipo': desc, 'valor': v})

    # Séries semestrais e anuais
    st.subheader("Pagamentos Semestrais Recorrentes")
    n_semi = st.number_input("Quantos pagamentos recorrentes semestrais terão? (Caso não haja, deixe zerado)", min_value=0, step=1)
    semi_series = []
    for i in range(int(n_semi)):
        d0_date = st.date_input(f"Data das parcelas semestrais {i+1}", key=f"s_d0_{i}")
        d0 = dt.combine(d0_date, time())
        v = st.number_input(f"Valor da parcela semestral {i+1} (R$)", min_value=0.0, step=0.01, key=f"s_v_{i}")
        assoc = st.checkbox(f"Atribuir a parcela mais próxima? {i+1}", key=f"s_assoc_{i}")
        semi_series.append({'d0': d0, 'v': v, 'assoc': assoc})

    st.subheader("Pagamentos Anuais Recorrentes")
    n_ann = st.number_input("Quantos pagamentos recorrentes anuais terão? (Caso não haja, deixe zerado)", min_value=0, step=1)
    annual_series = []
    for i in range(int(n_ann)):
        d0_date = st.date_input(f"Data das parcelas anuais {i+1}", key=f"a_d0_{i}")
        d0 = dt.combine(d0_date, time())
        v = st.number_input(f"Valor da parcela anual {i+1} (R$)", min_value=0.0, step=0.01, key=f"a_v_{i}")
        assoc = st.checkbox(f"Atribuir a parcela mais próxima? {i+1}", key=f"a_assoc_{i}")
        annual_series.append({'d0': d0, 'v': v, 'assoc': assoc})

    # Geração da planilha
    if st.button("Gerar Planilha"):
        # Eventos agregados
        for series in semi_series:
            for n in range(100):
                d = series['d0'] + relativedelta(months=6 * n)
                if series['assoc']:
                    d = adjust_day(d, dia_pagamento)
                non_rec.append({'data': d, 'tipo': 'Pagamento Semestral', 'valor': series['v']})
        for series in annual_series:
            for n in range(100):
                d = series['d0'] + relativedelta(years=n)
                if series['assoc']:
                    d = adjust_day(d, dia_pagamento)
                non_rec.append({'data': d, 'tipo': 'Pagamento Anual', 'valor': series['v']})
        # Separar pré e pós
        pre_nr = sorted([e for e in non_rec if e['data'] < data_entrega], key=lambda x: x['data'])
        post_nr = sorted([e for e in non_rec if e['data'] >= data_entrega], key=lambda x: x['data'])
        eventos = []
        saldo = valor_imovel
        tracker_pre = PaymentTracker(dia_pagamento, taxa_pre)
        tracker_pos = PaymentTracker(dia_pagamento, taxa_pos)
        # 1) PRÉ-ENTREGA
        cursor = data_inicio_pre
        idx_nr = 0
        while True:
            d_evt = adjust_day(cursor, dia_pagamento)
            if d_evt >= data_entrega:
                break
            if idx_nr < len(pre_nr) and pre_nr[idx_nr]['data'] == d_evt:
                ev = pre_nr[idx_nr]; idx_nr += 1
            else:
                ev = {'data': d_evt, 'tipo': 'Pré-Entrega', 'valor': capacidade_pre}
            juros, dias_corr, taxa_eff = tracker_pre.calculate(ev['data'], saldo)
            incc = saldo * TAXA_INCC; ipca = 0.0
            extras = [saldo * t['pct'] if t['periodo'] in ['pré','ambos'] else 0.0 for t in taxas_extras]
            total_taxas = sum(extras) + incc + ipca
            abatimento = ev['valor'] - juros - total_taxas; saldo -= abatimento
            eventos.append({**ev, 'juros': juros, 'dias_corridos': dias_corr, 'taxa_efetiva': taxa_eff,
                            'incc': incc, 'ipca': ipca, 'taxas_extra': extras, 'abatimento': abatimento, 'saldo': saldo})
            cursor += relativedelta(months=1)
        # 2) ENTREGA
        ent = adjust_day(data_entrega, dia_pagamento)
        for desc, v in [('Abatimento FGTS', fgts), ('Abatimento Fin. Banco', fin_banco)]:
            saldo -= v; eventos.append({'data':ent,'tipo':desc,'valor':v,'juros':0,'dias_corridos':'','taxa_efetiva':'',
                                        'incc':0,'ipca':0,'taxas_extra':[],'abatimento':0,'saldo':saldo})
        for nome,val in [('Emissão CCB',TAXA_EMISSAO_CCB),('Alienação Fiduciária',TAXA_ALIENACAO_FIDUCIARIA),
                         ('Registro',TAXA_REGISTRO_FIXA)]:
            saldo += val; eventos.append({'data':ent,'tipo':'Taxa '+nome,'valor':-val,'juros':0,'dias_corridos':'','taxa_efetiva':'',
                                        'incc':0,'ipca':0,'taxas_extra':[],'abatimento':0,'saldo':saldo})
        fee = saldo * TAXA_SEGURO_PRESTAMISTA_PCT; saldo += fee
        eventos.append({'data':ent,'tipo':'Taxa Seguro Prestamista','valor':-fee,'juros':0,'dias_corridos':'','taxa_efetiva':'',
                        'incc':0,'ipca':0,'taxas_extra':[],'abatimento':v,'saldo':saldo})
        # 3) PÓS-ENTREGA
        idx_nr, parcelas, dt_evt = 0, 0, ent
        while saldo>0 and parcelas<=420:
            if idx_nr<len(post_nr) and post_nr[idx_nr]['data']<=dt_evt:
                ev = post_nr[idx_nr]; idx_nr+=1
            else:
                ev = {'data':dt_evt,'tipo':'Pós-Entrega','valor':capacidade_pos}
            juros,dias_corr,taxa_eff = tracker_pos.calculate(ev['data'],saldo)
            ipca = saldo*TAXA_IPCA; incc = 0.0
            extras  = [saldo*t['pct'] if t['periodo'] in ['pós','ambos'] else 0.0 for t in taxas_extras]
            total_taxas = sum(extras)+ipca+incc
            abatimento = ev['valor']-juros-total_taxas; saldo -= abatimento
            eventos.append({**ev,'parcela':parcelas,'juros':juros,'dias_corridos':dias_corr,'taxa_efetiva':taxa_eff,
                            'incc':incc,'ipca':ipca,'taxas_extra':extras,'abatimento':abatimento,'saldo':saldo})
            parcelas+=1; dt_evt=adjust_day(dt_evt+relativedelta(months=1),dia_pagamento)
        # MONTAR PLANILHA
        wb=Workbook(); ws=wb.active; ws.title=f"Financ-{cliente}"[:31]
        headers = ["Data","Parcela","Tipo","Dias no Mês","Dias Corridos","Taxa Efetiva","Valor Pago (R$)",
                   "Juros (R$)","INCC (R$)","IPCA (R$)"]
        headers+=[f"Taxa {i+1} (R$)" for i in range(len(taxas_extras))]
        headers+=["abatimento (R$)","Saldo Devedor (R$)"]
        for i,h in enumerate(headers,1): cell=ws.cell(row=1,column=i,value=h); cell.fill=HEADER_FILL; cell.font=Font(bold=True)
        # inicial
        ws.append(["-"]*(len(headers)-1)+[valor_imovel])
        # eventos
        for ev in sorted(eventos,key=lambda x:x['data']):
            row=[ev['data'],ev.get('parcela',''),ev['tipo'],days_in_month(ev['data']),ev.get('dias_corridos',''),ev.get('taxa_efetiva',''),
                 ev.get('valor',0),ev.get('juros',0),ev.get('incc',0),ev.get('ipca',0)]
            taxas = ev.get('taxas_extra') or []  # Garante que será uma lista
            row+=ev.get('taxas_extra',[])+[ev.get('abatimento',0),ev.get('saldo',0)]
            ws.append(row)
        # linha em branco + soma
        ws.append([""]*len(headers))
        sum_row=ws.max_row+1
        ws.cell(row=sum_row,column=1,value="TOTAL").fill=HEADER_FILL
        for col_idx in range(7,len(headers)-1):
            letter=get_column_letter(col_idx)
            ws.cell(row=sum_row,column=col_idx,value=f"=SUM({letter}3:{letter}{sum_row-2})")
        # formatação
        for col_idx,h in enumerate(headers,1):
            for row_idx in range(2,sum_row+1):
                cell=ws.cell(row=row_idx,column=col_idx)
                if h=="Data": cell.number_format=DATE_FORMAT
                elif h in ["Parcela","Dias no Mês","Dias Corridos"]: cell.number_format='0'
                elif h=="Taxa Efetiva": cell.number_format=PERCENT_FORMAT
                else: cell.number_format=CURRENCY_FORMAT
                elif "R$" in h or "Valor" in h or "Saldo" in h or "abatimento" in h or "Juros" in h or "INCC" in h or "IPCA" in h or "Taxa" in h:
                    cell.number_format = CURRENCY_FORMAT
        # ajuste colunas
        for col_cells in ws.columns:
            width=max(len(str(c.value)) for c in col_cells if c.value is not None)
            ws.column_dimensions[get_column_letter(col_cells[0].column)].width=width+2

        # Se excedeu parcelas e ainda há saldo devedor
        if parcelas >= 420 and saldo > 0:
            st.error(
                f"Financiamento de {cliente} não é possível! "
                "A quantidade de parcelas excede 420 e o saldo devedor continua positivo."
                )

        # download
        buf=BytesIO(); wb.save(buf); buf.seek(0)
        st.download_button("Download Excel",data=buf,file_name=f"financiamento_{cliente}.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        
if __name__=="__main__": main()
