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
# ---------- V28: Simple decision experience ----------
view=result.copy()
if isinstance(items,pd.DataFrame) and not items.empty:
    _master_cols=[c for c in ["SKU","SUPPLIER","CATEGORY","LOCATION","DESCRIPTION","UNIT_COST","CURRENCY","LEAD_TIME_DAYS","MOQ","ORDER_MULTIPLE"] if c in items.columns]
    if "SKU" in _master_cols:
        _m=items[_master_cols].copy(); _m["SKU"]=_m["SKU"].astype(str); _m=_m.drop_duplicates("SKU")
        _m=_m.rename(columns={"SUPPLIER":"Supplier","CATEGORY":"Master_Category","LOCATION":"Location","DESCRIPTION":"Description",
                              "UNIT_COST":"Master_Unit_cost","CURRENCY":"Master_Currency","LEAD_TIME_DAYS":"Master_Lead_time",
                              "MOQ":"Master_MOQ","ORDER_MULTIPLE":"Master_Order_multiple"})
        view["SKU"]=view["SKU"].astype(str); view=view.merge(_m,on="SKU",how="left")
        if "Currency" in view and "Master_Currency" in view:
            view["Currency"]=view["Currency"].astype("string").fillna("")
            view["Currency"]=view["Currency"].mask(view["Currency"].str.strip().eq(""),view["Master_Currency"])
for c in ["Purchase_value","Excess_value","Inventory_value","Unit_cost","Recommended_qty","Forecast_weekly","On_hand","Lead_time_days"]:
    if c in view: view[c]=pd.to_numeric(view[c],errors="coerce").fillna(0)
    else: view[c]=0.0
if "Description" not in view: view["Description"]=view["SKU"]
view["Description"]=view["Description"].astype("string").fillna(view["SKU"]).replace({"":pd.NA}).fillna(view["SKU"])
view["WOS"]=view["On_hand"]/view["Forecast_weekly"].replace(0,pd.NA)

# A simple status layer: conclusions first, technical detail second.
def simple_status(r):
    w=r.get("WOS")
    if bool(r.get("Expedite",False)) or (pd.notna(w) and w<2): return "Running low"
    if r.get("Recommended_qty",0)>0 or (pd.notna(w) and w<4): return "Reorder soon"
    if r.get("Excess_value",0)>0 or (pd.notna(w) and w>12): return "Too much stock"
    return "Healthy"
view["Simple_status"]=view.apply(simple_status,axis=1)
view["_stockout_dt"]=pd.to_datetime(view.get("Stockout"),errors="coerce")
view["_days_to_stockout"]=(view["_stockout_dt"]-pd.Timestamp.today().normalize()).dt.days
view["_attention"]=view["Simple_status"].map({"Running low":0,"Reorder soon":1,"Too much stock":2,"Healthy":3}).fillna(4)
view=view.sort_values(["_attention","_days_to_stockout"],na_position="last").reset_index(drop=True)

# Preserve a compact three-destination mental model.
if "workspace" not in st.session_state or st.session_state.workspace not in ["Action Plan","Overview","Products","Copilot"]:
    st.session_state.workspace="Action Plan"
if "selected_product" not in st.session_state: st.session_state.selected_product=None

nav0,nav1,nav2,nav3=st.columns([1.35,1,1,1])
for col,name,label in [(nav0,"Action Plan","📋 Action Plan" if lang=="en" else "📋 Plan de acción"),(nav1,"Overview","Overview" if lang=="en" else "Resumen"),(nav2,"Products","Products" if lang=="en" else "Productos"),(nav3,"Copilot","Copilot")]:
    with col:
        if st.button(label,type="primary" if st.session_state.workspace==name else "secondary",use_container_width=True,key=f"v30_{name}"):
            st.session_state.workspace=name; st.session_state.selected_product=None; st.rerun()
st.divider()

workspace=st.session_state.workspace
running=int((view["Simple_status"]=="Running low").sum())
reorder=int((view["Simple_status"]=="Reorder soon").sum())
overstock=int((view["Simple_status"]=="Too much stock").sum())
healthy=int((view["Simple_status"]=="Healthy").sum())
attention=running+reorder+overstock

# ---------- Product detail ----------
def render_product_detail(row):
    name=str(row.get("Description") or row.get("SKU"))
    if st.button("← Products" if lang=="en" else "← Productos",key="back_products"):
        st.session_state.selected_product=None; st.rerun()
    st.title(name)
    status=row.get("Simple_status","Healthy")
    status_es={"Running low":"Inventario bajo","Reorder soon":"Comprar pronto","Too much stock":"Demasiado inventario","Healthy":"Saludable"}
    st.markdown(f"### {status if lang=='en' else status_es.get(status,status)}")
    w=row.get("WOS")
    if pd.notna(w):
        msg=(f"At the current sales rate, you have approximately **{w:.1f} weeks of inventory**." if lang=="en" else f"Al ritmo actual de venta, tienes aproximadamente **{w:.1f} semanas de inventario**.")
        st.write(msg)
    a,b,c=st.columns(3)
    a.metric("On hand" if lang=="en" else "Inventario",f"{row.get('On_hand',0):,.0f}")
    b.metric("Recent demand / week" if lang=="en" else "Demanda reciente / semana",f"{row.get('Forecast_weekly',0):,.1f}")
    c.metric("Weeks of supply" if lang=="en" else "Semanas de inventario",f"{w:.1f}" if pd.notna(w) else "—",help="Weeks of Supply (WOS): how many weeks current stock may last at the estimated sales rate." if lang=="en" else "Weeks of Supply (WOS): cuántas semanas podría durar el inventario al ritmo de venta estimado.")
    st.divider()
    st.subheader("Copilot insight")
    if status=="Running low": insight="Inventory is very low compared with recent demand. Review replenishment now." if lang=="en" else "El inventario es muy bajo frente a la demanda reciente. Revisa reposición ahora."
    elif status=="Reorder soon": insight="Coverage is getting low. Review your next replenishment before it becomes urgent." if lang=="en" else "La cobertura está bajando. Revisa tu próxima reposición antes de que sea urgente."
    elif status=="Too much stock": insight="Current stock is high compared with recent demand. Review upcoming purchases before adding more inventory." if lang=="en" else "El inventario actual es alto frente a la demanda reciente. Revisa próximas compras antes de agregar más stock."
    else: insight="No immediate inventory exception was detected from the data available." if lang=="en" else "No detectamos una excepción inmediata con los datos disponibles."
    st.info(insight)
    if pd.notna(row.get("Stockout")):
        st.caption(("Projected stockout: " if lang=="en" else "Quiebre proyectado: ")+fmt_date(row.get("Stockout")))

    # Advanced capabilities live in context instead of separate navigation modules.
    advanced=[]
    if row.get("Lead_time_days",0)>0: advanced.append("Lead time")
    if row.get("Unit_cost",0)>0: advanced.append("Cost")
    if str(row.get("Supplier","") or "").strip(): advanced.append("Supplier")
    if row.get("Recommended_qty",0)>0: advanced.append("Purchase recommendation")
    with st.expander("✦ Planning details" if lang=="en" else "✦ Detalles de planificación",expanded=False):
        st.caption("Advanced decisions appear here, in the context of the product—not as extra modules." if lang=="en" else "Las decisiones avanzadas aparecen aquí, dentro del producto, no como módulos adicionales.")
        if row.get("Lead_time_days",0)>0: st.write((f"**Lead time:** {row.get('Lead_time_days',0):.0f} days" if lang=="en" else f"**Tiempo de entrega:** {row.get('Lead_time_days',0):.0f} días"))
        if row.get("Recommended_qty",0)>0: st.write((f"**Suggested purchase:** {row.get('Recommended_qty',0):,.0f} units" if lang=="en" else f"**Compra sugerida:** {row.get('Recommended_qty',0):,.0f} unidades"))
        if row.get("Purchase_value",0)>0: st.write((f"**Estimated purchase value:** {row.get('Purchase_value',0):,.0f} {row.get('Currency','')}" if lang=="en" else f"**Valor estimado de compra:** {row.get('Purchase_value',0):,.0f} {row.get('Currency','')}"))
        if row.get("Excess_value",0)>0: st.write((f"**Estimated excess value:** {row.get('Excess_value',0):,.0f} {row.get('Currency','')}" if lang=="en" else f"**Valor estimado en exceso:** {row.get('Excess_value',0):,.0f} {row.get('Currency','')}"))
        if not advanced: st.write("Add lead time, cost, supplier or open POs to unlock purchase timing, financial impact and supplier-aware recommendations." if lang=="en" else "Agrega lead time, costo, proveedor o PO abiertas para desbloquear momento de compra, impacto financiero y recomendaciones por proveedor.")

    with st.expander("Explore a scenario" if lang=="en" else "Explorar un escenario"):
        pct=st.slider("Demand change" if lang=="en" else "Cambio en demanda",-50,100,20,10,key=f"scenario_{row.get('SKU')}")
        base=float(row.get("Forecast_weekly",0)); oh=float(row.get("On_hand",0)); new=base*(1+pct/100)
        nw=(oh/new) if new>0 else None
        st.write((f"With demand {pct:+d}%, estimated coverage becomes **{nw:.1f} weeks**." if lang=="en" else f"Con demanda {pct:+d}%, la cobertura estimada pasa a **{nw:.1f} semanas**.") if nw is not None else "—")

if st.session_state.selected_product:
    _match=view[view["SKU"].astype(str)==str(st.session_state.selected_product)]
    if len(_match): render_product_detail(_match.iloc[0]); st.stop()
    st.session_state.selected_product=None

# ---------- Action Plan / Report ----------
if workspace=="Action Plan":
    st.title("Inventory Action Plan" if lang=="en" else "Plan de acción de inventario")
    st.caption("One page with the decisions that matter now. Review it first, work the actions, then open a product only when you need the detail." if lang=="en" else "Una sola vista con las decisiones que importan ahora. Revísala primero, trabaja las acciones y abre un producto solo cuando necesites el detalle.")

    open_actions=view[view["Simple_status"]!="Healthy"].copy()
    completed=0
    in_progress=0
    for _sku in open_actions["SKU"].astype(str):
        _state=st.session_state.get(f"task_state_{_sku}","To do")
        completed += int(_state=="Done")
        in_progress += int(_state=="In progress")
    todo=max(0,len(open_actions)-completed-in_progress)
    a1,a2,a3,a4=st.columns(4)
    a1.metric("Open actions" if lang=="en" else "Acciones abiertas",len(open_actions)-completed)
    a2.metric("Urgent" if lang=="en" else "Urgentes",running)
    a3.metric("In progress" if lang=="en" else "En progreso",in_progress)
    a4.metric("Completed" if lang=="en" else "Completadas",completed)

    st.markdown("### Action overview" if lang=="en" else "### Resumen de acciones")
    _chart=pd.DataFrame({
        ("Status" if lang=="en" else "Estado"):["Running low" if lang=="en" else "Inventario bajo","Reorder soon" if lang=="en" else "Comprar pronto","Too much stock" if lang=="en" else "Demasiado inventario","Healthy" if lang=="en" else "Saludable"],
        ("Products" if lang=="en" else "Productos"):[running,reorder,overstock,healthy]
    }).set_index("Status" if lang=="en" else "Estado")
    st.bar_chart(_chart,height=250,use_container_width=True)
    st.caption("The chart summarizes where attention is concentrated; healthy products stay visible without taking over the report." if lang=="en" else "El gráfico resume dónde se concentra la atención; los productos saludables siguen visibles sin dominar el reporte.")

    st.divider()
    st.markdown("### Your tasks" if lang=="en" else "### Tus tareas")
    if open_actions.empty:
        st.success("No inventory actions are required right now based on the available data." if lang=="en" else "No se requieren acciones de inventario ahora según los datos disponibles.")
    else:
        for _i,(_,r) in enumerate(open_actions.iterrows(),1):
            _sku=str(r["SKU"]); _status=r["Simple_status"]; _w=r.get("WOS")
            _status_es={"Running low":"Inventario bajo","Reorder soon":"Comprar pronto","Too much stock":"Demasiado inventario","Healthy":"Saludable"}
            _why=(f"{_w:.1f} weeks of inventory" if pd.notna(_w) else "Review current coverage") if lang=="en" else (f"{_w:.1f} semanas de inventario" if pd.notna(_w) else "Revisar cobertura actual")
            if _status=="Running low": _action="Review replenishment now" if lang=="en" else "Revisar reposición ahora"
            elif _status=="Reorder soon": _action="Plan the next replenishment" if lang=="en" else "Planificar la próxima reposición"
            else: _action="Review or pause upcoming purchases" if lang=="en" else "Revisar o pausar próximas compras"
            st.markdown(f"#### {_i}. {r['Description']}")
            st.caption(f"{_status if lang=='en' else _status_es.get(_status,_status)} · {_why}")
            st.write(f"**{'Action' if lang=='en' else 'Acción'}:** {_action}")
            _c1,_c2,_c3=st.columns([1.2,2.8,1])
            _labels=["To do","In progress","Done"]
            _current=st.session_state.get(f"task_state_{_sku}","To do")
            with _c1:
                _sel=st.selectbox("Task status" if lang=="en" else "Estado de tarea",_labels,index=_labels.index(_current),key=f"task_state_{_sku}")
            with _c2:
                st.text_input("Note" if lang=="en" else "Nota",placeholder="Waiting for supplier confirmation..." if lang=="en" else "Esperando confirmación del proveedor...",key=f"task_note_{_sku}",label_visibility="collapsed")
            with _c3:
                if st.button("View →" if lang=="en" else "Ver →",key=f"plan_view_{_sku}",use_container_width=True):
                    st.session_state.selected_product=_sku; st.rerun()
            st.divider()

    st.markdown("### Portfolio summary" if lang=="en" else "### Resumen del portafolio")
    _avg=view["WOS"].dropna().mean()
    s1,s2,s3=st.columns(3)
    s1.metric("Products analyzed" if lang=="en" else "Productos analizados",len(view))
    s2.metric("Average WOS" if lang=="en" else "WOS promedio",f"{_avg:.1f}" if pd.notna(_avg) else "—")
    s3.metric("Healthy — no action" if lang=="en" else "Saludables — sin acción",healthy)

    _export=view[[c for c in ["SKU","Description","Simple_status","On_hand","Forecast_weekly","WOS","Recommended_qty","Stockout","Action"] if c in view.columns]].copy()
    _export["Task_status"]=[st.session_state.get(f"task_state_{str(x)}","To do") if stt!="Healthy" else "No action" for x,stt in zip(_export["SKU"],_export["Simple_status"])]
    _export["Task_note"]=[st.session_state.get(f"task_note_{str(x)}","") for x in _export["SKU"]]
    st.download_button("Download action report (CSV)" if lang=="en" else "Descargar reporte de acciones (CSV)",_export.to_csv(index=False).encode("utf-8-sig"),file_name="inventory_action_plan.csv",mime="text/csv",use_container_width=True)

# ---------- Overview ----------
elif workspace=="Overview":
    st.title("Your inventory today" if lang=="en" else "Tu inventario hoy")
    st.markdown((f"### **{attention} things need your attention**" if lang=="en" else f"### **{attention} cosas necesitan tu atención**"))
    st.caption((f"Based on {len(view)} products and the information available in your file." if lang=="en" else f"Basado en {len(view)} productos y la información disponible en tu archivo."))
    c1,c2,c3,c4=st.columns(4)
    c1.metric("Running low" if lang=="en" else "Inventario bajo",running)
    c2.metric("Reorder soon" if lang=="en" else "Comprar pronto",reorder)
    c3.metric("Too much stock" if lang=="en" else "Demasiado inventario",overstock)
    c4.metric("Healthy" if lang=="en" else "Saludable",healthy)
    st.divider()
    st.subheader("Top actions" if lang=="en" else "Acciones principales")
    top=view[view["Simple_status"]!="Healthy"].head(3)
    if top.empty: st.success("Everything looks healthy based on the data available." if lang=="en" else "Todo se ve saludable según los datos disponibles.")
    else:
        for _,r in top.iterrows():
            a,b=st.columns([5,1])
            with a:
                w=r.get("WOS"); detail=(f"{w:.1f} weeks of inventory" if pd.notna(w) else "Review current coverage")
                if lang=="es": detail=(f"{w:.1f} semanas de inventario" if pd.notna(w) else "Revisar cobertura actual")
                st.markdown(f"**{r['Description']}**  \n{r['Simple_status']} · {detail}")
            with b:
                if st.button("Review →" if lang=="en" else "Revisar →",key=f"top_{r['SKU']}",use_container_width=True):
                    st.session_state.selected_product=str(r["SKU"]); st.rerun()
    st.divider()
    st.subheader("Inventory health" if lang=="en" else "Salud del inventario")
    avg_wos=view["WOS"].dropna().mean()
    h1,h2,h3=st.columns(3)
    h1.metric("Products" if lang=="en" else "Productos",len(view))
    h2.metric("Average WOS" if lang=="en" else "WOS promedio",f"{avg_wos:.1f}" if pd.notna(avg_wos) else "—",help="Weeks of Supply: estimated weeks current inventory may last." if lang=="en" else "Weeks of Supply: semanas estimadas que podría durar el inventario actual.")
    h3.metric("Need attention" if lang=="en" else "Necesitan atención",attention)
    st.divider()
    st.subheader("What Inventory Copilot can do for you" if lang=="en" else "Cómo Inventory Copilot te ayuda")
    st.caption("Capabilities appear when your data supports them. No extra setup or modules to learn." if lang=="en" else "Las capacidades aparecen cuando tus datos las permiten. Sin configuraciones ni módulos extra que aprender.")
    caps=procurement_capabilities(items,po) if isinstance(items,pd.DataFrame) else {}
    v1,v2,v3=st.columns(3)
    with v1:
        st.markdown("**Know what needs attention**" if lang=="en" else "**Saber qué necesita atención**")
        st.caption("Low stock, excess and healthy products are prioritized automatically." if lang=="en" else "Prioriza automáticamente inventario bajo, exceso y productos saludables.")
    with v2:
        if caps.get("lead_time"):
            st.markdown("**Know when to reorder**" if lang=="en" else "**Saber cuándo reponer**")
            st.caption("Lead time is included in replenishment risk and timing." if lang=="en" else "El tiempo de entrega se incorpora al riesgo y momento de reposición.")
        else:
            st.markdown("**Add lead time → know when to reorder**" if lang=="en" else "**Agrega lead time → sabe cuándo reponer**")
            st.caption("Your current analysis still works; this makes purchasing timing smarter." if lang=="en" else "Tu análisis actual sigue funcionando; este dato mejora el momento de compra.")
    with v3:
        if caps.get("cost"):
            _vals=inventory_value_by_currency(view)
            st.markdown("**See where your inventory money is**" if lang=="en" else "**Ve dónde está el dinero de tu inventario**")
            st.caption(("Inventory value is available by currency." if _vals else "Cost data is available for financial analysis.") if lang=="en" else ("El valor de inventario está disponible por moneda." if _vals else "El costo está disponible para análisis financiero."))
        else:
            st.markdown("**Add cost → see tied-up capital**" if lang=="en" else "**Agrega costo → ve capital inmovilizado**")
            st.caption("Turn excess units into financial impact when cost is available." if lang=="en" else "Convierte unidades en exceso en impacto financiero cuando tengas costo.")
    if isinstance(items,pd.DataFrame):
        with st.expander("Your data · Improve the analysis" if lang=="en" else "Tus datos · Mejora el análisis"):
            render_unlock_more(items,po,lang)

# ---------- Products ----------
elif workspace=="Products":
    st.title("Products" if lang=="en" else "Productos")
    st.caption("One place for inventory, demand, status and product-level decisions." if lang=="en" else "Un solo lugar para inventario, demanda, estado y decisiones por producto.")
    q1,q2=st.columns([2,1])
    search=q1.text_input("Search products" if lang=="en" else "Buscar productos",placeholder="Paint, A100...")
    opts=["All","Running low","Reorder soon","Too much stock","Healthy"]
    status=q2.selectbox("Status" if lang=="en" else "Estado",opts)
    pv=view.copy()
    if search: pv=pv[pv["Description"].astype(str).str.contains(search,case=False,na=False)|pv["SKU"].astype(str).str.contains(search,case=False,na=False)]
    if status!="All": pv=pv[pv["Simple_status"]==status]
    for _,r in pv.head(100).iterrows():
        a,b,c,d,e=st.columns([3,1.2,1,1,1])
        a.markdown(f"**{r['Description']}**  \n<span style='color:#64748b'>{r['SKU']}</span>",unsafe_allow_html=True)
        b.write(r["Simple_status"])
        c.metric("On hand" if lang=="en" else "Stock",f"{r['On_hand']:,.0f}")
        c.caption("Current inventory" if lang=="en" else "Inventario actual")
        d.metric("WOS",f"{r['WOS']:.1f}" if pd.notna(r['WOS']) else "—")
        d.caption("Weeks of supply" if lang=="en" else "Semanas de inventario")
        if e.button("Open →" if lang=="en" else "Abrir →",key=f"prod_{r['SKU']}",use_container_width=True):
            st.session_state.selected_product=str(r["SKU"]); st.rerun()
        st.divider()

# ---------- Copilot ----------
else:
    st.title("Ask Inventory Copilot" if lang=="en" else "Pregúntale a Inventory Copilot")
    st.caption("Ask business questions without learning where every feature lives." if lang=="en" else "Haz preguntas de negocio sin aprender dónde vive cada función.")
    st.markdown("**Try asking:** what needs attention · what should I reorder · where do I have too much stock" if lang=="en" else "**Prueba preguntando:** qué necesita atención · qué debería reponer · dónde tengo demasiado inventario")
    questions=(
        ["What needs my attention?","What should I reorder?","Where do I have too much inventory?","Which products look healthy?"]
        if lang=="en" else
        ["¿Qué necesita mi atención?","¿Qué debería reponer?","¿Dónde tengo demasiado inventario?","¿Qué productos están saludables?"]
    )
    q=st.selectbox("Suggested questions" if lang=="en" else "Preguntas sugeridas",questions)
    custom=st.text_input("Ask about your inventory..." if lang=="en" else "Pregunta sobre tu inventario...",placeholder="Which products should I review first?" if lang=="en" else "¿Qué productos debería revisar primero?")
    if st.button("Ask" if lang=="en" else "Preguntar",type="primary",use_container_width=True):
        text=(custom or q).lower()
        if any(x in text for x in ["reorder","reponer","comprar"]): ans=view[view["Simple_status"].isin(["Running low","Reorder soon"])].head(10)
        elif any(x in text for x in ["too much","demasiado","exceso","overstock"]): ans=view[view["Simple_status"]=="Too much stock"].head(10)
        elif any(x in text for x in ["healthy","saludable"]): ans=view[view["Simple_status"]=="Healthy"].head(10)
        else: ans=view[view["Simple_status"]!="Healthy"].head(10)
        if ans.empty: st.success("No matching exceptions were found." if lang=="en" else "No encontré excepciones que coincidan con esa pregunta.")
        else:
            st.markdown("### Answer" if lang=="en" else "### Respuesta")
            for _,r in ans.iterrows():
                w=r.get("WOS"); extra=f" · {w:.1f} WOS" if pd.notna(w) else ""
                st.write(f"**{r['Description']}** — {r['Simple_status']}{extra}")
    st.info("Inventory Copilot uses the information available in your file. Add lead time, cost, supplier or open POs to make the answers more precise and actionable." if lang=="en" else "Inventory Copilot usa la información disponible en tu archivo. Agrega lead time, costo, proveedor o PO abiertas para obtener respuestas más precisas y accionables.")
