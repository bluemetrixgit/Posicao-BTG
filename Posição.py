import pandas as pd
import numpy as np
import streamlit as st
from io import BytesIO

st.set_page_config(page_title="Match Contas BTG + Posição", layout="wide")
st.title("Match de Contas BTG × Posição")

def limpar_conta(valor):
    if pd.isna(valor):
        return ''
    valor = str(valor).strip().replace('.0', '')
    valor = ''.join(filter(str.isdigit, valor))
    return valor.zfill(9) if valor else ''

@st.cache_data
def carregar_e_processar(controle_bytes, posicao_bytes):
    """Carrega e processa as planilhas (só roda 1 vez)"""
    
    # ---- Controle ----
    df_controle = pd.read_excel(controle_bytes, sheet_name="BTG", skiprows=1)
    df_controle['Conta'] = df_controle['Conta'].apply(limpar_conta)

    # ---- Posição ----
    df_posicao = pd.read_excel(posicao_bytes)
    df_posicao['Conta'] = df_posicao['Conta'].apply(limpar_conta)
    df_posicao["Valor Bruto"] = pd.to_numeric(df_posicao["Valor Bruto"], errors="coerce").fillna(0)

    # Contas em comum
    contas_comuns = set(df_controle["Conta"]) & set(df_posicao["Conta"])
    
    df_controle = df_controle[df_controle["Conta"].isin(contas_comuns)].copy()
    df_posicao = df_posicao[df_posicao["Conta"].isin(contas_comuns)].copy()

    # Base fixa
    colunas_fixas = ["Conta", "Carteira", "Status", "Situação", "Observações"]
    df_base = df_controle[colunas_fixas].drop_duplicates(subset=["Conta"]).copy()

    # ---- Colunas fixas de valor (PL, Caixa, D+0, D+2) ----
    pl_total = df_posicao.groupby("Conta")["Valor Bruto"].sum().reset_index().rename(columns={"Valor Bruto": "PL"})

    d0 = (df_posicao[df_posicao["Produto"] == "BTG Tesouro Selic FIRFRefDI"]
          .groupby("Conta")["Valor Bruto"].sum()
          .reset_index().rename(columns={"Valor Bruto": "D+0"}))

    d2 = (df_posicao[df_posicao["Produto"] == "BLUEMETRIX RF ATIVO FIRF"]
          .groupby("Conta")["Valor Bruto"].sum()
          .reset_index().rename(columns={"Valor Bruto": "D+2"}))

    caixa = pd.merge(d0, d2, on="Conta", how="outer").fillna(0)
    caixa["Caixa"] = caixa["D+0"] + caixa["D+2"]
    caixa = caixa[["Conta", "Caixa"]]

    df_base = (df_base
               .merge(pl_total, on="Conta", how="left")
               .merge(caixa, on="Conta", how="left")
               .merge(d0, on="Conta", how="left")
               .merge(d2, on="Conta", how="left"))

    for col in ["PL", "Caixa", "D+0", "D+2"]:
        df_base[col] = df_base[col].fillna(0)

    # Listas para os multiselects
    ativos = sorted(df_posicao["Ativo"].dropna().astype(str).unique().tolist())
    produtos = sorted(df_posicao["Produto"].dropna().astype(str).unique().tolist())
    submercados = sorted(df_posicao["Sub Mercado"].dropna().astype(str).unique().tolist())
    emissores = sorted(df_posicao["Emissor"].dropna().astype(str).unique().tolist())

    return df_base, df_posicao, ativos, produtos, submercados, emissores, len(contas_comuns)


# ====================== UPLOAD ======================
st.header("1. Upload das planilhas")

col1, col2 = st.columns(2)

with col1:
    uploaded_controle = st.file_uploader("Controle de Contratos (aba BTG)", type=["xlsx"], key="controle")

with col2:
    uploaded_posicao = st.file_uploader("Posição.xlsx", type=["xlsx"], key="posicao")

if uploaded_controle and uploaded_posicao:

    controle_bytes = uploaded_controle.getvalue()
    posicao_bytes = uploaded_posicao.getvalue()

    with st.spinner("Processando planilhas (só na primeira vez)..."):
        df_base, df_posicao, ativos_unicos, produtos_unicos, submercados_unicos, emissores_unicos, qtd_comuns = carregar_e_processar(
            controle_bytes, posicao_bytes
        )

    st.success(f"Contas em comum encontradas: **{qtd_comuns}**")

    # ---------- Seleção ----------
    st.header("2. Selecione Ativos, Produtos, Sub Mercado e Emissor")

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        ativos_selecionados = st.multiselect("Ativos", options=ativos_unicos, default=[])

    with col2:
        produtos_selecionados = st.multiselect("Produtos", options=produtos_unicos, default=[])

    with col3:
        submercados_selecionados = st.multiselect("Sub Mercados", options=submercados_unicos, default=[])

    with col4:
        emissores_selecionados = st.multiselect("Emissores", options=emissores_unicos, default=[])

    # ---------- Montar resultado ----------
    df_final = df_base.copy()

    def adicionar_coluna(df_origem, coluna_filtro, valor_filtro, nome_coluna):
        temp = (df_origem[df_origem[coluna_filtro] == valor_filtro]
                .groupby("Conta")["Valor Bruto"]
                .sum()
                .reset_index()
                .rename(columns={"Valor Bruto": nome_coluna}))
        return pd.merge(df_final, temp, on="Conta", how="left")

    for ativo in ativos_selecionados:
        df_final = adicionar_coluna(df_posicao, "Ativo", ativo, ativo)

    for produto in produtos_selecionados:
        df_final = adicionar_coluna(df_posicao, "Produto", produto, produto)

    for sub in submercados_selecionados:
        df_final = adicionar_coluna(df_posicao, "Sub Mercado", sub, sub)

    for emissor in emissores_selecionados:
        df_final = adicionar_coluna(df_posicao, "Emissor", emissor, emissor)

    # Preencher NaN com 0
    colunas_fixas = ["Conta", "Carteira", "Status", "Situação", "Observações", "PL", "Caixa", "D+0", "D+2"]
    valor_cols = [c for c in df_final.columns if c not in colunas_fixas]
    df_final[valor_cols] = df_final[valor_cols].fillna(0)

    # ---------- Prévia ----------
    st.header("3. Prévia do resultado")
    st.dataframe(df_final, use_container_width=True)

    # ---------- Download ----------
    st.header("4. Download")

    output = BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        df_final.to_excel(writer, index=False, sheet_name="Match_Contas")

        workbook = writer.book
        worksheet = writer.sheets["Match_Contas"]
        formato_contabil = workbook.add_format({'num_format': '#,##0.00', 'align': 'right'})

        for col_num in range(len(df_final.columns)):
            if col_num >= 5:
                worksheet.set_column(col_num, col_num, 18, formato_contabil)
            else:
                worksheet.set_column(col_num, col_num, 18)

    output.seek(0)

    st.download_button(
        label="Baixar Excel",
        data=output,
        file_name="match_contas_btg_posicao.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

else:
    st.info("Faça o upload das duas planilhas para começar.")