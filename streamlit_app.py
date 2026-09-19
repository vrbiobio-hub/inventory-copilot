from io import BytesIO
import pandas as pd
import streamlit as st
from engine import analyze
from importer import suggest_mapping, apply_mapping, validate_dataset
from i18n import tr

st.set_page_config(page_title="Inventory Copilot", page_icon="📦", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
:root {--navy:#16324F;--blue:#0A6ED1;--line:#D9E2EC;--soft:#F5F7F9;--text:#1F2937;}
.stApp {background:#F7F9FB;}
.block-container {padding-top:1rem;padding-bottom:2rem;max-width:1500px;}
section[data-testid="stSidebar"] {background:#F1F4F7;border-right:1px solid #D9E2EC;}
h1,h2,h3 {color:#1F2937;letter-spacing:-.02em;}
.hero {background:white;padding:1rem 1.25rem;border:1px solid #D9E2EC;border-left:5px solid #0A6ED1;border-radius:4px;margin-bottom:.8rem;}
.hero h1 {margin:0 0 .2rem 0;font-size:1.75rem;color:#16324F;}
.hero p {margin:0;color:#52606D;font-size:.98rem;}
.step {font-weight:700;font-size:.78rem;color:#52606D;letter-spacing:.05em;margin-bottom:.25rem;}
.card {background:white;padding:.8rem 1rem;border:1px solid #D9E2EC;border-radius:4px;min-height:105px;}
.small {color:#6B7280;font-size:.86rem;}
div[data-testid="stMetric"] {background:white;border:1px solid #D9E2EC;border-radius:4px;padding:10px 12px;}
div[data-testid="stMetricLabel"] {font-size:.78rem;text-transform:uppercase;letter-spacing:.03em;}
div[data-testid="stMetricValue"] {color:#16324F;}
.stButton>button {border-radius:3px;font-weight:600;}
div[data-testid="stExpander"] {background:white;border-radius:3px!important;border-color:#D9E2EC!important;}
div[data-baseweb="tab-list"] {gap:4px;border-bottom:1px solid #D9E2EC;}
button[data-baseweb="tab"] {font-weight:600;}
[data-testid="stDataFrame"] {border:1px solid #D9E2EC;}
.enterprise-bar {background:#16324F;color:white;padding:10px 14px;border-radius:3px;margin-bottom:12px;font-weight:700;letter-spacing:.02em;}
.status-note {background:white;border:1px solid #D9E2EC;border-left:4px solid #0A6ED1;padding:10px 12px;border-radius:3px;margin:.5rem 0;}
div[role="radiogroup"] {background:white;border:1px solid #D9E2EC;padding:4px;border-radius:4px;gap:4px;}
div[role="radiogroup"] label {padding:.35rem .75rem;border-radius:3px;}
</style>
""", unsafe_allow_html=True)

SALES_TARGETS=['SKU','PERIOD_START','PERIOD_END','QUANTITY','LOCATION','CUSTOMER']
ITEM_TARGETS=['SKU','DESCRIPTION','ON_HAND','UNIT_COST','CURRENCY','LEAD_TIME_DAYS','MOQ','ORDER_MULTIPLE','SUPPLIER','CATEGORY','LOCATION','SERVICE_LEVEL','TARGET_WOS']
PO_TARGETS=['SKU','PO_NUMBER','QUANTITY','EXPECTED_DATE','SUPPLIER']

for k,v in {"stage":1, "result":None, "projection":None, "validated":False, "validation_checks":None, "demand_change":0.0, "lead_delay":0, "review_weeks":4}.items():
    if k not in st.session_state: st.session_state[k]=v

demand_change=st.session_state.demand_change
lead_delay=st.session_state.lead_delay
review_weeks=st.session_state.review_weeks

def read_any(upload):
    name=upload.name.lower(); raw=upload.getvalue()
    if name.endswith('.csv'):
        return {'CSV':pd.read_csv(BytesIO(raw))}
    xls=pd.ExcelFile(BytesIO(raw))
    return {s:pd.read_excel(xls,s) for s in xls.sheet_names}

def choose_sheet(label,sheets,preferred=None,key=None):
    names=list(sheets)
    idx=names.index(preferred) if preferred in names else 0
    return st.selectbox(label,names,index=idx,key=key)

FRIENDLY = {
"es":{"SKU":"Código / SKU","PERIOD_START":"Fecha inicial","PERIOD_END":"Fecha final","QUANTITY":"Cantidad vendida",
"LOCATION":"Ubicación","CUSTOMER":"Cliente","DESCRIPTION":"Descripción","ON_HAND":"Inventario actual",
"UNIT_COST":"Costo unitario","CURRENCY":"Moneda (USD, CLP, COP, MXN...)","LEAD_TIME_DAYS":"Tiempo de entrega (días)","MOQ":"Compra mínima (MOQ)",
"ORDER_MULTIPLE":"Múltiplo de compra","SUPPLIER":"Proveedor","CATEGORY":"Categoría","SERVICE_LEVEL":"Nivel de servicio",
"TARGET_WOS":"Semanas objetivo","PO_NUMBER":"Orden de compra","EXPECTED_DATE":"Fecha esperada"},
"en":{"SKU":"SKU / Item code","PERIOD_START":"Start date","PERIOD_END":"End date","QUANTITY":"Sales quantity",
"LOCATION":"Location","CUSTOMER":"Customer","DESCRIPTION":"Description","ON_HAND":"Current inventory",
"UNIT_COST":"Unit cost","CURRENCY":"Currency (USD, CLP, COP, MXN...)","LEAD_TIME_DAYS":"Lead time (days)","MOQ":"Minimum order qty (MOQ)",
"ORDER_MULTIPLE":"Order multiple","SUPPLIER":"Supplier","CATEGORY":"Category","SERVICE_LEVEL":"Service level",
"TARGET_WOS":"Target weeks","PO_NUMBER":"Purchase order","EXPECTED_DATE":"Expected date"}
}
def mapper(title,df,targets,key,lang):
    st.markdown(f"#### {title}")
    suggestion=suggest_mapping(df.columns,targets)
    options=['— No mapear —' if lang=="es" else '— Not mapped —']+list(df.columns)
    mapping={}
    cols=st.columns(3)
    for i,t in enumerate(targets):
        default=suggestion.get(t)
        idx=options.index(default) if default in options else 0
        mapping[t]=cols[i%3].selectbox(FRIENDLY[lang].get(t,t),options,index=idx,key=f'{key}_{t}')
    return apply_mapping(df,mapping),mapping

def fmt_date(x):
    if pd.isna(x): return "—"
    try: return pd.Timestamp(x).strftime("%d %b %Y")
    except: return str(x)

with st.sidebar:
    lang_label=st.selectbox("Idioma / Language",["Español","English"],key="ui_language")
    lang="es" if lang_label=="Español" else "en"
    st.markdown("## 📦 Inventory Copilot")
    st.caption("Decisiones de inventario en palabras simples.")
    st.divider()
    st.markdown("**Tu progreso**")
    labels=["1 · Cargar datos","2 · Confirmar columnas","3 · Revisar datos","4 · Ver recomendaciones"]
    for i,l in enumerate(labels,1):
        st.write(("✅ " if st.session_state.stage>i else "➡️ " if st.session_state.stage==i else "○ ")+l)
    st.divider()

    st.caption("Enterprise inventory decision support")

st.markdown(f"""<div class="hero"><h1>{tr(lang,"title")}</h1><p>{tr(lang,"subtitle")}</p></div>""",unsafe_allow_html=True)
st.markdown('<div class="enterprise-bar">INVENTORY COPILOT&nbsp;&nbsp; | &nbsp;&nbsp;ACTION CENTER&nbsp;&nbsp; | &nbsp;&nbsp;INVENTORY HEALTH&nbsp;&nbsp; | &nbsp;&nbsp;FORECAST&nbsp;&nbsp; | &nbsp;&nbsp;SCENARIOS</div>',unsafe_allow_html=True)

# V14: the two main workflow actions live above the file uploader.
top_actions = st.empty()
with top_actions.container():
    a1,a2=st.columns(2)
    a1.button("Validar datos" if lang=="es" else "Validate data", disabled=True, use_container_width=True, key="top_validate_disabled")
    a2.button("Analizar mi inventario" if lang=="es" else "Analyze my inventory", disabled=True, use_container_width=True, key="top_analyze_disabled")
    st.caption("Sube el archivo y confirma las columnas; estos botones se activarán aquí mismo." if lang=="es" else "Upload the file and confirm the columns; these buttons will activate here.")

upload=st.file_uploader(tr(lang,"upload"),type=["xlsx","xls","csv"],help="Para el análisis completo necesitas historial de ventas, maestro de artículos y órdenes de compra abiertas.")

if upload is None:
    st.session_state.stage=1
    c1,c2,c3=st.columns(3)
    with c1:
        st.markdown('<div class="card"><b>1. Sube tus datos</b><br><span class="small">No necesitas usar nuestros nombres de columnas. Intentaremos reconocer Material, Item, Stock, Sales Qty, ETA y otros nombres comunes.</span></div>',unsafe_allow_html=True)
    with c2:
        st.markdown('<div class="card"><b>2. Confirma el significado</b><br><span class="small">Antes de calcular, tú confirmas qué columna representa SKU, ventas, inventario, lead time y PO abiertas.</span></div>',unsafe_allow_html=True)
    with c3:
        st.markdown('<div class="card"><b>3. Recibe acciones</b><br><span class="small">Te mostramos primero lo urgente: comprar, acelerar, detener compras o simplemente monitorear.</span></div>',unsafe_allow_html=True)
    st.info("Consejo: para probar el producto puedes usar el archivo demo incluido en el paquete.")
    st.stop()

sheets=read_any(upload)
# Ignore spreadsheet formatting tails / completely blank rows and columns.
for _name,_df in list(sheets.items()):
    _df=_df.dropna(axis=0,how="all").dropna(axis=1,how="all")
    _df.columns=[str(c).strip() for c in _df.columns]
    sheets[_name]=_df
st.session_state.stage=max(st.session_state.stage,2)

st.markdown('<div class="step">PASO 1 DE 3</div>',unsafe_allow_html=True)
st.subheader(tr(lang,"where"))
if len(sheets)==1:
    st.warning("Este archivo contiene una sola tabla. Puedes probar el mapeo, pero el análisis completo necesita ventas, inventario/items y PO abiertas.")

c1,c2,c3=st.columns(3)
with c1: sales_sheet=choose_sheet(tr(lang,"sales"),sheets,"SALES_HISTORY","sheet_sales")
with c2: item_sheet=choose_sheet(tr(lang,"items"),sheets,"ITEM_MASTER","sheet_items")
with c3: po_sheet=choose_sheet(tr(lang,"po"),sheets,"OPEN_ORDERS","sheet_po")

with st.expander(tr(lang,"preview")):
    t1,t2,t3=st.tabs(["Ventas","Items","PO abiertas"])
    with t1: st.dataframe(sheets[sales_sheet].head(5),use_container_width=True,hide_index=True)
    with t2: st.dataframe(sheets[item_sheet].head(5),use_container_width=True,hide_index=True)
    with t3: st.dataframe(sheets[po_sheet].head(5),use_container_width=True,hide_index=True)

st.divider()
st.markdown('<div class="step">PASO 2 DE 3</div>',unsafe_allow_html=True)
st.subheader(tr(lang,"confirm"))
st.caption(tr(lang,"confirm_help"))

tab1,tab2,tab3=st.tabs(["Ventas","Inventario / Items","PO abiertas"])
with tab1: sales,_=mapper(tr(lang,"sales"),sheets[sales_sheet],SALES_TARGETS,"sales",lang)
with tab2: items,_=mapper("Maestro de artículos",sheets[item_sheet],ITEM_TARGETS,"items",lang)
with tab3: po,_=mapper(tr(lang,"po"),sheets[po_sheet],PO_TARGETS,"po",lang)

# Ignore obvious instructional/note rows from demo or exported spreadsheets.
if "SKU" in items.columns:
    _sku=items["SKU"].astype("string").str.strip()
    _note_mask=_sku.str.contains(r"ITEM_MASTER contiene|contains the current|SERVICE_LEVEL es|TARGET_WOS",case=False,na=False)
    items=items.loc[~_note_mask].copy()
if "SKU" in sales.columns:
    sales=sales.loc[~sales["SKU"].astype("string").str.contains(r"SALES_HISTORY contiene|historial de ventas contiene",case=False,na=False)].copy()
if "SKU" in po.columns:
    po=po.loc[~po["SKU"].astype("string").str.contains(r"OPEN_ORDERS contiene|PO abiertas contiene",case=False,na=False)].copy()

st.divider()
st.markdown(f'<div class="step">{"PASO 3 DE 3" if lang=="es" else "STEP 3 OF 3"}</div>',unsafe_allow_html=True)
st.subheader(tr(lang,"review"))
st.caption("Primero validamos la información. El análisis solo comienza cuando tú lo confirmas." if lang=="es" else "We validate the information first. Analysis starts only after you confirm it.")

validate_label="Validar datos" if lang=="es" else "Validate data"
# Populate the action bar created above the uploader now that mappings exist.
with top_actions.container():
    a1,a2=st.columns(2)
    validate_now=a1.button(validate_label,type="primary",use_container_width=True,key="top_validate_active")
    analyze_now=a2.button(tr(lang,"analyze"),type="primary",use_container_width=True,disabled=not st.session_state.validated,key="top_analyze_active")
    if st.session_state.validated:
        st.caption("✓ Datos validados · Puedes ejecutar el análisis." if lang=="es" else "✓ Data validated · You can run the analysis.")
    else:
        st.caption("Confirma el mapeo y valida. El análisis se habilita después de una validación correcta." if lang=="es" else "Confirm mapping and validate. Analysis is enabled after successful validation.")

if validate_now:
    checks=[]
    all_ok=True
    for name,df,kind in [(tr(lang,"sales"),sales,"sales"),(tr(lang,"items"),items,"items"),(tr(lang,"po"),po,"po")]:
        # Ignore rows that became fully empty after mapping.
        df.dropna(axis=0,how="all",inplace=True)
        issues=validate_dataset(df,kind)
        errors=[m for lvl,m in issues if lvl=="error"]
        warnings=[m for lvl,m in issues if lvl=="warning"]
        checks.append((name,errors,warnings))
        if errors: all_ok=False
    st.session_state.validation_checks=checks
    st.session_state.validated=all_ok
    if all_ok:
        st.session_state.stage=max(st.session_state.stage,3)
        # Important UX fix: refresh immediately so Analyze becomes enabled
        # after ONE click on Validate data.
        st.rerun()

checks=st.session_state.validation_checks
if checks:
    cols=st.columns(3)
    for col,(name,errors,warnings) in zip(cols,checks):
        with col:
            st.markdown(f"**{name}**")
            if errors:
                for m in errors: st.error(m)
            elif warnings:
                st.warning("Datos utilizables, con observaciones." if lang=="es" else "Usable data, with observations.")
                for m in warnings: st.caption("• "+m)
            else:
                st.success(tr(lang,"ready"))

if st.session_state.validated:
    st.success("✓ Datos validados" if lang=="es" else "✓ Data validated")
    if analyze_now:
        if "PERIOD_START" not in sales:
            sales["PERIOD_START"]=pd.Timestamp.today()
        if "PERIOD_END" not in sales: sales["PERIOD_END"]=sales["PERIOD_START"]
        for c,val in [("DESCRIPTION",""),("UNIT_COST",0),("CURRENCY",""),("LEAD_TIME_DAYS",0),("MOQ",0),("ORDER_MULTIPLE",1),("SERVICE_LEVEL",.97),("TARGET_WOS",10)]:
            if c not in items: items[c]=val
        if "PO_NUMBER" not in po: po["PO_NUMBER"]=""
        if "SUPPLIER" not in po: po["SUPPLIER"]=""
        result,projection=analyze(sales,items,po,demand_change=demand_change,lead_delay=lead_delay,review_weeks=review_weeks)
        st.session_state.result=result
        st.session_state.projection=projection
        st.session_state.stage=4
        st.rerun()
elif checks:
    st.error("Corrige los campos marcados y vuelve a presionar Validar datos." if lang=="es" else "Correct the highlighted fields and press Validate data again.")

if st.session_state.result is None:
    st.stop()

result=st.session_state.result
projection=st.session_state.projection


def inventory_value_by_currency(df):
    """Never add different currencies together."""
    if "Inventory_value" not in df.columns:
        return []
    tmp=df.copy()
    tmp["Currency"]=tmp.get("Currency","").astype("string").fillna("").str.strip().str.upper()
    tmp["Currency"]=tmp["Currency"].replace({"":"Sin moneda" if lang=="es" else "Unspecified"})
    tmp["Inventory_value"]=pd.to_numeric(tmp["Inventory_value"],errors="coerce").fillna(0)
    tmp=tmp[tmp["Inventory_value"]!=0]
    if tmp.empty: return []
    return [(str(k),float(v)) for k,v in tmp.groupby("Currency")["Inventory_value"].sum().sort_values(ascending=False).items()]

# ---------- V15: Workspace navigation (one view at a time) ----------
view=result.copy()
for c in ["Purchase_value","Excess_value","Inventory_value","Unit_cost","Recommended_qty","Forecast_weekly","On_hand"]:
    if c in view.columns:
        view[c]=pd.to_numeric(view[c],errors="coerce").fillna(0)
    else:
        view[c]=0.0

def priority_reason(r):
    reasons=[]
    if bool(r.get("Expedite",False)): reasons.append("quiebre antes de reposición normal" if lang=="es" else "stockout before normal replenishment")
    if pd.notna(r.get("Stockout")): reasons.append(("quiebre "+fmt_date(r.get("Stockout"))) if lang=="es" else ("stockout "+fmt_date(r.get("Stockout"))))
    if r.get("Recommended_qty",0)>0: reasons.append((f"compra sugerida {r.get('Recommended_qty',0):,.0f}") if lang=="es" else (f"suggested buy {r.get('Recommended_qty',0):,.0f}"))
    if r.get("Excess_value",0)>0: reasons.append((f"${r.get('Excess_value',0):,.0f} en exceso") if lang=="es" else (f"${r.get('Excess_value',0):,.0f} excess"))
    return " · ".join(reasons[:3]) or ("monitorear" if lang=="es" else "monitor")

def action_category(r):
    if bool(r.get("Expedite",False)): return "Urgente" if lang=="es" else "Urgent"
    if r.get("Recommended_qty",0)>0: return "Comprar pronto" if lang=="es" else "Buy soon"
    if r.get("Excess_value",0)>0: return "Exceso" if lang=="es" else "Excess"
    return "Monitorear" if lang=="es" else "Monitor"

view["Category"]=view.apply(action_category,axis=1)
view["_stockout_dt"]=pd.to_datetime(view.get("Stockout"),errors="coerce")
_today=pd.Timestamp.today().normalize()
view["_days_to_stockout"]=(view["_stockout_dt"]-_today).dt.days
view["_impact"]=view[["Purchase_value","Excess_value"]].max(axis=1)

def time_points(days):
    if pd.isna(days): return 0.0
    if days<=0:return 45.0
    if days<=14:return 42.0
    if days<=30:return 38.0
    if days<=60:return 32.0
    if days<=90:return 25.0
    if days<=180:return 15.0
    return 7.0

def replenishment_points(r):
    if bool(r.get("Expedite",False)): return 25.0
    if r.get("Recommended_qty",0)>0 and pd.notna(r.get("Stockout")): return 14.0
    if r.get("Recommended_qty",0)>0:return 8.0
    return 0.0

import math
_max_impact=max(float(view["_impact"].max()),1.0)
_max_demand=max(float(view["Forecast_weekly"].max()),1.0)
def financial_points(x):
    x=max(float(x or 0),0.0)
    return 20.0*(math.log1p(x)/math.log1p(_max_impact)) if x>0 else 0.0
def demand_points(x): return min(10.0,10.0*max(float(x or 0),0.0)/_max_demand)

view["Priority_score"]=view.apply(lambda r:round(time_points(r.get("_days_to_stockout"))+replenishment_points(r)+financial_points(r.get("_impact",0))+demand_points(r.get("Forecast_weekly",0)),1),axis=1)
view["_stockout_sort"]=view["_stockout_dt"].fillna(pd.Timestamp("2262-01-01"))
view=view.sort_values(["Priority_score","_stockout_sort","_impact"],ascending=[False,True,False]).reset_index(drop=True)
view["Priority_rank"]=range(1,len(view)+1)
view["Priority_reason"]=view.apply(priority_reason,axis=1)

urgent=int((view["Category"]==( "Urgente" if lang=="es" else "Urgent")).sum())
buysoon=int((view["Category"]==( "Comprar pronto" if lang=="es" else "Buy soon")).sum())
excess=int((view["Category"]==( "Exceso" if lang=="es" else "Excess")).sum())
excess_value=float(view.Excess_value.sum()); purchase_value=float(view.Purchase_value.sum())

if "workspace" not in st.session_state: st.session_state.workspace="Acciones" if lang=="es" else "Actions"
if "detail_sku" not in st.session_state: st.session_state.detail_sku=None

# A SKU detail is a separate workspace, never appended below another page.
if st.session_state.detail_sku is not None:
    sku=str(st.session_state.detail_sku)
    r=view[view["SKU"].astype(str)==sku].iloc[0]
    b1,b2=st.columns([1,5])
    if b1.button("← Volver" if lang=="es" else "← Back",use_container_width=True):
        st.session_state.detail_sku=None; st.rerun()
    b2.markdown(f"### {sku} · {r.Category} · Ranking #{int(r.Priority_rank)} · Score {r.Priority_score:.1f}")
    st.markdown(f"## {r.Action}")
    d1,d2,d3,d4,d5=st.columns(5)
    d1.metric("Inventario" if lang=="es" else "Inventory",f"{r.On_hand:,.0f}")
    d2.metric("Demanda / semana" if lang=="es" else "Demand / week",f"{r.Forecast_weekly:,.1f}")
    wos=(r.On_hand/r.Forecast_weekly) if r.Forecast_weekly>0 else None
    d3.metric("Semanas inventario" if lang=="es" else "Weeks of supply",f"{wos:.1f}" if wos is not None else "—")
    d4.metric("Cantidad sugerida" if lang=="es" else "Suggested qty",f"{r.Recommended_qty:,.0f}")
    d5.metric("Confianza" if lang=="es" else "Confidence",str(r.Confidence))
    st.info(("Por qué está priorizado: " if lang=="es" else "Why prioritized: ")+str(r.Priority_reason))
    detail_tabs=st.tabs(["Resumen","Proyección","Forecast","PO abiertas","Simulador"] if lang=="es" else ["Summary","Projection","Forecast","Open POs","Simulator"])
    with detail_tabs[0]:
        c1,c2=st.columns(2)
        c1.metric("Impacto económico" if lang=="es" else "Financial impact",f"${r._impact:,.0f}")
        c2.metric("Posible quiebre" if lang=="es" else "Possible stockout",fmt_date(r.Stockout))
        st.write(str(r.Explanation))
    with detail_tabs[1]:
        sku_proj=projection[projection["SKU"].astype(str)==sku].copy()
        if len(sku_proj):
            date_col=next((c for c in sku_proj.columns if "week" in c.lower() or "date" in c.lower()),None)
            inv_col=next((c for c in sku_proj.columns if "ending" in c.lower() or "projected" in c.lower()),None)
            ss_col=next((c for c in sku_proj.columns if "safety" in c.lower()),None)
            if date_col and inv_col:
                chart=sku_proj[[date_col,inv_col]+([ss_col] if ss_col else [])].set_index(date_col)
                st.line_chart(chart)
            st.dataframe(sku_proj,use_container_width=True,hide_index=True)
        else: st.caption("Sin proyección disponible." if lang=="es" else "No projection available.")
    with detail_tabs[2]:
        st.metric("Modelo",str(r.Model))
        st.metric("Error histórico" if lang=="es" else "Historical error",f"{float(r.Forecast_error):.1%}" if pd.notna(r.Forecast_error) else "—")
        st.metric("Demanda esperada / semana" if lang=="es" else "Expected demand / week",f"{r.Forecast_weekly:,.1f}")
    with detail_tabs[3]:
        sku_po=po[po["SKU"].astype(str)==sku].copy() if "SKU" in po.columns else pd.DataFrame()
        if len(sku_po): st.dataframe(sku_po,use_container_width=True,hide_index=True)
        else: st.caption("No hay PO abiertas para este SKU." if lang=="es" else "No open POs for this SKU.")
    with detail_tabs[4]:
        with st.form("sku_scenario_form"):
            q1,q2,q3=st.columns(3)
            sales_pct=q1.number_input("Cambio ventas (%)" if lang=="es" else "Sales change (%)",-100.0,500.0,float(st.session_state.demand_change*100),1.0)
            lead_days=q2.number_input("Cambio lead time (días)" if lang=="es" else "Lead-time change (days)",-365,365,int(st.session_state.lead_delay),1)
            coverage=q3.number_input("Cobertura objetivo (semanas)" if lang=="es" else "Target coverage (weeks)",1,52,int(st.session_state.review_weeks),1)
            apply_scenario=st.form_submit_button("Aplicar escenario" if lang=="es" else "Apply scenario",type="primary",use_container_width=True)
        if apply_scenario:
            st.session_state.demand_change=float(sales_pct)/100; st.session_state.lead_delay=int(lead_days); st.session_state.review_weeks=int(coverage)
            nr,np=analyze(sales,items,po,demand_change=st.session_state.demand_change,lead_delay=st.session_state.lead_delay,review_weeks=st.session_state.review_weeks)
            st.session_state.result=nr; st.session_state.projection=np; st.rerun()
    st.stop()

# Main workspace navigation: only one page is rendered at a time.
nav_es=["Resumen","Acciones","Inventario","Forecast","Compras","Proveedores","Capital","Simulador"]
nav_en=["Summary","Actions","Inventory","Forecast","Purchasing","Suppliers","Capital","Simulator"]
nav=nav_es if lang=="es" else nav_en
# normalize language switches
aliases={"Actions":"Acciones","Summary":"Resumen","Inventory":"Inventario","Purchasing":"Compras","Suppliers":"Proveedores","Capital":"Capital","Simulator":"Simulador","Acciones":"Actions","Resumen":"Summary","Inventario":"Inventory","Compras":"Purchasing","Proveedores":"Suppliers","Simulador":"Simulator"}
if st.session_state.workspace not in nav:
    candidate=aliases.get(st.session_state.workspace,nav[0]); st.session_state.workspace=candidate if candidate in nav else nav[0]
workspace=st.radio("Navegación" if lang=="es" else "Navigation",nav,index=nav.index(st.session_state.workspace),horizontal=True,label_visibility="collapsed")
st.session_state.workspace=workspace
st.divider()

if workspace in ["Resumen","Summary"]:
    st.title("Resumen ejecutivo" if lang=="es" else "Executive summary")
    k1,k2,k3,k4,k5=st.columns(5)
    k1.metric("Acción urgente" if lang=="es" else "Urgent action",urgent)
    k2.metric("Comprar pronto" if lang=="es" else "Buy soon",buysoon)
    k3.metric("Con exceso" if lang=="es" else "Excess",excess)
    k4.metric("Valor en exceso" if lang=="es" else "Excess value",f"${excess_value:,.0f}")
    k5.metric("Compras sugeridas" if lang=="es" else "Suggested purchases",f"${purchase_value:,.0f}")
    # Data Health: make limitations visible instead of hiding them.
    missing_cost=int((pd.to_numeric(view["Unit_cost"],errors="coerce").fillna(0)<=0).sum()) if "Unit_cost" in view.columns else len(view)
    missing_curr=int(view["Currency"].astype("string").fillna("").str.strip().eq("").sum()) if "Currency" in view else len(view)
    missing_lt=int((pd.to_numeric(view["Lead_time_days"],errors="coerce").fillna(0)<=0).sum()) if "Lead_time_days" in view.columns else len(view)
    low_conf=int(view["Confidence"].astype(str).str.lower().isin(["baja","low"]).sum())
    denom=max(1,len(view)*4)
    health_score=max(0,round((1-(missing_cost+missing_curr+missing_lt+low_conf)/denom)*100))
    st.subheader("Salud de datos" if lang=="es" else "Data Health")
    d1,d2,d3,d4=st.columns(4)
    d1.metric("Score",f"{health_score}%")
    d2.metric("Sin costo" if lang=="es" else "Missing cost",missing_cost)
    d3.metric("Sin moneda" if lang=="es" else "Missing currency",missing_curr)
    d4.metric("Forecast baja confianza" if lang=="es" else "Low-confidence forecast",low_conf)
    st.subheader("Top 10 prioridades" if lang=="es" else "Top 10 priorities")
    summary=view.head(10).copy()
    summary["Ranking"]=summary.Priority_rank; summary["Score"]=summary.Priority_score.map(lambda x:f"{x:.1f}"); summary["Categoría"]=summary.Category; summary["SKU"]=summary.SKU.astype(str); summary["Acción"]=summary.Action; summary["Impacto $"]=summary._impact.map(lambda x:f"${x:,.0f}"); summary["Quiebre"]=summary.Stockout.apply(fmt_date)
    st.dataframe(summary[["Ranking","Score","Categoría","SKU","Acción","Impacto $","Quiebre"]],use_container_width=True,hide_index=True)
    st.caption("Ve a Acciones para filtrar el portafolio y abrir el detalle de un SKU." if lang=="es" else "Go to Actions to filter the portfolio and open SKU detail.")

elif workspace in ["Acciones","Actions"]:
    st.title("Centro de acciones" if lang=="es" else "Action Center")
    st.caption("Ranking y categoría son independientes. Filtra una categoría sin perder el ranking global." if lang=="es" else "Ranking and category are independent. Filter a category without losing the global ranking.")
    f1,f2=st.columns([2,1])
    search=f1.text_input("Buscar SKU" if lang=="es" else "Search SKU",placeholder="A100")
    opts=["Todas","Urgente","Comprar pronto","Exceso","Monitorear"] if lang=="es" else ["All","Urgent","Buy soon","Excess","Monitor"]
    cat=f2.selectbox("Categoría" if lang=="es" else "Category",opts)
    filtered=view.copy()
    if search: filtered=filtered[filtered.SKU.astype(str).str.contains(search,case=False,na=False)]
    if cat not in ["Todas","All"]: filtered=filtered[filtered.Category==cat]
    top=filtered.head(50).copy()
    top["Ranking"]=top.Priority_rank; top["Score"]=top.Priority_score.map(lambda x:f"{x:.1f}"); top["Categoría"]=top.Category; top["SKU"]=top.SKU.astype(str); top["Acción"]=top.Action; top["Cantidad"]=top.Recommended_qty.map(lambda x:f"{x:,.0f}"); top["Impacto $"]=top._impact.map(lambda x:f"${x:,.0f}"); top["Quiebre"]=top.Stockout.apply(fmt_date); top["Confianza"]=top.Confidence
    st.dataframe(top[["Ranking","Score","Categoría","SKU","Acción","Cantidad","Impacto $","Quiebre","Confianza"]],use_container_width=True,hide_index=True,height=520)
    if len(filtered)>50: st.caption((f"Mostrando 50 de {len(filtered):,} SKU filtrados." if lang=="es" else f"Showing 50 of {len(filtered):,} filtered SKUs."))
    c1,c2=st.columns([4,1]); sku_options=filtered.SKU.astype(str).tolist() if len(filtered) else view.SKU.astype(str).tolist(); selected=c1.selectbox("SKU para detalle" if lang=="es" else "SKU for detail",sku_options)
    if c2.button("Abrir detalle →" if lang=="es" else "Open detail →",type="primary",use_container_width=True): st.session_state.detail_sku=selected; st.rerun()

elif workspace in ["Inventario","Inventory"]:
    st.title("Inventario" if lang=="es" else "Inventory")
    inv=view.copy(); inv["SKU"]=inv.SKU.astype(str); inv["Categoría"]=inv.Category; inv["Inventario"]=inv.On_hand.map(lambda x:f"{x:,.0f}"); inv["Demanda/sem"]=inv.Forecast_weekly.map(lambda x:f"{x:,.1f}"); inv["WOS"]=inv.apply(lambda r:f"{r.On_hand/r.Forecast_weekly:.1f}" if r.Forecast_weekly>0 else "—",axis=1); inv["Exceso $"]=inv.Excess_value.map(lambda x:f"${x:,.0f}")
    st.dataframe(inv[["SKU","Categoría","Inventario","Demanda/sem","WOS","Exceso $"]],use_container_width=True,hide_index=True,height=650)

elif workspace=="Forecast":
    st.title("Forecast")
    fc=view.copy(); fc["SKU"]=fc.SKU.astype(str); fc["Demanda esperada/sem"]=fc.Forecast_weekly.map(lambda x:f"{x:,.1f}"); fc["Modelo"]=fc.Model; fc["Error histórico"]=fc.Forecast_error.map(lambda x:f"{x:.1%}" if pd.notna(x) else "—"); fc["Confianza"]=fc.Confidence
    st.dataframe(fc[["SKU","Demanda esperada/sem","Modelo","Error histórico","Confianza"]],use_container_width=True,hide_index=True,height=650)

elif workspace in ["Compras","Purchasing"]:
    st.title("Planificador de compras" if lang=="es" else "Purchase Planner")
    st.caption("Qué comprar, cuánto comprar y qué PO abiertas requieren revisión." if lang=="es" else "What to buy, how much to buy, and which open POs need review.")
    buy=view[pd.to_numeric(view["Recommended_qty"],errors="coerce").fillna(0)>0].copy()
    buy["Currency"]=buy["Currency"].astype("string").fillna("").str.strip().str.upper().replace({"":"Sin moneda" if lang=="es" else "Unspecified"}) if "Currency" in buy else ("Sin moneda" if lang=="es" else "Unspecified")
    b1,b2,b3=st.columns(3)
    b1.metric("SKU a comprar" if lang=="es" else "SKUs to buy",len(buy))
    b2.metric("Unidades sugeridas" if lang=="es" else "Suggested units",f"{buy['Recommended_qty'].sum():,.0f}")
    b3.metric("Urgentes" if lang=="es" else "Urgent",int(buy["Category"].astype(str).str.lower().isin(["urgente","urgent"]).sum()))
    if len(buy):
        st.subheader("Valor sugerido de compra" if lang=="es" else "Suggested purchase value")
        vals=buy.groupby("Currency")["Purchase_value"].sum()
        cc=st.columns(min(4,len(vals)))
        for i,(cur,val) in enumerate(vals.items()): cc[i%len(cc)].metric(str(cur),f"{val:,.0f}")
        if "Supplier" in buy:
            st.subheader("Consolidación por proveedor" if lang=="es" else "Supplier consolidation")
            g=buy.assign(Supplier=buy["Supplier"].astype("string").fillna("").replace({"":"Sin proveedor" if lang=="es" else "No supplier"})).groupby(["Supplier","Currency"]).agg(SKUs=("SKU","nunique"),Unidades=("Recommended_qty","sum"),Valor=("Purchase_value","sum")).reset_index().sort_values("Valor",ascending=False)
            g["Unidades"]=g["Unidades"].map(lambda x:f"{x:,.0f}"); g["Valor"]=g["Valor"].map(lambda x:f"{x:,.0f}")
            st.dataframe(g,use_container_width=True,hide_index=True)
        st.subheader("Lista de compra" if lang=="es" else "Buy list")
        t=buy.sort_values("Priority_rank").copy()
        t["Ranking"]=t["Priority_rank"].astype(int); t["Cantidad"]=t["Recommended_qty"].map(lambda x:f"{x:,.0f}"); t["Valor"]=t["Purchase_value"].map(lambda x:f"{x:,.0f}"); t["Quiebre"]=t["Stockout"].apply(fmt_date)
        cols=[c for c in ["Ranking","SKU","Supplier","Currency","Cantidad","Valor","Quiebre","Action"] if c in t.columns]
        st.dataframe(t[cols],use_container_width=True,hide_index=True,height=430)
    st.subheader("Open PO Control Tower")
    if po is not None and len(po):
        pc=po.copy(); pc["SKU"]=pc["SKU"].astype(str)
        stockmap=view.assign(_sku=view["SKU"].astype(str)).set_index("_sku")["Stockout"].to_dict()
        pc["Stockout"]=pd.to_datetime(pc["SKU"].map(stockmap),errors="coerce")
        pc["EXPECTED_DATE"]=pd.to_datetime(pc["EXPECTED_DATE"],errors="coerce")
        pc["Días vs quiebre"]=(pc["EXPECTED_DATE"]-pc["Stockout"]).dt.days
        pc["Acción"]=pc["Días vs quiebre"].apply(lambda x:("Acelerar / revisar" if lang=="es" else "Expedite / review") if pd.notna(x) and x>0 else ("Mantener" if lang=="es" else "Maintain"))
        pc["ETA"]=pc["EXPECTED_DATE"].dt.strftime("%d %b %Y"); pc["Quiebre"]=pc["Stockout"].dt.strftime("%d %b %Y").fillna("—")
        st.dataframe(pc[[c for c in ["PO_NUMBER","SKU","QUANTITY","ETA","Quiebre","Días vs quiebre","Acción"] if c in pc.columns]],use_container_width=True,hide_index=True)

elif workspace in ["Proveedores","Suppliers"]:
    st.title("Exposición por proveedor" if lang=="es" else "Supplier Exposure")
    st.caption("Exposición objetiva; todavía no es un score de desempeño del proveedor." if lang=="es" else "Objective exposure; this is not yet a supplier performance score.")
    if "Supplier" not in view:
        st.info("Agrega SUPPLIER para habilitar esta vista." if lang=="es" else "Add SUPPLIER to enable this view.")
    else:
        sv=view.copy()
        sv["Supplier"]=sv["Supplier"].astype("string").fillna("").replace({"":"Sin proveedor" if lang=="es" else "No supplier"})
        sv["Currency"]=sv["Currency"].astype("string").fillna("").str.upper().replace({"":"Sin moneda" if lang=="es" else "Unspecified"})
        sv["Urgentes"]=sv["Category"].astype(str).str.lower().isin(["urgente","urgent"]).astype(int)
        g=sv.groupby(["Supplier","Currency"]).agg(SKUs=("SKU","nunique"),Inventario=("Inventory_value","sum"),Exceso=("Excess_value","sum"),Lead_time=("Lead_time_days","mean"),Urgentes=("Urgentes","sum")).reset_index().sort_values(["Urgentes","Inventario"],ascending=False)
        g["Inventario"]=g["Inventario"].map(lambda x:f"{x:,.0f}"); g["Exceso"]=g["Exceso"].map(lambda x:f"{x:,.0f}"); g["Lead time"]=g["Lead_time"].map(lambda x:f"{x:.0f} d")
        st.dataframe(g,use_container_width=True,hide_index=True,height=580)
        st.info("Para OTD, fill rate y lead time real, la próxima expansión natural es PURCHASE_HISTORY." if lang=="es" else "For OTD, fill rate and actual lead time, the next natural expansion is PURCHASE_HISTORY.")

elif workspace=="Capital":
    st.title("Capital de inventario" if lang=="es" else "Inventory Capital")
    st.caption("Dónde está invertido el dinero y cuánto está inmovilizado en exceso. Las monedas nunca se mezclan." if lang=="es" else "Where money is invested and how much is tied up in excess. Currencies are never mixed.")
    cv=view.copy()
    cv["Currency"]=cv["Currency"].astype("string").fillna("").str.upper().replace({"":"Sin moneda" if lang=="es" else "Unspecified"})
    cur=cv.groupby("Currency").agg(Inventario=("Inventory_value","sum"),Exceso=("Excess_value","sum")).reset_index()
    for _,r in cur.iterrows():
        c1,c2,c3=st.columns(3)
        c1.metric(f"{r.Currency} · "+("Inventario" if lang=="es" else "Inventory"),f"{r.Inventario:,.0f}")
        c2.metric(f"{r.Currency} · "+("Exceso" if lang=="es" else "Excess"),f"{r.Exceso:,.0f}")
        c3.metric("% "+("capital en exceso" if lang=="es" else "capital in excess"),f"{(r.Exceso/r.Inventario*100 if r.Inventario else 0):.1f}%")
    dims=[c for c in ["Category","Supplier","Location"] if c in cv.columns]
    if dims:
        dim=st.selectbox("Agrupar por" if lang=="es" else "Group by",dims)
        g=cv.groupby([dim,"Currency"],dropna=False).agg(SKUs=("SKU","nunique"),Inventario=("Inventory_value","sum"),Exceso=("Excess_value","sum")).reset_index().sort_values("Inventario",ascending=False)
        g["Inventario"]=g["Inventario"].map(lambda x:f"{x:,.0f}"); g["Exceso"]=g["Exceso"].map(lambda x:f"{x:,.0f}")
        st.dataframe(g,use_container_width=True,hide_index=True)
    st.subheader("Top SKU por capital inmovilizado" if lang=="es" else "Top SKUs by tied-up capital")
    top=cv.sort_values("Excess_value",ascending=False).head(25).copy()
    top["Valor inventario"]=top["Inventory_value"].map(lambda x:f"{x:,.0f}"); top["Exceso"]=top["Excess_value"].map(lambda x:f"{x:,.0f}")
    st.dataframe(top[["SKU","Currency","Valor inventario","Exceso","Category","Action"]],use_container_width=True,hide_index=True)

else:
    st.title("Simulador" if lang=="es" else "Simulator")
    st.caption("Aplica un escenario al portafolio completo. Para simular un SKU específico, ábrelo desde Acciones." if lang=="es" else "Apply a scenario to the full portfolio. To simulate one SKU, open it from Actions.")
    with st.form("portfolio_scenario"):
        s1,s2,s3=st.columns(3)
        sales_pct=s1.number_input("Cambio esperado en ventas (%)" if lang=="es" else "Expected sales change (%)",-100.0,500.0,float(st.session_state.demand_change*100),1.0)
        lead_days=s2.number_input("Cambio en tiempo de entrega (días)" if lang=="es" else "Lead-time change (days)",-365,365,int(st.session_state.lead_delay),1)
        coverage=s3.number_input("Cobertura objetivo (semanas)" if lang=="es" else "Target coverage (weeks)",1,52,int(st.session_state.review_weeks),1)
        apply_all=st.form_submit_button("Aplicar escenario" if lang=="es" else "Apply scenario",type="primary",use_container_width=True)
    if apply_all:
        st.session_state.demand_change=float(sales_pct)/100; st.session_state.lead_delay=int(lead_days); st.session_state.review_weeks=int(coverage)
        nr,np=analyze(sales,items,po,demand_change=st.session_state.demand_change,lead_delay=st.session_state.lead_delay,review_weeks=st.session_state.review_weeks)
        st.session_state.result=nr; st.session_state.projection=np; st.rerun()
    st.markdown(f"**{'Escenario actual' if lang=='es' else 'Current scenario'}:** {st.session_state.demand_change:+.0%} {'ventas' if lang=='es' else 'sales'} · {st.session_state.lead_delay:+d} {'días lead time' if lang=='es' else 'lead-time days'} · {st.session_state.review_weeks} {'semanas cobertura' if lang=='es' else 'weeks coverage'}")
