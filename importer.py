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
 'CURRENCY':['currency','currency code','curr','moneda','codigo moneda','código moneda','divisa'],
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
    df=df.copy().dropna(axis=0,how="all")
    req={
      'sales':['SKU','QUANTITY'],
      'items':['SKU','DESCRIPTION','ON_HAND'],
      'po':['SKU','QUANTITY','EXPECTED_DATE']
    }[kind]
    issues=[]
    missing=[c for c in req if c not in df.columns]
    if missing:
        issues.append(('error',f'Faltan campos obligatorios: {", ".join(missing)}'))
        return issues
    # Rows with no meaningful mapped content are not business records.
    mapped=[c for c in df.columns if c in set(sum([
        ['SKU','QUANTITY','PERIOD_START','PERIOD_END'],
        ['DESCRIPTION','ON_HAND','UNIT_COST','LEAD_TIME_DAYS','MOQ','ORDER_MULTIPLE'],
        ['PO_NUMBER','EXPECTED_DATE','SUPPLIER','LOCATION','CUSTOMER']],[]))]
    if mapped:
        df=df.dropna(subset=mapped,how="all")
    sku=df['SKU'].astype("string").str.strip()
    bad_sku=sku.isna() | (sku=="") | (sku.str.lower().isin(["nan","none"]))
    if bad_sku.any(): issues.append(('error',f'Hay {int(bad_sku.sum())} fila(s) con datos pero sin SKU.'))
    if 'QUANTITY' in df.columns:
        raw=df['QUANTITY']
        q=pd.to_numeric(raw,errors='coerce')
        bad=q.isna() & raw.notna() & raw.astype("string").str.strip().ne("")
        if bad.any(): issues.append(('error',f'Hay {int(bad.sum())} cantidad(es) que no son numéricas.'))
    if kind=='items':
        for c,label in [('ON_HAND','Inventario actual'),('UNIT_COST','Costo unitario'),('LEAD_TIME_DAYS','Tiempo de entrega')]:
            if c not in df.columns:
                if c=='UNIT_COST': issues.append(('warning','Falta Costo unitario. El análisis operativo puede continuar, pero no se calculará impacto financiero.'))
                if c=='LEAD_TIME_DAYS': issues.append(('warning','Falta Lead Time. El análisis direccional puede continuar, pero no se calcularán Safety Stock, ROP ni cantidad de compra precisa.'))
                continue
            raw=df[c]
            n=pd.to_numeric(raw,errors='coerce')
            bad=n.isna() & raw.notna() & raw.astype("string").str.strip().ne("")
            if bad.any(): issues.append(('error',f'{label} contiene {int(bad.sum())} valor(es) no numéricos.'))
        if df['SKU'].duplicated(keep=False).any(): issues.append(('warning','Hay SKU duplicados en el maestro de artículos. Revisa si corresponden a ubicaciones diferentes.'))
        if 'CURRENCY' in df.columns:
            curr=df['CURRENCY'].astype("string").str.strip().str.upper()
            cost=pd.to_numeric(df['UNIT_COST'],errors='coerce').fillna(0) if 'UNIT_COST' in df.columns else pd.Series(0,index=df.index)
            missing_curr=(cost>0) & (curr.isna() | curr.eq("") | curr.str.lower().isin(["nan","none"]))
            if missing_curr.any():
                issues.append(('warning',f'Hay {int(missing_curr.sum())} SKU con costo pero sin moneda. El valor de inventario se mostrará como moneda no especificada para esos SKU.'))
            invalid=~curr.isna() & curr.ne("") & ~curr.str.match(r'^[A-Z]{3}$',na=False)
            if invalid.any():
                issues.append(('warning',f'Hay {int(invalid.sum())} código(s) de moneda que no usan el formato ISO de 3 letras (ej.: USD, CLP, COP, MXN).'))
        else:
            cost=pd.to_numeric(df['UNIT_COST'],errors='coerce').fillna(0) if 'UNIT_COST' in df.columns else pd.Series(0,index=df.index)
            if (cost>0).any():
                issues.append(('warning','Hay costos unitarios, pero no se indicó CURRENCY/MONEDA. Agrega USD, CLP, COP, MXN u otro código de 3 letras para identificar correctamente el valor del inventario.'))

    if kind=='po':
        raw=df['EXPECTED_DATE']
        d=pd.to_datetime(raw,errors='coerce')
        bad=d.isna() & raw.notna() & raw.astype("string").str.strip().ne("")
        if bad.any(): issues.append(('warning',f'{int(bad.sum())} PO tienen una fecha esperada inválida y deben revisarse.'))
    if kind=='sales' and 'PERIOD_START' not in df.columns:
        issues.append(('warning','No se mapeó una fecha inicial. Se necesita una fecha/período para ordenar correctamente el historial.'))
    if not issues: issues.append(('ok','Datos listos para analizar.'))
    return issues
