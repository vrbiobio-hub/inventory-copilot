import re
import pandas as pd

ALIASES = {
 'SKU':['sku','material','material number','sap material','item','item number','item no','part number','part no','product code','product','product id','codigo','código','codigo producto','código producto','codigo de producto','articulo','artículo','numero articulo','número artículo','referencia'],
 'PERIOD_START':['period start','start date','date from','from date','fecha inicio','inicio','posting date','pgi date','sales date','date'],
 'PERIOD_END':['period end','end date','date to','to date','fecha fin','fin'],
 'QUANTITY':['quantity','qty','sales qty','sold qty','shipped qty','delivered qty','sales','units sold','demand','cantidad','cantidad vendida','cantidad ventas','ventas','unidades','unidades vendidas','demanda','cantidad despachada'],
 'DESCRIPTION':['description','item description','material description','product description','descripcion','descripción','descripcion producto','descripción producto','descripcion material','descripción material','detalle'],
 'ON_HAND':['on hand','on-hand','onhand','stock','inventory','inventory qty','current inventory','available stock','unrestricted stock','qty on hand','qoh','existencia','existencias','inventario','inventario actual','stock actual','stock disponible','disponible','cantidad disponible'],
 'UNIT_COST':['unit cost','cost','standard cost','avg cost','average cost','precio costo','costo unitario','costo promedio','coste unitario','costo'],
 'LEAD_TIME_DAYS':['lead time days','lead time','leadtime','supplier lead time','lt days','dias lead time','días lead time','tiempo entrega','tiempo de entrega','dias entrega','días entrega','plazo entrega','plazo de entrega'],
 'MOQ':['moq','minimum order qty','minimum order quantity','min order','compra minima','compra mínima'],
 'ORDER_MULTIPLE':['order multiple','multiple','pack size','case pack','multiplo','múltiplo'],
 'SUPPLIER':['supplier','vendor','proveedor'],
 'CATEGORY':['category','product category','family','familia','categoria','categoría'],
 'LOCATION':['location','plant','warehouse','site','branch','almacen','almacén','ubicacion','ubicación'],
 'SERVICE_LEVEL':['service level','service','nivel servicio','nivel de servicio'],
 'TARGET_WOS':['target wos','target weeks','weeks target','target weeks of supply','wos target','semanas objetivo'],
 'PO_NUMBER':['po number','po','purchase order','purchase order number','orden compra','oc'],
 'EXPECTED_DATE':['expected date','eta','delivery date','expected delivery','arrival date','fecha llegada','fecha entrega']
}

def norm(s):
    s=str(s).strip().lower().replace('_',' ').replace('-',' ')
    return re.sub(r'\s+',' ',s)

def score(column, target):
    c=norm(column); aliases=[norm(x) for x in ALIASES.get(target,[])]
    if c==norm(target): return 1.0
    if c in aliases: return .98
    for a in aliases:
        if a in c or c in a: return .78
    return 0.0

def suggest_mapping(columns, targets):
    used=set(); result={}
    for t in targets:
        ranked=sorted(((score(c,t),c) for c in columns if c not in used), reverse=True)
        best=ranked[0] if ranked else (0,None)
        if best[0]>=.70:
            result[t]=best[1]; used.add(best[1])
        else: result[t]=None
    return result

def apply_mapping(df,mapping):
    ren={source:target for target,source in mapping.items() if source and source!='— No mapear —'}
    return df.rename(columns=ren).copy()

def validate_dataset(df, kind):
    req={
      'sales':['SKU','QUANTITY'],
      'items':['SKU','DESCRIPTION','ON_HAND','UNIT_COST','LEAD_TIME_DAYS'],
      'po':['SKU','QUANTITY','EXPECTED_DATE']
    }[kind]
    issues=[]
    missing=[c for c in req if c not in df.columns]
    if missing: issues.append(('error',f'Faltan campos obligatorios: {", ".join(missing)}'))
    if 'SKU' in df.columns and df['SKU'].isna().any(): issues.append(('error','Hay filas sin SKU.'))
    if 'QUANTITY' in df.columns:
        q=pd.to_numeric(df['QUANTITY'],errors='coerce')
        if q.isna().any(): issues.append(('error','Hay cantidades que no son numéricas.'))
    if kind=='items' and 'ON_HAND' in df.columns:
        if pd.to_numeric(df.ON_HAND,errors='coerce').isna().any(): issues.append(('error','ON_HAND contiene valores no numéricos.'))
    if kind=='po' and 'EXPECTED_DATE' in df.columns:
        if pd.to_datetime(df.EXPECTED_DATE,errors='coerce').isna().any(): issues.append(('warning','Algunas PO no tienen una fecha esperada válida y serán ignoradas.'))
    if kind=='sales' and 'PERIOD_START' not in df.columns:
        issues.append(('warning','No se mapeó fecha de inicio. Para este MVP se necesita una fecha/período para ordenar el historial.'))
    if not issues: issues.append(('ok','Datos listos para analizar.'))
    return issues
