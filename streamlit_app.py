from io import BytesIO
import pandas as pd
import streamlit as st
from engine import analyze
from importer import suggest_mapping, apply_mapping, validate_dataset
from i18n import tr

st.set_page_config(page_title="Inventory Copilot", page_icon="📦", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
.block-container {padding-top: 1.5rem; padding-bottom: 3rem; max-width: 1450px;}
.hero {padding: 1.35rem 1.5rem; border:1px solid #e5e7eb; border-radius:18px; margin-bottom:1rem;}
.hero h1 {margin:0 0 .25rem 0; font-size:2rem;}
.hero p {margin:0; color:#5f6368; font-size:1.03rem;}
.step {font-weight:700; font-size:.92rem; color:#5f6368; margin-bottom:.35rem;}
.card {padding:1rem 1.1rem; border:1px solid #e5e7eb; border-radius:14px; min-height:120px;}
.small {color:#6b7280; font-size:.9rem;}
div[data-testid="stMetric"] {border:1px solid #e5e7eb; padding:14px; border-radius:14px;}
</style>
""", unsafe_allow_html=True)

SALES_TARGETS=['SKU','PERIOD_START','PERIOD_END','QUANTITY','LOCATION','CUSTOMER']
ITEM_TARGETS=['SKU','DESCRIPTION','ON_HAND','UNIT_COST','LEAD_TIME_DAYS','MOQ','ORDER_MULTIPLE','SUPPLIER','CATEGORY','LOCATION','SERVICE_LEVEL','TARGET_WOS']
PO_TARGETS=['SKU','PO_NUMBER','QUANTITY','EXPECTED_DATE','SUPPLIER']

for k,v in {"stage":1, "result":None, "projection":None}.items():
    if k not in st.session_state: st.session_state[k]=v

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

def mapper(title,df,targets,key):
    st.markdown(f"#### {title}")
    suggestion=suggest_mapping(df.columns,targets)
    options=['— No mapear —']+list(df.columns)
    mapping={}
    cols=st.columns(3)
    for i,t in enumerate(targets):
        default=suggestion.get(t)
        idx=options.index(default) if default in options else 0
        mapping[t]=cols[i%3].selectbox(t,options,index=idx,key=f'{key}_{t}')
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
    st.markdown("**Escenario**")
    demand_change=st.slider("Cambio esperado en ventas",-50,100,0,5,help="Prueba qué ocurriría si las ventas suben o bajan.")/100
    lead_delay=st.slider("Cambio en tiempo de entrega (días)",-30,90,0,7)
    review_weeks=st.slider("Cobertura deseada después de recibir",1,12,4)
    st.caption("Estos controles permiten probar escenarios sin cambiar tu archivo.")

st.markdown(f"""<div class="hero"><h1>{tr(lang,"title")}</h1><p>{tr(lang,"subtitle")}</p></div>""",unsafe_allow_html=True)

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
st.session_state.stage=max(st.session_state.stage,2)

st.markdown('<div class="step">PASO 1 DE 3</div>',unsafe_allow_html=True)
st.subheader("¿Dónde está cada tipo de información?")
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
st.caption("Ya hicimos una primera sugerencia automática. Cambia solamente lo que no coincida con tus datos.")

tab1,tab2,tab3=st.tabs(["Ventas","Inventario / Items","PO abiertas"])
with tab1: sales,_=mapper(tr(lang,"sales"),sheets[sales_sheet],SALES_TARGETS,"sales")
with tab2: items,_=mapper("Maestro de artículos",sheets[item_sheet],ITEM_TARGETS,"items")
with tab3: po,_=mapper(tr(lang,"po"),sheets[po_sheet],PO_TARGETS,"po")

st.divider()
st.markdown('<div class="step">PASO 3 DE 3</div>',unsafe_allow_html=True)
st.subheader(tr(lang,"review"))
all_ok=True
checks=[]
for name,df,kind in [("Ventas",sales,"sales"),("Inventario / Items",items,"items"),("PO abiertas",po,"po")]:
    issues=validate_dataset(df,kind)
    errors=[m for lvl,m in issues if lvl=="error"]
    warnings=[m for lvl,m in issues if lvl=="warning"]
    checks.append((name,errors,warnings))
    if errors: all_ok=False

cols=st.columns(3)
for col,(name,errors,warnings) in zip(cols,checks):
    with col:
        st.markdown(f"**{name}**")
        if errors:
            for m in errors: st.error(m)
        elif warnings:
            st.warning("Datos utilizables, con observaciones.")
            for m in warnings: st.caption("• "+m)
        else:
            st.success("Listo para analizar")

if all_ok:
    st.session_state.stage=max(st.session_state.stage,3)
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
else:
    st.error("Corrige los campos marcados antes de ejecutar el análisis.")

if st.session_state.result is None:
    st.stop()

result=st.session_state.result
projection=st.session_state.projection
st.divider()
st.header(tr(lang,"dashboard"))
st.caption("Primero mostramos decisiones. Los términos técnicos quedan disponibles cuando los necesites.")

urgent=int((result.Priority==1).sum())
soon=int((result.Priority==2).sum())
excess_count=int((result.Situation=="Exceso").sum())
excess_value=float(result.Excess_value.sum())
purchase_value=float(result.Purchase_value.sum())

a,b,c,d,e=st.columns(5)
a.metric("Necesitan acción urgente",urgent)
b.metric("Comprar pronto",soon)
c.metric("Productos con exceso",excess_count)
d.metric("Dinero estimado en exceso",f"${excess_value:,.0f}")
e.metric("Compras sugeridas",f"${purchase_value:,.0f}")

st.subheader(tr(lang,"attention"))
for _,r in result.iterrows():
    icon="🔴" if r.Priority==1 else "🟠" if r.Priority==2 else "🟢" if r.Priority==3 else "🟡"
    with st.expander(f"{icon} {r.SKU} — {r.Situation} · {r.Action}", expanded=r.Priority<=2):
        x,y,z=st.columns(3)
        x.metric("Inventario actual",f"{r.On_hand:,.0f}")
        y.metric("Demanda esperada / semana",f"{r.Forecast_weekly:,.1f}")
        z.metric("Confianza",r.Confidence)
        st.write(r.Explanation)
        if r.Stockout is not None and not pd.isna(r.Stockout):
            st.write(f"**Posible quiebre:** {fmt_date(r.Stockout)}")
        if r.Recommended_qty:
            st.write(f"**Cantidad sugerida:** {r.Recommended_qty:,.0f} unidades · valor aproximado ${r.Purchase_value:,.0f}")
        if r.Expedite:
            st.warning("El lead time normal podría ser demasiado largo. Revisa expedite, transferencia entre ubicaciones, sustituto o una fecha de proveedor más rápida.")

st.subheader(tr(lang,"all"))
show=result[["SKU","Situation","Action","Recommended_qty","Purchase_value","Excess_value","Stockout","Confidence"]].copy()
show.columns=["SKU","Situación","Qué hacer","Cantidad sugerida","Valor compra","Valor en exceso","Posible quiebre","Confianza"]
st.dataframe(show,hide_index=True,use_container_width=True)

st.subheader(tr(lang,"detail"))
sku=st.selectbox("Selecciona SKU",result.SKU.tolist(),key="detail_sku")
r=result[result.SKU==sku].iloc[0]
left,right=st.columns([1,2])
with left:
    st.markdown(f"### {sku}")
    st.write(f"**{r.Action}**")
    st.write(r.Explanation)
    st.caption(f"Modelo de pronóstico: {r.Model} · Error histórico: {r.Forecast_error:.1%}" if not pd.isna(r.Forecast_error) else f"Modelo: {r.Model}")
    with st.expander("¿Qué significan estos términos?"):
        st.write("**Inventario de seguridad:** inventario extra para protegerte de variaciones en ventas.")
        st.write("**Lead time:** tiempo que demora el proveedor desde que compras hasta que recibes.")
        st.write("**Error histórico del pronóstico:** cuánto se equivocó el modelo al probarse con ventas anteriores. Menor suele ser mejor.")
with right:
    p=projection[projection.SKU==sku].copy().set_index("Week")[["Ending","Safety Stock"]]
    p.columns=["Inventario proyectado","Inventario de seguridad"]
    st.line_chart(p)


st.divider()
st.header(tr(lang,"executive"))
st.caption("Una lectura rápida para decidir dónde actuar hoy, sin necesidad de conversar con el sistema.")

urgent_df=result[result.Priority==1].sort_values("Purchase_value",ascending=False)
buy_df=result[result.Recommended_qty>0].sort_values(["Priority","Purchase_value"],ascending=[True,False])
excess_df=result[result.Excess_value>0].sort_values("Excess_value",ascending=False)
risk_df=result[result.Stockout.notna()].sort_values("Stockout")

tabs=st.tabs([f"🛒 {tr(lang,'whatbuy')}",f"⚠️ {tr(lang,'risk')}",f"📦 {tr(lang,'excess')}",f"📈 {tr(lang,'forecast')}",f"🧪 {tr(lang,'simulator')}"])
with tabs[0]:
    if buy_df.empty:
        st.success("No hay compras nuevas sugeridas con los datos y parámetros actuales.")
    else:
        for _,r in buy_df.iterrows():
            severity="URGENTE" if r.Priority==1 else "REVISAR"
            st.markdown(f"### {severity} · {r.SKU}")
            c1,c2,c3,c4=st.columns(4)
            c1.metric("Cantidad sugerida",f"{r.Recommended_qty:,.0f}")
            c2.metric("Valor estimado",f"${r.Purchase_value:,.0f}")
            c3.metric("Inventario actual",f"{r.On_hand:,.0f}")
            c4.metric("Confianza",r.Confidence)
            st.write(f"**Por qué:** {r.Explanation}")
            if r.Expedite:
                st.warning("La reposición normal podría llegar demasiado tarde. Revisa una entrega más rápida, transferencia o sustituto.")
            st.divider()

with tabs[1]:
    if risk_df.empty:
        st.success("No hay quiebres proyectados en el horizonte analizado.")
    else:
        risk_show=risk_df[["SKU","Stockout","On_hand","Forecast_weekly","Action","Confidence"]].copy()
        risk_show.columns=["SKU","Posible quiebre","Inventario actual","Demanda semanal","Acción","Confianza"]
        st.dataframe(risk_show,use_container_width=True,hide_index=True)
        st.caption("Una fecha de quiebre es una proyección basada en demanda, inventario y llegadas conocidas; no es una garantía.")

with tabs[2]:
    if excess_df.empty:
        st.success("No se detectó exceso de inventario con los parámetros actuales.")
    else:
        total=float(excess_df.Excess_value.sum())
        st.metric("Valor estimado atrapado en exceso",f"${total:,.0f}")
        excess_show=excess_df[["SKU","On_hand","Forecast_weekly","Excess_value","Action","Confidence"]].copy()
        excess_show.columns=["SKU","Inventario","Demanda semanal","Valor en exceso","Acción","Confianza"]
        st.dataframe(excess_show,use_container_width=True,hide_index=True)

with tabs[3]:
    fc=result[["SKU","Forecast_weekly","Model","Forecast_error","Confidence"]].copy()
    fc.columns=["SKU","Demanda esperada / semana","Modelo elegido","Error histórico","Confianza"]
    st.dataframe(fc,use_container_width=True,hide_index=True)
    st.caption("El sistema compara métodos de forecast y utiliza el de mejor desempeño histórico disponible para cada SKU.")

with tabs[4]:
    st.markdown("### ¿Qué pasa si cambia el negocio?")
    st.write("Usa los controles de **Escenario** en la barra lateral para cambiar ventas, lead time y cobertura deseada. El motor vuelve a calcular las decisiones usando esos supuestos.")
    sc1,sc2,sc3=st.columns(3)
    sc1.metric("Cambio de ventas",f"{demand_change:+.0%}")
    sc2.metric("Cambio de lead time",f"{lead_delay:+d} días")
    sc3.metric("Cobertura deseada",f"{review_weeks} semanas")
    st.info("Los escenarios son simulaciones para apoyar decisiones; no modifican tu archivo original.")

st.divider()
st.subheader("Cómo leer una recomendación")
c1,c2,c3,c4=st.columns(4)
c1.markdown("**1 · Acción**\n\nQué deberías revisar o hacer.")
c2.markdown("**2 · Cantidad**\n\nCuánto sugiere el motor.")
c3.markdown("**3 · Motivo**\n\nQué riesgo o exceso genera la acción.")
c4.markdown("**4 · Evidencia**\n\nForecast, inventario, fechas y confianza.")

st.caption("Inventory Copilot V7 · Los cálculos y recomendaciones provienen del motor determinístico. No se requiere conexión a una API de IA.")
