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
.hero {background:white;padding:2rem 2.25rem;border:1px solid #E5EAF0;border-radius:16px;margin-bottom:1rem;box-shadow:0 8px 30px rgba(15,23,42,.05);}
.hero h1 {margin:0 0 .45rem 0;font-size:2.15rem;color:#0F172A;letter-spacing:-.035em;}
.hero p {margin:0;color:#64748B;font-size:1.02rem;line-height:1.55;}
.step {font-weight:700;font-size:.78rem;color:#52606D;letter-spacing:.05em;margin-bottom:.25rem;}
.card {background:white;padding:.8rem 1rem;border:1px solid #D9E2EC;border-radius:4px;min-height:105px;}
.small {color:#6B7280;font-size:.86rem;}
div[data-testid="stMetric"] {background:white;border:1px solid #D9E2EC;border-radius:4px;padding:10px 12px;}
div[data-testid="stMetricLabel"] {font-size:.78rem;text-transform:uppercase;letter-spacing:.03em;}
div[data-testid="stMetricValue"] {color:#16324F;}
.stButton>button {border-radius:10px;font-weight:650;min-height:44px;}
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
    if name.endswith(('.csv','.txt','.tsv')):
        try:
            return {'DATA':pd.read_csv(BytesIO(raw),sep=None,engine='python')}
        except Exception:
            return {'DATA':pd.read_csv(BytesIO(raw))}
    xls=pd.ExcelFile(BytesIO(raw))
    return {sheet:pd.read_excel(xls,sheet) for sheet in xls.sheet_names}


def _norm_name(x):
    import unicodedata,re
    x=unicodedata.normalize("NFKD",str(x)).encode("ascii","ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+"," ",x).strip()

def _guess_col(columns, aliases):
    norms={c:_norm_name(c) for c in columns}
    for alias in aliases:
        a=_norm_name(alias)
        for c,n in norms.items():
            if n==a: return c
    for alias in aliases:
        a=_norm_name(alias)
        for c,n in norms.items():
            if a in n or n in a: return c
    return None


def _parse_period_series(series, period_type="Auto"):
    """Turn common SME date/month/week fields into usable period starts."""
    raw=series.astype("string").str.strip()
    dt=pd.to_datetime(raw,errors="coerce",dayfirst=False)
    # Spanish/English month names without a year: use current year.
    months={
      "enero":1,"ene":1,"january":1,"jan":1,"febrero":2,"feb":2,"february":2,
      "marzo":3,"mar":3,"march":3,"abril":4,"abr":4,"april":4,"mayo":5,"may":5,
      "junio":6,"jun":6,"june":6,"julio":7,"jul":7,"july":7,"agosto":8,"ago":8,"august":8,"aug":8,
      "septiembre":9,"setiembre":9,"sep":9,"sept":9,"september":9,
      "octubre":10,"oct":10,"october":10,"noviembre":11,"nov":11,"november":11,
      "diciembre":12,"dic":12,"dec":12,"december":12
    }
    missing=dt.isna()
    if missing.any():
        low=raw.str.lower()
        month_num=low.map(months)
        fill=month_num.notna() & missing
        if fill.any():
            year=pd.Timestamp.today().year
            dt.loc[fill]=pd.to_datetime(dict(year=[year]*int(fill.sum()),month=month_num[fill].astype(int),day=[1]*int(fill.sum())))
    # "Semana 12", "Week 12", "W12" -> current ISO year.
    missing=dt.isna()
    if missing.any():
        wk=raw.str.extract(r'(?i)(?:semana|week|wk|w)?\s*[-#:]?\s*(\d{1,2})')[0]
        fill=wk.notna() & missing
        if fill.any():
            year=pd.Timestamp.today().year
            vals=[]
            for w in wk[fill].astype(int):
                try: vals.append(pd.Timestamp.fromisocalendar(year,int(w),1))
                except Exception: vals.append(pd.NaT)
            dt.loc[fill]=vals
    return dt

def build_long_dataset(df, product_col, period_col, qty_col, onhand_col=None,
                       period_type="Auto", cost_col=None, currency_col=None,
                       lead_col=None, supplier_col=None, location_col=None):
    """Normalize transactional/database-style rows into canonical datasets."""
    base=df.copy().dropna(how="all")
    base=base[base[product_col].notna()].copy()
    base[product_col]=base[product_col].astype(str).str.strip()
    base=base[base[product_col].ne("")]
    base["_period"]=_parse_period_series(base[period_col],period_type)
    base["_qty"]=pd.to_numeric(base[qty_col],errors="coerce").fillna(0)
    base=base[base["_period"].notna()].copy()
    # Stable internal IDs: repeated descriptions become the same product.
    products=pd.Index(base[product_col].drop_duplicates())
    id_map={v:f"ITEM-{i:04d}" for i,v in enumerate(products,1)}
    base["SKU"]=base[product_col].map(id_map)

    # Aggregate sales; repeated transactional rows are intentionally summed.
    sales=(base.groupby(["SKU","_period"],as_index=False)["_qty"].sum()
           .rename(columns={"_period":"PERIOD_START","_qty":"QUANTITY"}))
    sales["PERIOD_END"]=sales["PERIOD_START"]

    def first_nonblank(g,col,default=""):
        if not col or col not in g: return default
        x=g[col].dropna()
        if len(x)==0: return default
        x=x.astype(str).str.strip()
        x=x[x.ne("")]
        return x.iloc[-1] if len(x) else default

    item_rows=[]
    for product,g in base.groupby(product_col,sort=False):
        # Current inventory is NOT summed across repeated sales transactions.
        oh=0.0
        if onhand_col and onhand_col in g:
            nums=pd.to_numeric(g[onhand_col],errors="coerce").dropna()
            oh=float(nums.iloc[-1]) if len(nums) else 0.0
        cost=0.0
        if cost_col and cost_col in g:
            nums=pd.to_numeric(g[cost_col],errors="coerce").dropna()
            cost=float(nums.iloc[-1]) if len(nums) else 0.0
        lead=0.0
        if lead_col and lead_col in g:
            nums=pd.to_numeric(g[lead_col],errors="coerce").dropna()
            lead=float(nums.iloc[-1]) if len(nums) else 0.0
        item_rows.append({
          "SKU":id_map[product],"DESCRIPTION":product,"ON_HAND":oh,
          "UNIT_COST":cost,"CURRENCY":first_nonblank(g,currency_col,"").upper(),
          "LEAD_TIME_DAYS":lead,"MOQ":0.0,"ORDER_MULTIPLE":1.0,
          "SUPPLIER":first_nonblank(g,supplier_col,""),
          "CATEGORY":"","LOCATION":first_nonblank(g,location_col,""),
          "SERVICE_LEVEL":.97,"TARGET_WOS":10.0
        })
    items=pd.DataFrame(item_rows)
    po=pd.DataFrame(columns=["SKU","PO_NUMBER","QUANTITY","EXPECTED_DATE","SUPPLIER"])
    return sales,items,po,base

def detect_single_table_shape(df):
    cols=list(df.columns)
    product=_guess_col(cols,["descripcion","description","producto","product","item description","material description","item","articulo","sku","part number"])
    period=_guess_col(cols,["fecha","date","mes","month","semana","week","periodo","period","posting date","sales date","invoice date","pgi date"])
    qty=_guess_col(cols,["venta","ventas","sales","quantity","qty","cantidad vendida","unidades vendidas","demand","shipped qty"])
    onhand=_guess_col(cols,["inventario actual","inventario","stock actual","stock","on hand","existencias","qoh"])
    if product and period and qty:
        return "long",{"product":product,"period":period,"qty":qty,"onhand":onhand}
    return "wide",{"product":product,"onhand":onhand}

def build_basic_dataset(df, desc_col, onhand_col, sales_cols):
    """Convert a tiny business spreadsheet into the canonical engine format."""
    base=df.copy().dropna(how="all")
    base=base[base[desc_col].notna()].copy()
    base[desc_col]=base[desc_col].astype(str).str.strip()
    base=base[base[desc_col].ne("")]
    base["SKU"]=[f"ITEM-{i:04d}" for i in range(1,len(base)+1)]
    items=pd.DataFrame({
        "SKU":base["SKU"],"DESCRIPTION":base[desc_col],
        "ON_HAND":pd.to_numeric(base[onhand_col],errors="coerce").fillna(0),
        "UNIT_COST":0.0,"CURRENCY":"","LEAD_TIME_DAYS":0.0,
        "MOQ":0.0,"ORDER_MULTIPLE":1.0,"SUPPLIER":"","CATEGORY":"",
        "LOCATION":"","SERVICE_LEVEL":.97,"TARGET_WOS":10.0
    })
    # Oldest -> newest in the order selected by the user.
    today=pd.Timestamp.today().normalize()
    periods=[today-pd.DateOffset(months=len(sales_cols)-1-i) for i in range(len(sales_cols))]
    rows=[]
    for _,r in base.iterrows():
        for col,dt in zip(sales_cols,periods):
            rows.append({"SKU":r["SKU"],"PERIOD_START":dt.replace(day=1),
                         "PERIOD_END":dt.replace(day=1)+pd.offsets.MonthEnd(0),
                         "QUANTITY":pd.to_numeric(pd.Series([r[col]]),errors="coerce").fillna(0).iloc[0]})
    sales=pd.DataFrame(rows)
    po=pd.DataFrame(columns=["SKU","PO_NUMBER","QUANTITY","EXPECTED_DATE","SUPPLIER"])
    return sales,items,po

def apply_basic_interpretation(result, items):
    """With no lead time/cost/PO, provide directional—not falsely precise—decisions."""
    out=result.copy()
    desc=items.set_index("SKU")["DESCRIPTION"].to_dict()
    out["Description"]=out["SKU"].map(desc)
    weekly=pd.to_numeric(out["Forecast_weekly"],errors="coerce").fillna(0)
    onhand=pd.to_numeric(out["On_hand"],errors="coerce").fillna(0)
    out["WOS"]=onhand/weekly.replace(0,pd.NA)
    def classify(r):
        w=r["WOS"]; f=r["Forecast_weekly"]
        if f<=0: return ("Monitorear","Sin demanda reciente; revisa si el producto sigue activo.")
        if pd.notna(w) and w<2: return ("Urgente","Cobertura menor a 2 semanas. Revisa reposición cuanto antes.")
        if pd.notna(w) and w<4: return ("Comprar pronto","Cobertura menor a 4 semanas. Revisa reposición.")
        if pd.notna(w) and w>12: return ("Exceso","Más de 12 semanas de cobertura con las ventas recientes.")
        return ("Monitorear","La cobertura reciente no muestra una excepción inmediata.")
    vals=out.apply(classify,axis=1,result_type="expand")
    out["Category"]=vals[0]; out["Situation"]=vals[0]; out["Action"]=vals[1]
    out["Recommended_qty"]=0.0; out["Purchase_value"]=0.0; out["Excess_value"]=0.0
    out["Expedite"]=False
    return out

def detect_analysis_level(items, po, basic_mode=False):
    if basic_mode: return 1
    has_cost="UNIT_COST" in items and pd.to_numeric(items["UNIT_COST"],errors="coerce").fillna(0).gt(0).any()
    has_lt="LEAD_TIME_DAYS" in items and pd.to_numeric(items["LEAD_TIME_DAYS"],errors="coerce").fillna(0).gt(0).any()
    has_supplier="SUPPLIER" in items and items["SUPPLIER"].astype("string").fillna("").str.strip().ne("").any()
    has_po=isinstance(po,pd.DataFrame) and len(po)>0 and "QUANTITY" in po and pd.to_numeric(po["QUANTITY"],errors="coerce").fillna(0).gt(0).any()
    if has_supplier or has_po: return 3
    if has_cost or has_lt: return 2
    return 1


def procurement_capabilities(items, po):
    """Explain what is available now and what each additional field unlocks."""
    def has_numeric(col):
        return isinstance(items,pd.DataFrame) and col in items and pd.to_numeric(items[col],errors="coerce").fillna(0).gt(0).any()
    def has_text(col):
        return isinstance(items,pd.DataFrame) and col in items and items[col].astype("string").fillna("").str.strip().ne("").any()
    caps={
      "lead_time":has_numeric("LEAD_TIME_DAYS"),
      "cost":has_numeric("UNIT_COST"),
      "currency":has_text("CURRENCY"),
      "supplier":has_text("SUPPLIER"),
      "moq":has_numeric("MOQ"),
      "multiple":has_numeric("ORDER_MULTIPLE") and pd.to_numeric(items["ORDER_MULTIPLE"],errors="coerce").fillna(1).gt(1).any(),
      "open_po":isinstance(po,pd.DataFrame) and not po.empty and "QUANTITY" in po and pd.to_numeric(po["QUANTITY"],errors="coerce").fillna(0).gt(0).any()
    }
    return caps

def render_unlock_more(items,po,lang="es"):
    caps=procurement_capabilities(items,po)
    missing=[]
    catalog=[
      ("lead_time","Tiempo de entrega","Lead time","Cuándo volver a comprar, riesgo de quiebre antes de recibir y urgencia de reposición.","When to reorder, pre-receipt stockout risk and replenishment urgency."),
      ("cost","Costo unitario","Unit cost","Valor del inventario, capital inmovilizado y priorización por impacto económico.","Inventory value, tied-up capital and financial-impact prioritization."),
      ("currency","Moneda","Currency","Totales financieros correctos sin mezclar USD, CLP, MXN u otras monedas.","Correct financial totals without mixing USD, CLP, MXN or other currencies."),
      ("supplier","Proveedor","Supplier","Consolidación de compras y exposición de inventario por proveedor.","Purchase consolidation and inventory exposure by supplier."),
      ("moq","Compra mínima (MOQ)","Minimum order quantity","Recomendaciones de compra que respetan el mínimo real del proveedor.","Purchase recommendations that respect supplier minimums."),
      ("multiple","Múltiplo de compra","Order multiple","Redondeo de recomendaciones a cajas, pallets o múltiplos realmente comprables.","Rounds recommendations to cases, pallets or actual purchasing multiples."),
      ("open_po","Órdenes abiertas + fecha esperada","Open POs + expected date","Evitar comprar dos veces y detectar órdenes que podrían llegar después del quiebre.","Avoid duplicate buying and detect orders that may arrive after a stockout.")
    ]
    for key,es,en,benefit_es,benefit_en in catalog:
        if not caps[key]: missing.append((key,es,en,benefit_es,benefit_en))
    if not missing:
        st.success("✓ Tus datos ya permiten un análisis avanzado de procurement." if lang=="es" else "✓ Your data already supports advanced procurement analysis.")
        return
    title="Mejora tu análisis" if lang=="es" else "Improve your analysis"
    st.markdown(f"### ✦ {title}")
    st.write("Inventory Copilot ya trabaja con lo que tienes. Si agregas algunos datos, puede pasar de detectar señales a recomendar decisiones de compra más completas." if lang=="es" else "Inventory Copilot already works with what you have. Add a few fields to move from signals to more complete purchasing recommendations.")
    # Recommend the highest-value next fields first.
    for i,(key,es,en,bes,ben) in enumerate(missing[:4],1):
        label=es if lang=="es" else en
        benefit=bes if lang=="es" else ben
        with st.expander(f"{'①②③④'[i-1]} {label}  ·  + desbloquea análisis"):
            st.write(benefit)
            if key=="lead_time":
                st.caption("Ejemplo: Producto A | 45 días" if lang=="es" else "Example: Product A | 45 days")
            elif key=="cost":
                st.caption("Ejemplo: Producto A | 12.50 | USD" if lang=="es" else "Example: Product A | 12.50 | USD")
            elif key=="open_po":
                st.caption("Ejemplo: Producto A | PO-1025 | 200 unidades | 15/10/2026" if lang=="es" else "Example: Product A | PO-1025 | 200 units | 2026-10-15")
    completed=sum(caps.values()); total=len(caps)
    st.progress(completed/total,text=(f"Madurez de datos de procurement: {completed}/{total} capacidades" if lang=="es" else f"Procurement data maturity: {completed}/{total} capabilities"))
    st.caption("No necesitas completar todo de una vez. Agrega el siguiente dato que tengas disponible y vuelve a analizar." if lang=="es" else "You do not need everything at once. Add the next field you have available and analyze again.")

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


CONCEPTS_ES={
 "WOS":("Semanas de inventario (WOS)","Cuántas semanas podría cubrir tu inventario actual al ritmo de venta estimado.","Ayuda a detectar si tienes muy poco inventario o demasiado dinero inmovilizado."),
 "Safety Stock":("Inventario de seguridad","Inventario adicional para protegerte de cambios en demanda o atrasos del proveedor.","Reduce el riesgo de quedarte sin producto cuando la realidad cambia."),
 "Reorder Point":("Punto para volver a comprar","Nivel en que conviene iniciar una compra considerando demanda y tiempo de entrega.","Ayuda a comprar antes de que sea demasiado tarde."),
 "Lead Time":("Tiempo de entrega","Días desde que compras hasta que el inventario está disponible.","Mientras mayor sea, antes debes tomar decisiones de reposición."),
 "Forecast":("Pronóstico de demanda","Estimación de cuánto podrías vender o consumir próximamente.","Es la base para calcular cuándo y cuánto comprar."),
 "Confidence":("Confianza del pronóstico","Indica qué tan consistente ha sido el comportamiento histórico usado para pronosticar.","Una confianza baja sugiere revisar la recomendación con mayor atención."),
 "Stockout":("Quiebre proyectado","Fecha estimada en que podrías quedarte sin inventario.","Permite actuar antes de perder ventas o interrumpir operaciones."),
 "Excess":("Exceso de inventario","Inventario por encima de la cobertura objetivo.","Muestra dónde puedes tener capital inmovilizado innecesariamente."),
 "Priority Score":("Puntaje de prioridad","Puntaje de 0 a 100 que ordena qué excepciones revisar primero.","No cambia la categoría; ayuda a enfocar tu tiempo donde hay mayor urgencia o impacto."),
 "MOQ":("Compra mínima (MOQ)","Cantidad mínima que el proveedor permite comprar.","Puede hacer que la compra ejecutable sea mayor que la necesidad calculada."),
 "Order Multiple":("Múltiplo de compra","Cantidad en la que debe redondearse una orden, por ejemplo cajas de 12.","Hace que la recomendación respete cómo realmente puedes comprar."),
}
CONCEPTS_EN={k:v for k,v in CONCEPTS_ES.items()}
def concept_strip(keys):
    cols=st.columns(min(3,len(keys)))
    for i,key in enumerate(keys):
        title,meaning,importance=(CONCEPTS_ES if lang=="es" else CONCEPTS_EN)[key]
        with cols[i%len(cols)]:
            st.markdown(f"**ⓘ {title}**")
            st.caption(meaning)
            st.caption(("Por qué importa: " if lang=="es" else "Why it matters: ")+importance)

# Language is available in both onboarding and results workspaces.
_lang_label=st.session_state.get("ui_language","Español")
lang="es" if _lang_label=="Español" else "en"

if st.session_state.result is None:
    st.markdown("<div style='text-align:center;margin:.4rem 0 1.2rem'><h1 style='font-size:2.55rem;margin-bottom:.35rem'>Entiende tu inventario.</h1><p style='color:#64748b;font-size:1.08rem'>Sube lo que tengas. Inventory Copilot se encarga del resto.</p></div>" if lang=="es" else "<div style='text-align:center;margin:.4rem 0 1.2rem'><h1 style='font-size:2.55rem;margin-bottom:.35rem'>Understand your inventory.</h1><p style='color:#64748b;font-size:1.08rem'>Upload what you have. Inventory Copilot will figure out the rest.</p></div>",unsafe_allow_html=True)
    st.markdown("### Comienza aquí" if lang=="es" else "### Start here")
    _lc1,_lc2=st.columns([1,2])
    with _lc1:
        language=st.selectbox("Idioma / Language",["Español","English"],index=0 if st.session_state.get("ui_language","Español")=="Español" else 1,key="language_center")
        st.session_state.ui_language=language
        lang="es" if language=="Español" else "en"
    with _lc2:
        st.caption("Flujo de preparación" if lang=="es" else "Preparation flow")
        _steps=["1 · Sube tu archivo","2 · Inventory Copilot lo interpreta","3 · Analiza"] if lang=="es" else ["1 · Upload your file","2 · Inventory Copilot understands it","3 · Analyze"]
        st.markdown("  →  ".join(_steps))
    st.divider()
    st.markdown(f"""<div class="hero"><h1>{tr(lang,"title")}</h1><p>{tr(lang,"subtitle")}</p></div>""",unsafe_allow_html=True)
    upload=st.file_uploader(tr(lang,"upload"),type=["xlsx","xls","csv","tsv","txt"],help="Excel, CSV, TSV o TXT. No necesitas una plantilla específica." if lang=="es" else "Excel, CSV, TSV or TXT. No template required.")
    analyze_action = st.empty()
    with analyze_action.container():
        st.button(tr(lang,"analyze"),disabled=True,use_container_width=True,key="analyze_waiting")
        st.caption("Sube un archivo para comenzar. No necesitas validar ni preparar una plantilla." if lang=="es" else "Upload a file to begin. No validation step or template required.")

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

    # Universal onboarding: adapt to common SME exports and database-style tables.
    simple_mode=False
    if len(sheets)==1:
        _only=list(sheets.values())[0]
        _shape,_guess=detect_single_table_shape(_only)
        st.success("✓ Detectamos una sola tabla. Inventory Copilot puede adaptarla sin que tengas que rehacer tu archivo." if lang=="es" else "✓ We detected a single table. Inventory Copilot can adapt it without requiring you to rebuild the file.")
        simple_mode=st.toggle("Usar importación inteligente" if lang=="es" else "Use smart import",value=True,
                              help="Funciona con tablas resumidas por mes y con bases transaccionales donde el producto se repite.")
        if simple_mode:
            _cols=list(_only.columns)
            mode_labels=["Transacciones / Base de datos","Meses en columnas"] if lang=="es" else ["Transactions / Database","Months in columns"]
            default_mode=0 if _shape=="long" else 1
            import_mode=st.radio("¿Cómo vienen tus ventas?" if lang=="es" else "How are sales stored?",
                                 mode_labels,index=default_mode,horizontal=True,key="smart_mode")
            long_mode=import_mode==mode_labels[0]

            if long_mode:
                st.markdown("### Inventory Copilot detectará y sumará las transacciones" if lang=="es" else "### Inventory Copilot will detect and aggregate transactions")
                st.caption("El mismo producto puede repetirse cientos de veces. Las ventas se suman por período; el inventario actual se toma una sola vez por producto." if lang=="es" else "The same product can repeat hundreds of times. Sales are summed by period; current inventory is taken once per product.")
                c1,c2,c3=st.columns(3)
                prod_guess=_guess.get("product") or _cols[0]
                period_guess=_guess.get("period") or _cols[min(1,len(_cols)-1)]
                qty_guess=_guess.get("qty") or _cols[min(2,len(_cols)-1)]
                with c1: product_col=st.selectbox("Producto / descripción",_cols,index=_cols.index(prod_guess),key="long_product")
                with c2: period_col=st.selectbox("Fecha / mes / semana",_cols,index=_cols.index(period_guess),key="long_period")
                with c3: qty_col=st.selectbox("Cantidad vendida",_cols,index=_cols.index(qty_guess),key="long_qty")
                optional=["— No disponible —"]+_cols
                g=_guess.get("onhand")
                c1,c2,c3=st.columns(3)
                with c1: onhand_col=st.selectbox("Inventario actual (opcional)",optional,index=optional.index(g) if g in optional else 0,key="long_oh")
                with c2:
                    cost_guess=_guess_col(_cols,["costo","cost","unit cost","costo unitario"])
                    cost_col=st.selectbox("Costo unitario (opcional)",optional,index=optional.index(cost_guess) if cost_guess in optional else 0,key="long_cost")
                with c3:
                    curr_guess=_guess_col(_cols,["moneda","currency","curr"])
                    currency_col=st.selectbox("Moneda (opcional)",optional,index=optional.index(curr_guess) if curr_guess in optional else 0,key="long_curr")
                c1,c2,c3=st.columns(3)
                with c1:
                    lead_guess=_guess_col(_cols,["lead time","tiempo entrega","dias entrega","plazo entrega"])
                    lead_col=st.selectbox("Tiempo de entrega (opcional)",optional,index=optional.index(lead_guess) if lead_guess in optional else 0,key="long_lead")
                with c2:
                    sup_guess=_guess_col(_cols,["supplier","vendor","proveedor"])
                    supplier_col=st.selectbox("Proveedor (opcional)",optional,index=optional.index(sup_guess) if sup_guess in optional else 0,key="long_supplier")
                with c3:
                    loc_guess=_guess_col(_cols,["location","warehouse","plant","ubicacion","almacen"])
                    location_col=st.selectbox("Ubicación (opcional)",optional,index=optional.index(loc_guess) if loc_guess in optional else 0,key="long_location")
                def _none(x): return None if x=="— No disponible —" else x
                sales,items,po,_normalized=build_long_dataset(
                    _only,product_col,period_col,qty_col,_none(onhand_col),
                    cost_col=_none(cost_col),currency_col=_none(currency_col),
                    lead_col=_none(lead_col),supplier_col=_none(supplier_col),location_col=_none(location_col))
                if len(sales)==0:
                    st.error("No pudimos interpretar la columna de fecha/mes/semana. Confirma el campo seleccionado.")
                    st.stop()
                unique_products=items["SKU"].nunique()
                records=len(_only.dropna(how="all"))
                periods=sales["PERIOD_START"].nunique()
                k1,k2,k3=st.columns(3)
                k1.metric("Productos únicos",unique_products)
                k2.metric("Registros leídos",records)
                k3.metric("Períodos detectados",periods)
                st.caption(f"✓ {records:,} filas fueron consolidadas en {len(sales):,} registros producto-período. El inventario repetido no se suma." if lang=="es" else f"✓ {records:,} rows were consolidated into {len(sales):,} product-period records. Repeated inventory is not summed.")
            else:
                st.markdown("### Confirma solo lo esencial" if lang=="es" else "### Confirm only the essentials")
                _desc_guess=_guess.get("product") or _guess_col(_cols,["descripcion","description","producto","product","item","articulo"])
                _oh_guess=_guess.get("onhand") or _guess_col(_cols,["inventario","inventario actual","stock","on hand","existencias","cantidad actual"])
                c1,c2=st.columns(2)
                with c1:
                    desc_col=st.selectbox("Descripción del producto",_cols,index=_cols.index(_desc_guess) if _desc_guess in _cols else 0,key="basic_desc")
                with c2:
                    onhand_col=st.selectbox("Inventario actual",_cols,index=_cols.index(_oh_guess) if _oh_guess in _cols else min(1,len(_cols)-1),key="basic_oh")
                candidates=[c for c in _cols if c not in [desc_col,onhand_col]]
                default_sales=candidates[-3:] if len(candidates)>=3 else candidates
                sales_cols=st.multiselect("Columnas de ventas — selecciona de la más antigua a la más reciente",
                                          candidates,default=default_sales,key="basic_sales")
                st.caption("Ejemplo: Julio → Agosto → Septiembre. Inventory Copilot convertirá esas columnas en un historial temporal.")
                if len(sales_cols)<2:
                    st.warning("Selecciona al menos 2 columnas de ventas para comenzar.")
                    st.stop()
                sales,items,po=build_basic_dataset(_only,desc_col,onhand_col,sales_cols)

            st.session_state.validation_checks=[("Importación inteligente",[],["El análisis se adapta a los campos realmente disponibles."])]
            st.session_state.validated=True
            level=detect_analysis_level(items,po,True if not long_mode else False)
            # A transactional file can unlock level 2 if it actually includes cost/lead time.
            if long_mode:
                level=detect_analysis_level(items,po,False)
            st.markdown("### Lo que Inventory Copilot puede hacer con este archivo")
            q1,q2,q3=st.columns(3)
            q1.success("✓ Consolidar ventas\n\nSuma transacciones repetidas por producto y período")
            q2.success("✓ Cobertura y prioridades\n\nDetecta bajo inventario, exceso potencial y seguimiento")
            q3.success("✓ Tendencia\n\nConvierte días, semanas o meses en historial analizable")
            if level<3:
                with st.expander("✦ ¿Quieres un análisis de procurement más avanzado?" if lang=="es" else "✦ Want a more advanced procurement analysis?",expanded=False):
                    render_unlock_more(items,po,lang)
            with st.expander("ⓘ Cómo estamos interpretando tu archivo"):
                st.markdown("**Ventas:** se suman cuando el producto aparece varias veces en el mismo período.  \n**Inventario actual:** se toma una sola vez por producto; nunca se suma por transacción.  \n**Producto sin código:** Inventory Copilot crea un ID interno y conserva tu descripción visible.  \n**Datos opcionales:** costo, moneda, lead time, proveedor y ubicación desbloquean análisis adicionales.")
            with analyze_action.container():
                smart_analyze=st.button(tr(lang,"analyze"),type="primary",use_container_width=True,key="smart_analyze")
                st.caption((f"✓ {len(_only.dropna(how='all')):,} registros leídos · {items['SKU'].nunique():,} productos detectados" if long_mode else f"✓ {len(items):,} productos detectados") if lang=="es" else (f"✓ {len(_only.dropna(how='all')):,} rows read · {items['SKU'].nunique():,} products detected" if long_mode else f"✓ {len(items):,} products detected"))
            if smart_analyze:
                with st.spinner("Entendiendo tus datos y analizando tu inventario…" if lang=="es" else "Understanding your data and analyzing your inventory…"):
                    result,projection=analyze(sales,items,po,demand_change=0,lead_delay=0,review_weeks=4)
                if level==1:
                    result=apply_basic_interpretation(result,items)
                st.session_state.sales_data=sales.copy(); st.session_state.items_data=items.copy(); st.session_state.po_data=po.copy()
                st.session_state.result=result; st.session_state.projection=projection
                st.session_state.analysis_level=level; st.session_state.basic_mode=(level==1)
                st.session_state.stage=4; st.session_state.workspace="Resumen" if lang=="es" else "Summary"
                st.session_state.category_detail=None
                st.rerun()
            st.stop()

    st.markdown('<div class="step">PASO 1 DE 3</div>',unsafe_allow_html=True)
    st.subheader(tr(lang,"where"))
    if len(sheets)==1:
        st.warning("Si prefieres el modo avanzado, puedes mapear esta tabla manualmente. Las PO abiertas son opcionales; Inventory Copilot mostrará solo los análisis respaldados por tus datos.")

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
    st.markdown(f'<div class="step">{"LISTO PARA ANALIZAR" if lang=="es" else "READY TO ANALYZE"}</div>',unsafe_allow_html=True)
    st.subheader("Inventory Copilot hará las comprobaciones por ti" if lang=="es" else "Inventory Copilot will check the data for you")
    st.caption("No hay un paso separado de validación. Al analizar, revisaremos automáticamente los campos esenciales y solo te pediremos intervenir si algo realmente impide continuar." if lang=="es" else "There is no separate validation step. When you analyze, we automatically check the essentials and only ask you to intervene if something truly blocks the analysis.")

    with analyze_action.container():
        analyze_now=st.button(tr(lang,"analyze"),type="primary",use_container_width=True,key="top_analyze_active")
        st.caption("Un clic: comprobar datos → entender estructura → analizar inventario." if lang=="es" else "One click: check data → understand structure → analyze inventory.")

    if analyze_now:
        checks=[]
        all_ok=True
        for name,df,kind in [(tr(lang,"sales"),sales,"sales"),(tr(lang,"items"),items,"items"),(tr(lang,"po"),po,"po")]:
            df.dropna(axis=0,how="all",inplace=True)
            issues=validate_dataset(df,kind)
            errors=[m for lvl,m in issues if lvl=="error"]
            warnings=[m for lvl,m in issues if lvl=="warning"]
            checks.append((name,errors,warnings))
            if errors: all_ok=False
        st.session_state.validation_checks=checks
        st.session_state.validated=all_ok
        if not all_ok:
            st.error("Encontré algunos campos esenciales que necesito para continuar. Revisa solo los puntos marcados abajo." if lang=="es" else "I found a few essential fields needed to continue. Review only the items marked below.")
            cols=st.columns(3)
            for col,(name,errors,warnings) in zip(cols,checks):
                with col:
                    st.markdown(f"**{name}**")
                    for m in errors: st.error(m)
                    for m in warnings: st.caption("• "+m)
        else:
            if "PERIOD_START" not in sales: sales["PERIOD_START"]=pd.Timestamp.today()
            if "PERIOD_END" not in sales: sales["PERIOD_END"]=sales["PERIOD_START"]
            for c,val in [("DESCRIPTION",""),("UNIT_COST",0),("CURRENCY",""),("LEAD_TIME_DAYS",0),("MOQ",0),("ORDER_MULTIPLE",1),("SERVICE_LEVEL",.97),("TARGET_WOS",10)]:
                if c not in items: items[c]=val
            if "PO_NUMBER" not in po: po["PO_NUMBER"]=""
            if "SUPPLIER" not in po: po["SUPPLIER"]=""
            with st.spinner("Entendiendo tus datos y analizando tu inventario…" if lang=="es" else "Understanding your data and analyzing your inventory…"):
                result,projection=analyze(sales,items,po,demand_change=demand_change,lead_delay=lead_delay,review_weeks=review_weeks)
            st.session_state.sales_data=sales.copy(); st.session_state.items_data=items.copy(); st.session_state.po_data=po.copy()
            st.session_state.result=result; st.session_state.projection=projection
            st.session_state.analysis_level=detect_analysis_level(items,po,False); st.session_state.basic_mode=False
            st.session_state.stage=4; st.session_state.workspace="Resumen" if lang=="es" else "Summary"
            st.session_state.category_detail=None
            st.rerun()

    st.stop()

# ---------- DECISION WORKSPACE: separate page after analysis ----------
lang="es" if st.session_state.get("ui_language","Español")=="Español" else "en"
st.markdown("""
<style>
section[data-testid="stSidebar"]{display:none !important;}
[data-testid="collapsedControl"]{display:none !important;}
.stApp{background:#F7F9FC;}
.block-container{max-width:1800px;padding:1.2rem 2.4rem 3.5rem 2.4rem;}
h1,h2,h3{letter-spacing:-0.02em;}
div[data-testid="stMetric"]{border:1px solid #E5EAF1;border-radius:12px;padding:14px 16px;background:#fff;box-shadow:0 1px 2px rgba(15,23,42,.04);}
div[data-testid="stDataFrame"]{border:1px solid #E5EAF1;border-radius:10px;overflow:hidden;background:#fff;}
button[kind="primary"],button[kind="secondary"]{border-radius:9px;font-weight:650;}
</style>
""",unsafe_allow_html=True)
h1,h2=st.columns([5,1])
with h1:
    st.markdown("## 📦 Inventory Copilot")
    st.caption("De tus datos de inventario a decisiones claras." if lang=="es" else "From inventory data to clear decisions.")
with h2:
    if st.button("Nuevo análisis" if lang=="es" else "New analysis",use_container_width=True):
        for _k in ["result","projection","sales_data","items_data","po_data","validation_checks","category_detail","analysis_level","basic_mode"]:
            if _k in st.session_state: st.session_state[_k]=None
        st.session_state.validated=False
        st.session_state.stage=1
        st.rerun()

result=st.session_state.result
projection=st.session_state.projection

# Restore prepared input datasets after Streamlit reruns into the separate
# Decision Workspace. Local variables from the onboarding page do not persist.
sales=st.session_state.get("sales_data")
items=st.session_state.get("items_data")
po=st.session_state.get("po_data")



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
# Enrich analysis output with master-data fields needed by procurement/capital views.
if isinstance(items,pd.DataFrame) and not items.empty:
    _master_cols=[c for c in ["SKU","SUPPLIER","CATEGORY","LOCATION","DESCRIPTION","UNIT_COST","CURRENCY"] if c in items.columns]
    if "SKU" in _master_cols:
        _m=items[_master_cols].copy()
        _m["SKU"]=_m["SKU"].astype(str)
        _m=_m.drop_duplicates("SKU")
        view["SKU"]=view["SKU"].astype(str)
        _rename={"SUPPLIER":"Supplier","CATEGORY":"Master_Category","LOCATION":"Location","DESCRIPTION":"Description",
                 "UNIT_COST":"Master_Unit_cost","CURRENCY":"Master_Currency"}
        _m=_m.rename(columns=_rename)
        view=view.merge(_m,on="SKU",how="left")
        if "Currency" in view.columns and "Master_Currency" in view.columns:
            view["Currency"]=view["Currency"].astype("string").fillna("")
            view["Currency"]=view["Currency"].mask(view["Currency"].str.strip().eq(""),view["Master_Currency"])

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
if "category_detail" not in st.session_state: st.session_state.category_detail=None

# Main workspace navigation: friendly one-click buttons, 2 rows x 4.
_level=st.session_state.get("analysis_level",3)
nav_es=["Resumen","Acciones","Inventario","Tendencia"]
nav_en=["Summary","Actions","Inventory","Trend"]
if _level>=2:
    nav_es += ["Compras","Capital","Simulador"]; nav_en += ["Purchasing","Capital","Simulator"]
if _level>=3:
    nav_es += ["Proveedores"]; nav_en += ["Suppliers"]
nav=nav_es if lang=="es" else nav_en
aliases={"Actions":"Acciones","Summary":"Resumen","Inventory":"Inventario","Trend":"Tendencia","Tendencia":"Trend","Purchasing":"Compras","Suppliers":"Proveedores","Capital":"Capital","Simulator":"Simulador",
         "Acciones":"Actions","Resumen":"Summary","Inventario":"Inventory","Compras":"Purchasing","Proveedores":"Suppliers","Simulador":"Simulator"}
if st.session_state.workspace not in nav:
    candidate=aliases.get(st.session_state.workspace,nav[0])
    st.session_state.workspace=candidate if candidate in nav else nav[0]
icons={"Resumen":"▦","Summary":"▦","Acciones":"!","Actions":"!","Inventario":"▤","Inventory":"▤","Forecast":"↗","Tendencia":"↗","Trend":"↗",
       "Compras":"$","Purchasing":"$","Proveedores":"◫","Suppliers":"◫","Capital":"◆","Simulador":"◇","Simulator":"◇"}
for row in [nav[:4],nav[4:]]:
    cols=st.columns(4)
    for col,name in zip(cols,row):
        active=st.session_state.workspace==name
        with col:
            if st.button(f"{icons.get(name,'')}  {name}",key=f"nav_{name}",
                         type="primary" if active else "secondary",use_container_width=True):
                if not active:
                    st.session_state.workspace=name
                    st.session_state.category_detail=None
                    st.rerun()
workspace=st.session_state.workspace
st.divider()

if workspace in ["Resumen","Summary"]:
    st.title("Centro de decisiones" if lang=="es" else "Decision Center")
    _level=st.session_state.get("analysis_level",3)
    _level_name={1:"Básico",2:"Planificación",3:"Procurement"}[_level] if lang=="es" else {1:"Basic",2:"Planning",3:"Procurement"}[_level]
    st.markdown(f"**Nivel de análisis: {_level_name} · {_level}/3**")
    _steps=("Básico  →  Planificación  →  Procurement avanzado" if lang=="es" else "Basic  →  Planning  →  Advanced procurement")
    st.caption(_steps)
    if _level==1:
        st.caption("Con tus datos actuales podemos priorizar cobertura, bajo inventario, exceso potencial y tendencia. No mostraremos cantidades de compra ni impacto en dinero sin los datos necesarios.")
        with st.expander("ⓘ ¿Qué puedo desbloquear después?"):
            st.markdown("**Agrega tiempo de entrega** → riesgo de quiebre y momento de reposición  \n**Agrega costo + moneda** → valor del inventario y capital inmovilizado  \n**Agrega proveedor + PO abiertas** → planificación de compras y exposición por proveedor")
    if _level<3:
        st.info("✦ **Inventory Copilot puede ayudarte más.** Tu análisis actual es útil, pero todavía hay decisiones de procurement que podemos desbloquear con información adicional." if lang=="es" else "✦ **Inventory Copilot can help you go further.** Your current analysis is useful, but additional data can unlock more procurement decisions.")
        with st.expander("Ver cómo mejorar mi análisis →" if lang=="es" else "See how to improve my analysis →",expanded=False):
            render_unlock_more(items,po,lang)

    st.caption("No necesitas revisar todo el inventario. Inventory Copilot procesa el portafolio y te muestra dónde decidir o actuar primero." if lang=="es" else "You do not need to review all inventory. Inventory Copilot processes the portfolio and shows where to decide or act first.")
    st.info("Empieza por **Acciones**: la categoría explica qué está pasando y el ranking indica qué revisar primero." if lang=="es" else "Start with **Actions**: category explains what is happening and ranking indicates what to review first.")
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
    st.caption("Ve a Acciones para revisar el portafolio y abrir el detalle por categoría." if lang=="es" else "Go to Actions to review the portfolio and open category detail.")

elif workspace in ["Acciones","Actions"]:
    with st.expander("ⓘ Cómo leer las prioridades" if lang=="es" else "ⓘ How to read priorities"):
        concept_strip(["Priority Score","Stockout","Confidence"])
    labels_es={"urgent":"Urgente","buy":"Comprar pronto","excess":"Exceso","monitor":"Monitorear"}
    labels_en={"urgent":"Urgent","buy":"Buy soon","excess":"Excess","monitor":"Monitor"}
    labels=labels_es if lang=="es" else labels_en
    def catkey(r):
        c=str(r.get("Category","")).lower()
        if c in ["urgente","urgent"]: return "urgent"
        if c in ["comprar pronto","buy soon"]: return "buy"
        if c in ["exceso","excess"]: return "excess"
        return "monitor"
    view["_cat_key"]=view.apply(catkey,axis=1)

    if st.session_state.category_detail:
        key=st.session_state.category_detail
        subset=view[view["_cat_key"]==key].copy().sort_values("Priority_rank")
        if st.button("← Volver a categorías" if lang=="es" else "← Back to categories"):
            st.session_state.category_detail=None
            st.rerun()
        st.title(("Detalle de categoría: " if lang=="es" else "Category detail: ")+labels[key])
        guidance_es={
          "urgent":("SKU con riesgo inmediato de quiebre o reposición tardía.",["Confirmar inventario y demanda.","Revisar ETA de PO abiertas.","Emitir o acelerar compras.","Monitorear hasta normalizar."]),
          "buy":("SKU que requieren reposición dentro del horizonte de planificación.",["Revisar cantidad sugerida.","Confirmar MOQ y múltiplos.","Validar PO abiertas.","Liberar primero los de mayor ranking."]),
          "excess":("SKU con inventario sobre el nivel objetivo y capital inmovilizado.",["Detener o reducir compras.","Revisar PO que aumenten exceso.","Evaluar transferencias/consumo.","Revisar cambios de demanda."]),
          "monitor":("SKU sin una excepción inmediata.",["Mantener seguimiento normal.","Observar demanda y lead time.","No generar compras sin una nueva señal."])}
        guidance_en={
          "urgent":("SKUs with immediate stockout or late-replenishment risk.",["Confirm inventory and demand.","Review open-PO ETAs.","Place or expedite purchases.","Monitor until normalized."]),
          "buy":("SKUs requiring replenishment within the planning horizon.",["Review suggested quantity.","Confirm MOQ and multiples.","Validate open POs.","Release highest-ranked items first."]),
          "excess":("SKUs above target inventory with capital tied up.",["Stop or reduce purchases.","Review POs increasing excess.","Evaluate transfers/consumption.","Review demand changes."]),
          "monitor":("SKUs without an immediate exception.",["Maintain normal monitoring.","Watch demand and lead time.","Do not purchase without a new signal."])}
        desc,todo=(guidance_es if lang=="es" else guidance_en)[key]
        st.caption(desc)
        m1,m2,m3,m4=st.columns(4)
        m1.metric("SKU",len(subset))
        m2.metric("Impacto total" if lang=="es" else "Total impact",f"{subset['_impact'].sum():,.0f}")
        avg_wos=(subset["On_hand"]/subset["Forecast_weekly"].replace(0,pd.NA)).dropna()
        m3.metric("WOS promedio" if lang=="es" else "Average WOS",f"{avg_wos.mean():.1f}" if len(avg_wos) else "—")
        dates=pd.to_datetime(subset["Stockout"],errors="coerce").dropna()
        days=(dates-pd.Timestamp.today().normalize()).dt.days
        days=days[days>=0]
        m4.metric("Días a quiebre prom." if lang=="es" else "Avg days to stockout",f"{days.mean():.0f}" if len(days) else "—")
        x,y=st.columns(2)
        with x:
            st.subheader("¿Por qué están aquí?" if lang=="es" else "Why are they here?")
            st.info(desc)
        with y:
            st.subheader("Qué ejecutar" if lang=="es" else "What to execute")
            st.markdown("\n".join("- "+v for v in todo))
        st.subheader("Ranking de SKU de esta categoría" if lang=="es" else "SKU ranking for this category")
        st.caption("La categoría explica el tipo de excepción; el ranking indica qué revisar primero." if lang=="es" else "Category explains the exception type; ranking indicates what to review first.")
        t=subset.copy()
        t["Ranking"]=t["Priority_rank"].astype(int); t["Score"]=t["Priority_score"].map(lambda x:f"{x:.1f}")
        t["Cantidad"]=t["Recommended_qty"].map(lambda x:f"{x:,.0f}"); t["Impacto"]=t["_impact"].map(lambda x:f"{x:,.0f}")
        t["Quiebre"]=t["Stockout"].apply(fmt_date); t["Por qué"]=t["Priority_reason"]
        cols=["Ranking","Score","SKU","Action","Cantidad","Impacto","Quiebre","Confidence","Por qué"]
        st.dataframe(t[cols],use_container_width=True,hide_index=True,height=min(700,90+35*max(1,len(t))))
        st.stop()

    st.title("Centro de acciones" if lang=="es" else "Action Center")
    st.caption("Abre una categoría para entender por qué están esos SKU, su ranking y qué ejecutar." if lang=="es" else "Open a category to understand why those SKUs are there, their ranking and what to execute.")
    counts={k:int((view["_cat_key"]==k).sum()) for k in labels}
    cols=st.columns(4)
    subtitles_es={"urgent":"Acción inmediata","buy":"Reposición requerida","excess":"Capital inmovilizado","monitor":"Seguimiento normal"}
    subtitles_en={"urgent":"Immediate action","buy":"Replenishment required","excess":"Capital tied up","monitor":"Normal monitoring"}
    subtitles=subtitles_es if lang=="es" else subtitles_en
    for col,key in zip(cols,["urgent","buy","excess","monitor"]):
        with col:
            st.metric(labels[key],counts[key],subtitles[key])
            if st.button("Ver detalle →" if lang=="es" else "View detail →",key=f"cat_{key}",use_container_width=True):
                st.session_state.category_detail=key
                st.rerun()
    st.divider()
    f1,f2=st.columns([2,1])
    search=f1.text_input("Buscar SKU" if lang=="es" else "Search SKU",placeholder="A100")
    opts=["Todas","Urgente","Comprar pronto","Exceso","Monitorear"] if lang=="es" else ["All","Urgent","Buy soon","Excess","Monitor"]
    cat=f2.selectbox("Categoría" if lang=="es" else "Category",opts)
    filtered=view.copy()
    if search: filtered=filtered[filtered.SKU.astype(str).str.contains(search,case=False,na=False)]
    if cat not in ["Todas","All"]: filtered=filtered[filtered.Category==cat]
    top=filtered.head(50).copy()
    top["Ranking"]=top.Priority_rank; top["Score"]=top.Priority_score.map(lambda x:f"{x:.1f}"); top["Categoría"]=top.Category
    top["Cantidad"]=top.Recommended_qty.map(lambda x:f"{x:,.0f}"); top["Impacto"]=top._impact.map(lambda x:f"{x:,.0f}"); top["Quiebre"]=top.Stockout.apply(fmt_date)
    st.dataframe(top[["Ranking","Score","Categoría","SKU","Action","Cantidad","Impacto","Quiebre","Confidence"]],use_container_width=True,hide_index=True,height=520)

elif workspace in ["Inventario","Inventory"]:
    if st.session_state.get("analysis_level",3)==1:
        st.info("Vista básica: priorizamos unidades y semanas de inventario. Agrega costo y moneda para convertirlo a impacto financiero." if lang=="es" else "Basic view: we prioritize units and weeks of supply. Add cost and currency to convert this into financial impact.")
        with st.expander("✦ Desbloquear análisis avanzado" if lang=="es" else "✦ Unlock advanced analysis"):
            render_unlock_more(items,po,lang)

    st.caption("Aquí conviertes cantidades en cobertura, riesgo y capital. No necesitas conocer los términos técnicos para usarlo." if lang=="es" else "This page turns quantities into coverage, risk and capital.")
    with st.expander("ⓘ Entender esta página" if lang=="es" else "ⓘ Understand this page"):
        concept_strip(["WOS","Safety Stock","Excess"])
    st.title("Inventario" if lang=="es" else "Inventory")
    inv=view.copy(); inv["SKU"]=inv.SKU.astype(str); inv["Categoría"]=inv.Category; inv["Inventario"]=inv.On_hand.map(lambda x:f"{x:,.0f}"); inv["Demanda/sem"]=inv.Forecast_weekly.map(lambda x:f"{x:,.1f}"); inv["Semanas inventario (WOS)"]=inv.apply(lambda r:f"{r.On_hand/r.Forecast_weekly:.1f}" if r.Forecast_weekly>0 else "—",axis=1); inv["Exceso $"]=inv.Excess_value.map(lambda x:f"${x:,.0f}")
    st.dataframe(inv[["SKU","Categoría","Inventario","Demanda/sem","Semanas inventario (WOS)","Exceso $"]],use_container_width=True,hide_index=True,height=650)

elif workspace in ["Forecast","Tendencia","Trend"]:
    with st.expander("ⓘ Entender esta página" if lang=="es" else "ⓘ Understand this page"):
        concept_strip(["Forecast","Confidence","Stockout"])
    st.title("Forecast")
    fc=view.copy(); fc["SKU"]=fc.SKU.astype(str); fc["Demanda esperada/sem"]=fc.Forecast_weekly.map(lambda x:f"{x:,.1f}"); fc["Modelo"]=fc.Model; fc["Error histórico"]=fc.Forecast_error.map(lambda x:f"{x:.1%}" if pd.notna(x) else "—"); fc["Confianza"]=fc.Confidence
    st.dataframe(fc[["SKU","Demanda esperada/sem","Modelo","Error histórico","Confianza"]],use_container_width=True,hide_index=True,height=650)

elif workspace in ["Compras","Purchasing"]:
    with st.expander("ⓘ Entender esta página" if lang=="es" else "ⓘ Understand this page"):
        concept_strip(["Reorder Point","Lead Time","MOQ"])
        concept_strip(["Order Multiple","Stockout","Safety Stock"])
    st.title("Planificador de compras" if lang=="es" else "Purchase Planner")
    st.caption("De la recomendación a la ejecución: qué comprar, cuánto y qué PO requieren atención." if lang=="es" else "From recommendation to execution: what to buy, how much, and which POs require attention.")

    buy=view[pd.to_numeric(view["Recommended_qty"],errors="coerce").fillna(0)>0].copy()
    if "Purchase_value" not in buy.columns:
        _rq=pd.to_numeric(buy["Recommended_qty"],errors="coerce").fillna(0) if "Recommended_qty" in buy.columns else pd.Series(0.0,index=buy.index)
        _uc=pd.to_numeric(buy["Unit_cost"],errors="coerce").fillna(0) if "Unit_cost" in buy.columns else pd.Series(0.0,index=buy.index)
        buy["Purchase_value"]=_rq*_uc
    if "Supplier" not in buy.columns:
        buy["Supplier"]="Sin proveedor" if lang=="es" else "No supplier"
    if "Currency" not in buy.columns:
        buy["Currency"]="Sin moneda" if lang=="es" else "Unspecified"
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
        if "Supplier" in buy.columns:
            st.subheader("Consolidación por proveedor" if lang=="es" else "Supplier consolidation")
            g=buy.assign(Supplier=buy["Supplier"].astype("string").fillna("").replace({"":"Sin proveedor" if lang=="es" else "No supplier"})).groupby(["Supplier","Currency"]).agg(SKUs=("SKU","nunique"),Unidades=("Recommended_qty","sum"),Valor=("Purchase_value","sum")).reset_index().sort_values("Valor",ascending=False)
            g["Unidades"]=g["Unidades"].map(lambda x:f"{x:,.0f}"); g["Valor"]=g["Valor"].map(lambda x:f"{x:,.0f}")
            st.dataframe(g,use_container_width=True,hide_index=True)
        st.subheader("Lista de compra" if lang=="es" else "Buy list")
        t=buy.sort_values("Priority_rank").copy()
        t["Ranking"]=t["Priority_rank"].astype(int); t["Cantidad"]=t["Recommended_qty"].map(lambda x:f"{x:,.0f}"); t["Valor"]=t["Purchase_value"].map(lambda x:f"{x:,.0f}"); t["Quiebre"]=t["Stockout"].apply(fmt_date)
        cols=[c for c in ["Ranking","SKU","Supplier","Currency","Cantidad","Valor","Quiebre","Action"] if c in t.columns]
        st.dataframe(t[cols],use_container_width=True,hide_index=True,height=430)
    st.subheader("Control de órdenes de compra abiertas" if lang=="es" else "Open PO Control Tower")
    if isinstance(po,pd.DataFrame) and not po.empty and "SKU" in po.columns and "EXPECTED_DATE" in po.columns:
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
    st.caption("Identifica concentración y exposición para saber qué relaciones de suministro requieren revisión." if lang=="es" else "Identify concentration and exposure to know which supply relationships require review.")

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
    st.caption("Convierte inventario en impacto financiero: dónde está tu dinero y dónde actuar sobre exceso." if lang=="es" else "Turn inventory into financial impact: where your money is and where to act on excess.")

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
