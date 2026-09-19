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
</style>
""", unsafe_allow_html=True)

SALES_TARGETS=['SKU','PERIOD_START','PERIOD_END','QUANTITY','LOCATION','CUSTOMER']
ITEM_TARGETS=['SKU','DESCRIPTION','ON_HAND','UNIT_COST','LEAD_TIME_DAYS','MOQ','ORDER_MULTIPLE','SUPPLIER','CATEGORY','LOCATION','SERVICE_LEVEL','TARGET_WOS']
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
"UNIT_COST":"Costo unitario","LEAD_TIME_DAYS":"Tiempo de entrega (días)","MOQ":"Compra mínima (MOQ)",
"ORDER_MULTIPLE":"Múltiplo de compra","SUPPLIER":"Proveedor","CATEGORY":"Categoría","SERVICE_LEVEL":"Nivel de servicio",
"TARGET_WOS":"Semanas objetivo","PO_NUMBER":"Orden de compra","EXPECTED_DATE":"Fecha esperada"},
"en":{"SKU":"SKU / Item code","PERIOD_START":"Start date","PERIOD_END":"End date","QUANTITY":"Sales quantity",
"LOCATION":"Location","CUSTOMER":"Customer","DESCRIPTION":"Description","ON_HAND":"Current inventory",
"UNIT_COST":"Unit cost","LEAD_TIME_DAYS":"Lead time (days)","MOQ":"Minimum order qty (MOQ)",
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
st.markdown("**Siguiente paso:** valida la información antes de ejecutar el análisis." if lang=="es" else "**Next step:** validate the information before running the analysis.")
if st.button(validate_label,type="primary",use_container_width=True):
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
    if all_ok: st.session_state.stage=max(st.session_state.stage,3)

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
    if st.button(tr(lang,"analyze"),type="primary",use_container_width=True):
        if "PERIOD_START" not in sales:
            sales["PERIOD_START"]=pd.Timestamp.today()
        if "PERIOD_END" not in sales: sales["PERIOD_END"]=sales["PERIOD_START"]
        for c,val in [("DESCRIPTION",""),("UNIT_COST",0),("LEAD_TIME_DAYS",0),("MOQ",0),("ORDER_MULTIPLE",1),("SERVICE_LEVEL",.97),("TARGET_WOS",10)]:
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

# ---------- V12: Exception Management & SKU Detail ----------
# Normalize presentation fields and create an auditable priority ranking.
view=result.copy()
view["Purchase_value"]=pd.to_numeric(view.get("Purchase_value",0),errors="coerce").fillna(0)
view["Excess_value"]=pd.to_numeric(view.get("Excess_value",0),errors="coerce").fillna(0)
view["Recommended_qty"]=pd.to_numeric(view.get("Recommended_qty",0),errors="coerce").fillna(0)
view["Forecast_weekly"]=pd.to_numeric(view.get("Forecast_weekly",0),errors="coerce").fillna(0)
view["On_hand"]=pd.to_numeric(view.get("On_hand",0),errors="coerce").fillna(0)

def priority_reason(r):
    reasons=[]
    if bool(r.get("Expedite",False)): reasons.append("quiebre antes de reposición normal" if lang=="es" else "stockout before normal replenishment")
    if pd.notna(r.get("Stockout")): reasons.append(("quiebre "+fmt_date(r.get("Stockout"))) if lang=="es" else ("stockout "+fmt_date(r.get("Stockout"))))
    if r.get("Recommended_qty",0)>0: reasons.append((f"compra sugerida {r.get('Recommended_qty',0):,.0f}") if lang=="es" else (f"suggested buy {r.get('Recommended_qty',0):,.0f}"))
    if r.get("Excess_value",0)>0: reasons.append((f"${r.get('Excess_value',0):,.0f} en exceso") if lang=="es" else (f"${r.get('Excess_value',0):,.0f} excess"))
    return " · ".join(reasons[:3]) or ("monitorear" if lang=="es" else "monitor")

def urgency_bucket(r):
    if bool(r.get("Expedite",False)): return 1
    if r.get("Recommended_qty",0)>0: return 2
    if r.get("Excess_value",0)>0: return 3
    return 4

view["_bucket"]=view.apply(urgency_bucket,axis=1)
# Within each action class, nearer stockouts and larger financial exposure rise first.
view["_stockout_sort"]=pd.to_datetime(view.get("Stockout"),errors="coerce").fillna(pd.Timestamp("2262-01-01"))
view["_impact"]=view[["Purchase_value","Excess_value"]].max(axis=1)
view=view.sort_values(["_bucket","_stockout_sort","_impact"],ascending=[True,True,False]).reset_index(drop=True)
view["Priority_rank"]=range(1,len(view)+1)
view["Priority_reason"]=view.apply(priority_reason,axis=1)
def action_category(r):
    if bool(r.get("Expedite",False)): return "Urgente" if lang=="es" else "Urgent"
    if r.get("Recommended_qty",0)>0: return "Comprar pronto" if lang=="es" else "Buy soon"
    if r.get("Excess_value",0)>0: return "Exceso" if lang=="es" else "Excess"
    return "Monitorear" if lang=="es" else "Monitor"
view["Category"]=view.apply(action_category,axis=1)

urgent=int((view["_bucket"]==1).sum())
buysoon=int((view["_bucket"]==2).sum())
excess=int((view["_bucket"]==3).sum())
excess_value=float(view.Excess_value.sum())
purchase_value=float(view.Purchase_value.sum())

st.markdown('<div class="enterprise-bar">INVENTORY COPILOT&nbsp;&nbsp; | &nbsp;&nbsp;ACTION CENTER&nbsp;&nbsp; | &nbsp;&nbsp;INVENTORY HEALTH</div>',unsafe_allow_html=True)
st.title("Centro de acciones" if lang=="es" else "Action Center")
st.caption(("El sistema prioriza las excepciones para que no tengas que revisar cada SKU." if lang=="es"
            else "The system prioritizes exceptions so you do not have to review every SKU."))

k1,k2,k3,k4,k5=st.columns(5)
k1.metric("Acción urgente" if lang=="es" else "Urgent action",urgent)
k2.metric("Comprar pronto" if lang=="es" else "Buy soon",buysoon)
k3.metric("Con exceso" if lang=="es" else "Excess",excess)
k4.metric("Valor en exceso" if lang=="es" else "Excess value",f"${excess_value:,.0f}")
k5.metric("Compras sugeridas" if lang=="es" else "Suggested purchases",f"${purchase_value:,.0f}")

st.subheader("Acciones prioritarias" if lang=="es" else "Priority actions")
f1,f2=st.columns([2,1])
search=f1.text_input("Buscar SKU" if lang=="es" else "Search SKU",placeholder="A100")
category_options=(["Todas","Urgente","Comprar pronto","Exceso","Monitorear"] if lang=="es" else ["All","Urgent","Buy soon","Excess","Monitor"])
filter_label=f2.selectbox("Categoría" if lang=="es" else "Category",category_options)

filtered=view.copy()
if search:
    filtered=filtered[filtered["SKU"].astype(str).str.contains(search,case=False,na=False)]
if filter_label not in ["Todas","All"]:
    filtered=filtered[filtered["Category"]==filter_label]

top=filtered.head(25).copy()
top["Ranking"]=top["Priority_rank"]
top["SKU"]=top["SKU"].astype(str)
top["Categoría"]=top["Category"]
top["Acción"]=top["Action"]
top["Cantidad"]=top["Recommended_qty"].round(0).map(lambda x:f"{x:,.0f}")
top["Impacto $"]=top["_impact"].map(lambda x:f"${x:,.0f}")
top["Quiebre"]=top["Stockout"].apply(fmt_date)
top["Confianza"]=top["Confidence"]
display_cols=["Ranking","Categoría","SKU","Acción","Cantidad","Impacto $","Quiebre","Confianza"]
st.dataframe(top[display_cols],use_container_width=True,hide_index=True,height=min(850,80+35*max(1,len(top))))
if len(filtered)>25:
    st.caption((f"Mostrando las 25 acciones más prioritarias de {len(filtered):,} resultados." if lang=="es"
                else f"Showing the top 25 priority actions out of {len(filtered):,} results."))

st.divider()
sku_options=filtered["SKU"].astype(str).tolist() if len(filtered) else view["SKU"].astype(str).tolist()
dc1,dc2=st.columns([4,1])
selected=dc1.selectbox("Detalle de SKU" if lang=="es" else "SKU detail",sku_options)
open_detail=dc2.button("Abrir →" if lang=="es" else "Open →",type="primary",use_container_width=True)
if open_detail:
    st.session_state.detail_sku=selected
    st.session_state.page="detail"
    st.rerun()

if "page" not in st.session_state: st.session_state.page="action"
if "detail_sku" not in st.session_state: st.session_state.detail_sku=selected

# Streamlit reruns top-to-bottom, so detail view is rendered below and visually separated.
if st.session_state.page=="detail":
    st.divider()
    back=st.button("← Volver al Centro de acciones" if lang=="es" else "← Back to Action Center")
    if back:
        st.session_state.page="action"
        st.rerun()
    sku=st.session_state.detail_sku
    r=view[view["SKU"].astype(str)==str(sku)].iloc[0]
    st.markdown(f"## {sku}  ·  {r.Category}  ·  Ranking #{int(r.Priority_rank)}")
    st.markdown(f"### {r.Action}")
    d1,d2,d3,d4,d5=st.columns(5)
    d1.metric("Inventario" if lang=="es" else "Inventory",f"{r.On_hand:,.0f}")
    d2.metric("Demanda / semana" if lang=="es" else "Demand / week",f"{r.Forecast_weekly:,.1f}")
    wos=(r.On_hand/r.Forecast_weekly) if r.Forecast_weekly>0 else None
    d3.metric("Semanas inventario" if lang=="es" else "Weeks of supply",f"{wos:.1f}" if wos is not None else "—")
    d4.metric("Cantidad sugerida" if lang=="es" else "Suggested qty",f"{r.Recommended_qty:,.0f}")
    d5.metric("Confianza" if lang=="es" else "Confidence",str(r.Confidence))
    st.info(("Por qué está priorizado: " if lang=="es" else "Why it is prioritized: ")+str(r.Priority_reason))

    tabs=st.tabs(["Proyección","Forecast","PO abiertas","Explicación"] if lang=="es" else ["Projection","Forecast","Open POs","Explanation"])
    with tabs[0]:
        sku_proj=projection[projection["SKU"].astype(str)==str(sku)].copy()
        if len(sku_proj):
            date_col=next((c for c in sku_proj.columns if "week" in c.lower() or "date" in c.lower()),None)
            inv_col=next((c for c in sku_proj.columns if "ending" in c.lower() or "projected" in c.lower()),None)
            ss_col=next((c for c in sku_proj.columns if "safety" in c.lower()),None)
            if date_col and inv_col:
                chart=sku_proj[[date_col,inv_col]+([ss_col] if ss_col else [])].copy()
                chart=chart.set_index(date_col)
                st.line_chart(chart)
            st.dataframe(sku_proj,use_container_width=True,hide_index=True)
        else: st.caption("Sin proyección disponible." if lang=="es" else "No projection available.")
    with tabs[1]:
        st.metric("Modelo",str(r.Model))
        st.metric("Error histórico" if lang=="es" else "Historical error",f"{float(r.Forecast_error):.1%}" if pd.notna(r.Forecast_error) else "—")
        st.write(("Demanda esperada semanal: " if lang=="es" else "Expected weekly demand: ")+f"{r.Forecast_weekly:,.1f}")
    with tabs[2]:
        sku_po=po[po["SKU"].astype(str)==str(sku)].copy() if "SKU" in po.columns else pd.DataFrame()
        if len(sku_po): st.dataframe(sku_po,use_container_width=True,hide_index=True)
        else: st.caption("No hay PO abiertas para este SKU." if lang=="es" else "No open POs for this SKU.")
    with tabs[3]:
        st.write(str(r.Explanation))
        st.write(("Acción recomendada: " if lang=="es" else "Recommended action: ")+str(r.Action))
        st.write(("Posible quiebre: " if lang=="es" else "Possible stockout: ")+fmt_date(r.Stockout))

    st.subheader("Simular este SKU" if lang=="es" else "Simulate this SKU")
    st.caption("Los cambios recalculan el portafolio, pero aquí puedes evaluar cómo cambia este SKU." if lang=="es" else "Changes recalculate the portfolio, while this view lets you evaluate this SKU.")
    with st.form("sku_scenario_form"):
        q1,q2,q3=st.columns(3)
        sales_pct=q1.number_input("Ventas (%)" if lang=="es" else "Sales (%)",-100.0,500.0,float(st.session_state.demand_change*100),1.0)
        lead_days=q2.number_input("Lead time (días)" if lang=="es" else "Lead time (days)",-365,365,int(st.session_state.lead_delay),1)
        coverage=q3.number_input("Cobertura (semanas)" if lang=="es" else "Coverage (weeks)",1,52,int(st.session_state.review_weeks),1)
        apply_scenario=st.form_submit_button("Aplicar escenario" if lang=="es" else "Apply scenario",type="primary")
    if apply_scenario:
        st.session_state.demand_change=float(sales_pct)/100
        st.session_state.lead_delay=int(lead_days)
        st.session_state.review_weeks=int(coverage)
        nr,np=analyze(sales,items,po,demand_change=st.session_state.demand_change,lead_delay=st.session_state.lead_delay,review_weeks=st.session_state.review_weeks)
        st.session_state.result=nr; st.session_state.projection=np
        st.rerun()
