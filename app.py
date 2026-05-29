import streamlit as st
import pandas as pd
import json
from datetime import datetime
import base64

st.set_page_config(
    page_title="Gerador de Fechamento — Manutenção",
    page_icon="⚙️",
    layout="centered"
)

st.markdown("""
<style>
    .main { background: #f4f3ef; }
    h1 { color: #1a3a5c; }
    .stButton > button {
        background: #1a3a5c;
        color: white;
        border: none;
        padding: 10px 28px;
        border-radius: 5px;
        font-weight: 600;
        font-size: 15px;
        width: 100%;
    }
    .stButton > button:hover { background: #254f7a; }
</style>
""", unsafe_allow_html=True)

st.title("⚙️ Fechamento de Manutenção")
st.markdown("Faça upload dos dois arquivos do ERP e gere o relatório completo em HTML.")

st.divider()

col1, col2 = st.columns(2)
with col1:
    st.markdown("**📋 Arquivo 1 — Horas Detalhada**")
    file_horas = st.file_uploader("Apontamentos de horas por técnico", type=["xlsx"], key="horas")
with col2:
    st.markdown("**📦 Arquivo 2 — Movimento de Materiais**")
    file_mov = st.file_uploader("Movimento de materiais (código 0298)", type=["xlsx"], key="mov")

horas_mes = st.number_input("Jornada mensal por técnico (horas)", min_value=100, max_value=250, value=176, step=1)
nome_responsavel = st.text_input("Responsável pelo relatório", value="Andrei")
cargo_responsavel = st.text_input("Cargo", value="Programador PCM — Manutenção Industrial")

st.divider()

def tipo_manut(desc):
    d = str(desc)
    if 'Preventiva' in d: return 'Preventiva'
    if 'Corretiva' in d: return 'Corretiva'
    return 'Geral/Apoio'

def processar_dados(df_horas_raw, df_mov_raw, horas_mes):
    df = df_horas_raw.copy()
    df['DATA'] = pd.to_datetime(df['DATA'], errors='coerce')
    df['TIPO'] = df['DESCRICAO'].apply(tipo_manut)

    df_custo = df_mov_raw[df_mov_raw['TIPO_OPERACAO'] == 2].copy()

    total_h   = df['UTT'].sum()
    total_os  = df['P_ORDEM'].nunique()
    total_tec = df['NP'].nunique()
    total_mat = df_custo['CME_TOTAL'].sum()
    cap_total = total_tec * horas_mes

    tipo_h = df.groupby('TIPO')['UTT'].sum()
    pm_h   = tipo_h.get('Preventiva', 0)
    cm_h   = tipo_h.get('Corretiva', 0)
    ge_h   = tipo_h.get('Geral/Apoio', 0)
    pm_pct = round(pm_h / total_h * 100, 1)
    cm_pct = round(cm_h / total_h * 100, 1)
    ge_pct = round(ge_h / total_h * 100, 1)

    data_min = df['DATA'].min().strftime('%d/%m/%Y')
    data_max = df['DATA'].max().strftime('%d/%m/%Y')
    mes_ano  = df['DATA'].max().strftime('%B %Y').capitalize()

    colab = df.groupby(['NP','Expr1'])['UTT'].sum().reset_index()
    colab.columns = ['NP','NOME','HORAS']
    colab = colab.sort_values('HORAS', ascending=False)
    colab['OCC']    = (colab['HORAS'] / horas_mes * 100).round(1)
    colab['SALDO']  = (colab['HORAS'] - horas_mes).round(1)
    excedente_total = colab['SALDO'].clip(lower=0).sum()

    equipe = df.groupby('Expr2')['UTT'].sum().reset_index()
    setor  = df.groupby('DES')['UTT'].sum().reset_index().sort_values('UTT', ascending=False)

    eq_h    = df.groupby('cod')['UTT'].sum().reset_index()
    eq_info = df.drop_duplicates('cod')[['cod','DESCRICAO','TIPO']]
    custo_eq= df_custo.groupby('__COLUMN1')['CME_TOTAL'].sum().reset_index()
    custo_eq.columns = ['cod','CUSTO_MAT']

    eq = eq_h.merge(eq_info, on='cod').merge(custo_eq, on='cod', how='left')
    eq['CUSTO_MAT'] = eq['CUSTO_MAT'].fillna(0)
    eq = eq.sort_values('UTT', ascending=False).reset_index(drop=True)
    eq['PCT']  = (eq['UTT'] / total_h * 100).round(1)
    eq['ACUM'] = eq['PCT'].cumsum().round(1)
    eq['NOME_CURTO'] = eq['DESCRICAO'].str.slice(0, 55)

    top10 = eq.head(10)

    df['DIA_SEM'] = df['DATA'].dt.dayofweek
    fds_h = df[df['DIA_SEM'].isin([5,6])]['UTT'].sum()

    return {
        'total_h': round(total_h, 1),
        'total_os': total_os,
        'total_tec': total_tec,
        'total_mat': total_mat,
        'cap_total': cap_total,
        'pm_h': round(pm_h, 1), 'pm_pct': pm_pct,
        'cm_h': round(cm_h, 1), 'cm_pct': cm_pct,
        'ge_h': round(ge_h, 1), 'ge_pct': ge_pct,
        'data_min': data_min, 'data_max': data_max, 'mes_ano': mes_ano,
        'colab': colab.to_dict('records'),
        'excedente_total': round(excedente_total, 1),
        'occ_media': round(total_h / cap_total * 100, 1),
        'equipe': equipe.to_dict('records'),
        'setor': setor.to_dict('records'),
        'top10': top10.to_dict('records'),
        'fds_h': round(fds_h, 1),
        'horas_mes': horas_mes,
    }

def gerar_html(d, nome, cargo):
    mes = d['mes_ano']
    periodo = f"{d['data_min']} – {d['data_max']}"

    pareto_rows = ''
    for i, r in enumerate(d['top10']):
        tipo = r['TIPO']
        badge_cls = 'prev' if tipo=='Preventiva' else ('corr' if tipo=='Corretiva' else 'geral')
        is_top = i < 5
        is_crit = tipo == 'Corretiva' and i < 3
        row_style = 'pareto-row-top3' if is_top else ''
        nome_style = 'style="color:#a32020;font-weight:600;"' if is_crit else ('' if not is_top else 'style="font-weight:600;"')
        hora_style = 'style="color:#a32020;font-weight:700;"' if is_crit else ('style="color:#1a3a5c;font-weight:700;"' if is_top else '')
        custo = f"R$ {r['CUSTO_MAT']:,.2f}".replace(',','X').replace('.',',').replace('X','.') if r['CUSTO_MAT'] > 0 else '—'
        pct_bar = r['PCT'] / d['top10'][0]['PCT'] * 100
        bar_color = '#1a3a5c' if r['ACUM'] <= 80 else '#c8c4b8'
        pareto_rows += f"""
        <tr class="{row_style}">
          <td style="font-family:var(--mono);color:var(--muted);">{i+1}</td>
          <td {nome_style}>{r['NOME_CURTO']}</td>
          <td><span class="badge {badge_cls}">{tipo.upper()}</span></td>
          <td class="num" {hora_style}>{r['UTT']:.1f}h</td>
          <td class="num">{r['PCT']}%</td>
          <td class="num" style="color:{'var(--accent)' if r['ACUM']<=80 else 'var(--muted)'};">{r['ACUM']}%</td>
          <td><div class="pareto-bar-bg"><div class="pareto-bar-fill" style="width:{pct_bar:.0f}%;background:{bar_color};"></div></div></td>
        </tr>"""

    tech_js = json.dumps([{
        'nome': r['NOME'].title(),
        'tipo': 'Mecânica' if 'MEC' in str(r.get('NP','')).upper() else 'Elétrica',
        'horas': r['HORAS'],
        'occ': r['OCC'],
        'saldo': r['SALDO'],
    } for r in d['colab']])

    setor_labels = json.dumps([r['DES'][:18] for r in d['setor'][:6]])
    setor_data   = json.dumps([round(r['UTT'],1) for r in d['setor'][:6]])

    total_mat_fmt = f"R$ {d['total_mat']:,.2f}".replace(',','X').replace('.',',').replace('X','.')
    occ_color = '#c8510a' if d['occ_media'] > 100 else '#1a3a5c'

    if d['cm_pct'] > 25:
        alert_pmcm_color = 'red'
        alert_pmcm_icon  = '✘'
        alert_pmcm_txt   = f'Corretiva em {d["cm_pct"]}% — acima do ideal (≤25%). Equipamentos críticos ainda operam com plano preventivo insuficiente.'
    else:
        alert_pmcm_color = 'green'
        alert_pmcm_icon  = '✔'
        alert_pmcm_txt   = f'Corretiva em {d["cm_pct"]}% — dentro do ideal (≤25%). Plano preventivo bem executado no mês.'

    alert_occ = ''
    if d['occ_media'] > 100:
        alert_occ = f'<div class="alert red"><strong>✘ Atenção:</strong> Todos os {d["total_tec"]} técnicos ultrapassaram a jornada de {d["horas_mes"]}h. Total de {d["excedente_total"]}h excedentes — demanda real acima da capacidade nominal.</div>'

    diag_pos = ''
    diag_neg = ''
    if d['pm_pct'] >= 50:
        diag_pos += f'<div class="diag-item"><div class="diag-dot dot-green"></div><span>{d["pm_pct"]}% das horas em manutenção preventiva demonstra comprometimento com o plano mesmo sob pressão de corretivas.</span></div>'
    diag_pos += f'<div class="diag-item"><div class="diag-dot dot-green"></div><span>{d["total_os"]} OS gerenciadas por {d["total_tec"]} técnicos no mês — alta produtividade operacional.</span></div>'
    if d['excedente_total'] == 0:
        diag_pos += f'<div class="diag-item"><div class="diag-dot dot-green"></div><span>Equipe dentro da capacidade nominal de {d["horas_mes"]}h — sem horas excedentes.</span></div>'

    if d['cm_pct'] > 25:
        diag_neg += f'<div class="diag-item"><div class="diag-dot dot-red"></div><span>{d["cm_pct"]}% de corretiva é acima do ideal (≤25%). Equipamentos críticos operam com PM insuficiente.</span></div>'
    if d['excedente_total'] > 0:
        diag_neg += f'<div class="diag-item"><div class="diag-dot dot-red"></div><span>Todos os técnicos ultrapassaram {d["horas_mes"]}h. Total de {d["excedente_total"]}h excedentes — sem margem para emergências.</span></div>'
    if d['pm_pct'] < 60:
        diag_neg += f'<div class="diag-item"><div class="diag-dot dot-yellow"></div><span>Preventiva abaixo da meta de 60% ({d["pm_pct"]}%). Elevar gradualmente nos próximos meses.</span></div>'

    html = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Fechamento de Manutenção – {mes}</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js"></script>
<style>
  @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@300;400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap');
  *,*::before,*::after{{box-sizing:border-box;margin:0;padding:0;}}
  :root{{--bg:#f4f3ef;--surface:#ffffff;--surface2:#f9f8f5;--border:#e2e0d8;--text:#1a1917;--muted:#6b6a64;--accent:#1a3a5c;--accent2:#c8510a;--green:#2d6a2d;--green-bg:#eaf3ea;--red:#a32020;--red-bg:#fdf0f0;--yellow:#7a5500;--yellow-bg:#fef7e0;--blue-bg:#e8f0f8;--font:'IBM Plex Sans',sans-serif;--mono:'IBM Plex Mono',monospace;}}
  body{{font-family:var(--font);background:var(--bg);color:var(--text);font-size:13px;line-height:1.6;padding:32px 24px 64px;max-width:1100px;margin:0 auto;}}
  .report-header{{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:36px;padding-bottom:20px;border-bottom:2px solid var(--accent);}}
  .report-title h1{{font-size:22px;font-weight:600;color:var(--accent);letter-spacing:-0.3px;}}
  .report-title p{{font-size:12px;color:var(--muted);margin-top:4px;font-family:var(--mono);}}
  .report-badge{{background:var(--accent);color:white;padding:8px 16px;border-radius:4px;font-size:11px;font-weight:500;font-family:var(--mono);text-align:right;}}
  .section{{margin-bottom:32px;}}
  .section-title{{font-size:10px;font-weight:600;color:var(--muted);text-transform:uppercase;letter-spacing:1.2px;margin-bottom:12px;display:flex;align-items:center;gap:8px;}}
  .section-title::after{{content:'';flex:1;height:1px;background:var(--border);}}
  .kpi-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;}}
  .kpi-card{{background:var(--surface);border:1px solid var(--border);border-radius:6px;padding:16px;}}
  .kpi-label{{font-size:10px;font-weight:500;color:var(--muted);text-transform:uppercase;letter-spacing:0.8px;margin-bottom:6px;}}
  .kpi-value{{font-size:26px;font-weight:600;color:var(--accent);font-family:var(--mono);line-height:1;}}
  .kpi-sub{{font-size:11px;color:var(--muted);margin-top:4px;}}
  .kpi-card.highlight{{border-left:3px solid var(--accent2);}}
  .alert{{display:flex;align-items:center;gap:12px;padding:12px 16px;border-radius:5px;font-size:12px;margin-bottom:10px;}}
  .alert.green{{background:var(--green-bg);color:var(--green);border-left:3px solid var(--green);}}
  .alert.red{{background:var(--red-bg);color:var(--red);border-left:3px solid var(--red);}}
  .alert.yellow{{background:var(--yellow-bg);color:var(--yellow);border-left:3px solid #c8900a;}}
  .charts-row{{display:grid;grid-template-columns:1fr 1fr;gap:16px;}}
  .chart-card{{background:var(--surface);border:1px solid var(--border);border-radius:6px;padding:20px;}}
  .chart-card h3{{font-size:12px;font-weight:600;color:var(--muted);text-transform:uppercase;letter-spacing:0.8px;margin-bottom:16px;}}
  .table-card{{background:var(--surface);border:1px solid var(--border);border-radius:6px;overflow:hidden;}}
  .table-card table{{width:100%;border-collapse:collapse;}}
  .table-card th{{background:var(--surface2);font-size:10px;font-weight:600;text-transform:uppercase;letter-spacing:0.8px;color:var(--muted);padding:10px 14px;text-align:left;border-bottom:1px solid var(--border);}}
  .table-card td{{padding:9px 14px;border-bottom:1px solid var(--border);font-size:12px;color:var(--text);}}
  .table-card tr:last-child td{{border-bottom:none;}}
  .table-card tr:hover td{{background:var(--surface2);}}
  .num{{font-family:var(--mono);font-size:12px;text-align:right;}}
  .badge{{display:inline-block;padding:2px 8px;border-radius:3px;font-size:10px;font-weight:600;font-family:var(--mono);}}
  .badge.prev{{background:var(--blue-bg);color:#1a3a5c;}}
  .badge.corr{{background:var(--red-bg);color:var(--red);}}
  .badge.geral{{background:#f0ede6;color:#5a5650;}}
  .pareto-bar-bg{{background:#e8e6e0;border-radius:2px;height:8px;min-width:60px;}}
  .pareto-bar-fill{{height:100%;border-radius:2px;background:var(--accent);}}
  .pareto-row-top3 td{{background:#f0ede6;}}
  .tech-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px;}}
  .tech-card{{background:var(--surface);border:1px solid var(--border);border-radius:6px;padding:14px 16px;}}
  .tech-name{{font-size:12px;font-weight:600;color:var(--text);margin-bottom:2px;}}
  .tech-role{{font-size:10px;color:var(--muted);margin-bottom:12px;}}
  .tech-hours{{font-size:22px;font-weight:600;font-family:var(--mono);color:var(--accent);}}
  .tech-pct{{font-size:11px;margin-bottom:8px;}}
  .occ-bar-bg{{background:#e8e6e0;border-radius:2px;height:6px;}}
  .occ-bar-fill{{height:100%;border-radius:2px;}}
  .diag-grid{{display:grid;grid-template-columns:1fr 1fr;gap:12px;}}
  .diag-card{{background:var(--surface);border:1px solid var(--border);border-radius:6px;padding:16px;}}
  .diag-card h4{{font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:0.8px;color:var(--muted);margin-bottom:10px;}}
  .diag-item{{display:flex;align-items:flex-start;gap:8px;margin-bottom:8px;font-size:12px;}}
  .diag-dot{{width:6px;height:6px;border-radius:50%;margin-top:5px;flex-shrink:0;}}
  .dot-green{{background:var(--green);}} .dot-red{{background:var(--red);}} .dot-yellow{{background:#c8900a;}}
  .report-footer{{margin-top:40px;padding-top:20px;border-top:1px solid var(--border);display:flex;justify-content:space-between;align-items:center;font-size:11px;color:var(--muted);font-family:var(--mono);}}
</style>
</head>
<body>
<div class="report-header">
  <div class="report-title">
    <h1>Fechamento de Manutenção</h1>
    <p>{mes} · Período: {periodo}</p>
  </div>
  <div class="report-badge">RELATÓRIO GERENCIAL<br>MANUTENÇÃO INDUSTRIAL</div>
</div>
<div class="section">
  <div class="section-title">Indicadores Gerais do Mês</div>
  <div class="kpi-grid">
    <div class="kpi-card highlight">
      <div class="kpi-label">Total de Horas</div>
      <div class="kpi-value">{d['total_h']}</div>
      <div class="kpi-sub">base {d['horas_mes']}h/técnico</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-label">Ordens de Serviço</div>
      <div class="kpi-value">{d['total_os']}</div>
      <div class="kpi-sub">OS abertas no mês</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-label">Técnicos</div>
      <div class="kpi-value">{d['total_tec']}</div>
      <div class="kpi-sub">equipe manutenção</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-label">Custo de Materiais</div>
      <div class="kpi-value" style="font-size:18px;">{total_mat_fmt}</div>
      <div class="kpi-sub">total do mês</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-label">% Preventiva (PM)</div>
      <div class="kpi-value">{d['pm_pct']}%</div>
      <div class="kpi-sub">{d['pm_h']}h · meta ≥ 60%</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-label">% Corretiva (CM)</div>
      <div class="kpi-value" style="color:{'var(--red)' if d['cm_pct']>25 else 'var(--accent)'};">{d['cm_pct']}%</div>
      <div class="kpi-sub">{d['cm_h']}h · ideal ≤ 25%</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-label">Horas FDS</div>
      <div class="kpi-value">{d['fds_h']}h</div>
      <div class="kpi-sub">fim de semana</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-label">Ocupação Equipe</div>
      <div class="kpi-value" style="color:{occ_color};">{d['occ_media']}%</div>
      <div class="kpi-sub">base {d['horas_mes']}h/técnico</div>
    </div>
  </div>
</div>
<div class="section">
  <div class="section-title">Diagnóstico Rápido</div>
  <div class="alert {alert_pmcm_color}"><strong>{alert_pmcm_icon} PM/CM:</strong> {alert_pmcm_txt}</div>
  {alert_occ}
</div>
<div class="section">
  <div class="section-title">Distribuição de Horas</div>
  <div class="charts-row">
    <div class="chart-card">
      <h3>Por tipo de manutenção</h3>
      <div style="position:relative;width:100%;height:220px;"><canvas id="chartTipo"></canvas></div>
    </div>
    <div class="chart-card">
      <h3>Por setor atendido</h3>
      <div style="position:relative;width:100%;height:220px;"><canvas id="chartSetor"></canvas></div>
    </div>
  </div>
</div>
<div class="section">
  <div class="section-title">Pareto de Equipamentos — Horas Totais (80/20)</div>
  <div class="table-card">
    <table>
      <thead><tr>
        <th>#</th><th>Equipamento</th><th>Tipo</th>
        <th class="num">Horas</th><th class="num">%</th>
        <th class="num">% Acum.</th><th style="min-width:100px;">Pareto</th>
      </tr></thead>
      <tbody>{pareto_rows}</tbody>
    </table>
  </div>
</div>
<div class="section">
  <div class="section-title">Desempenho por Técnico</div>
  <div style="background:var(--surface);border:1px solid var(--border);border-radius:6px;padding:20px;margin-bottom:16px;">
    <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin-bottom:16px;padding-bottom:16px;border-bottom:1px solid var(--border);">
      <div>
        <div style="font-size:10px;font-weight:600;text-transform:uppercase;letter-spacing:0.8px;color:var(--muted);margin-bottom:6px;">Capacidade nominal</div>
        <div style="font-size:22px;font-weight:600;font-family:var(--mono);color:var(--accent);">{d['cap_total']}h</div>
        <div style="font-size:11px;color:var(--muted);margin-top:2px;">{d['total_tec']} técnicos × {d['horas_mes']}h/mês</div>
      </div>
      <div>
        <div style="font-size:10px;font-weight:600;text-transform:uppercase;letter-spacing:0.8px;color:var(--muted);margin-bottom:6px;">Total executado</div>
        <div style="font-size:22px;font-weight:600;font-family:var(--mono);color:{'var(--accent2)' if d['total_h']>d['cap_total'] else 'var(--accent)'};">{d['total_h']}h</div>
        <div style="font-size:11px;color:var(--muted);margin-top:2px;">{'+'+str(d['excedente_total'])+'h acima da jornada' if d['excedente_total']>0 else 'dentro da jornada'}</div>
      </div>
      <div>
        <div style="font-size:10px;font-weight:600;text-transform:uppercase;letter-spacing:0.8px;color:var(--muted);margin-bottom:6px;">Excedente médio/técnico</div>
        <div style="font-size:22px;font-weight:600;font-family:var(--mono);color:{'var(--accent2)' if d['excedente_total']>0 else 'var(--accent)'};">+{round(d['excedente_total']/d['total_tec'],1)}h</div>
        <div style="font-size:11px;color:var(--muted);margin-top:2px;">por profissional no mês</div>
      </div>
    </div>
    <p style="font-size:12px;color:var(--text);line-height:1.8;">
      {'<strong>Todos os técnicos ultrapassaram a jornada contratual de '+str(d["horas_mes"])+'h.</strong> A demanda real foi superior à capacidade nominal — a operação está sendo sustentada por horas acima do limite, sem margem para emergências.' if d['excedente_total']>0 else 'Equipe operando dentro da capacidade contratual de '+str(d['horas_mes'])+'h por técnico.'}
    </p>
  </div>
  <div class="tech-grid" id="techGrid"></div>
</div>
<div class="section">
  <div class="section-title">Diagnóstico Estratégico</div>
  <div class="diag-grid">
    <div class="diag-card"><h4>Pontos Positivos</h4>{diag_pos}</div>
    <div class="diag-card"><h4>Pontos Críticos</h4>{diag_neg}</div>
  </div>
</div>
<div class="report-footer">
  <span>Fechamento Manutenção · {mes}</span>
  <span>{nome} · {cargo}</span>
</div>
<script>
const techData = {tech_js};
const tg = document.getElementById('techGrid');
techData.forEach(t => {{
  const color = t.occ > 110 ? '#c8510a' : t.occ > 100 ? '#7a5500' : '#2d6a2d';
  const saldo = t.saldo > 0 ? '+'+t.saldo.toFixed(1)+'h acima de {d["horas_mes"]}h' : Math.abs(t.saldo).toFixed(1)+'h abaixo de {d["horas_mes"]}h';
  tg.innerHTML += `<div class="tech-card">
    <div class="tech-name">${{t.nome}}</div>
    <div class="tech-role">Manutenção ${{t.tipo}}</div>
    <div class="tech-hours">${{t.horas.toFixed(1)}}h</div>
    <div class="tech-pct" style="color:${{color}};font-weight:500;">${{t.occ.toFixed(1)}}% · ${{saldo}}</div>
    <div class="occ-bar-bg"><div class="occ-bar-fill" style="width:${{Math.min(t.occ,120)/120*100}}%;background:${{color}};"></div></div>
  </div>`;
}});
new Chart(document.getElementById('chartTipo'), {{
  type:'doughnut',
  data:{{labels:['Preventiva','Corretiva','Geral/Apoio'],datasets:[{{data:[{d['pm_h']},{d['cm_h']},{d['ge_h']}],backgroundColor:['#1a3a5c','#c8510a','#b4b2a9'],borderWidth:2,borderColor:'#ffffff'}}]}},
  options:{{responsive:true,maintainAspectRatio:false,plugins:{{legend:{{display:false}},tooltip:{{callbacks:{{label:ctx=>` ${{ctx.label}}: ${{ctx.parsed.toFixed(1)}}h`}}}}}}}}
}});
new Chart(document.getElementById('chartSetor'), {{
  type:'bar',
  data:{{labels:{setor_labels},datasets:[{{label:'Horas',data:{setor_data},backgroundColor:'#1a3a5c',borderRadius:3,borderWidth:0}}]}},
  options:{{responsive:true,maintainAspectRatio:false,plugins:{{legend:{{display:false}}}},scales:{{x:{{ticks:{{font:{{size:10}}}},grid:{{display:false}}}},y:{{ticks:{{font:{{size:10}}}},grid:{{color:'#e8e6e0'}}}}}}}}
}});
</script>
</body></html>"""
    return html

if file_horas and file_mov:
    if st.button("⚙️ Gerar Relatório"):
        with st.spinner("Processando dados..."):
            try:
                df_h = pd.read_excel(file_horas)
                df_m = pd.read_excel(file_mov)
                dados = processar_dados(df_h, df_m, horas_mes)
                html  = gerar_html(dados, nome_responsavel, cargo_responsavel)

                st.success(f"✅ Relatório gerado! **{dados['mes_ano']}** · {dados['total_h']}h · {dados['total_os']} OS · {dados['total_tec']} técnicos")

                col1, col2, col3 = st.columns(3)
                with col1: st.metric("Preventiva", f"{dados['pm_pct']}%", f"{dados['pm_h']}h")
                with col2: st.metric("Corretiva",  f"{dados['cm_pct']}%", f"{dados['cm_h']}h", delta_color="inverse")
                with col3: st.metric("Ocupação",   f"{dados['occ_media']}%", f"+{dados['excedente_total']}h" if dados['excedente_total']>0 else "OK", delta_color="inverse" if dados['excedente_total']>0 else "normal")

                st.divider()

                mes_clean = dados['mes_ano'].replace(' ','_').replace('/','_')
                b64 = base64.b64encode(html.encode('utf-8')).decode()
                st.markdown(
                    f'<a href="data:text/html;base64,{b64}" download="Fechamento_Manutencao_{mes_clean}.html">'
                    f'<button style="background:#1a3a5c;color:white;border:none;padding:12px 32px;border-radius:5px;font-size:15px;font-weight:600;cursor:pointer;width:100%;">⬇️ Baixar Relatório HTML</button></a>',
                    unsafe_allow_html=True
                )

                st.divider()
                st.markdown("**Pré-visualização:**")
                st.components.v1.html(html, height=600, scrolling=True)

            except Exception as e:
                st.error(f"Erro ao processar: {e}")
                st.exception(e)
else:
    st.info("⬆️ Faça upload dos dois arquivos Excel acima para habilitar a geração do relatório.")

st.divider()
st.caption("Gerador de Fechamento de Manutenção · Desenvolvido com Claude")
