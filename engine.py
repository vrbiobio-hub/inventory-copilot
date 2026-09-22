import math
import numpy as np
import pandas as pd

def wape(a,p):
    den=np.abs(a).sum(); return np.abs(a-p).sum()/den if den else np.nan

def croston(y,alpha=.2):
    y=np.asarray(y,float); nz=np.where(y>0)[0]
    if not len(nz): return 0.
    q=y[nz[0]]; interval=max(1,nz[0]+1); last=nz[0]
    for idx in nz[1:]:
        gap=idx-last; q+=alpha*(y[idx]-q); interval+=alpha*(gap-interval); last=idx
    return q/interval if interval else 0.

def forecast(y):
    y=np.asarray(y,float)
    if not len(y): return 'No history',0.,np.nan,0.
    if len(y)<3: return 'Naive',float(y[-1]),np.nan,0.
    n=min(6,max(1,len(y)-4)); actual=[]; pred={k:[] for k in ['Naive','MA3','SES','Croston']}
    for i in range(len(y)-n,len(y)):
        tr=y[:i]; actual.append(y[i]); pred['Naive'].append(tr[-1]); pred['MA3'].append(np.mean(tr[-3:]))
        level=tr[0]
        for v in tr[1:]: level=.3*v+.7*level
        pred['SES'].append(level); pred['Croston'].append(croston(tr))
    scores={k:wape(np.array(actual),np.array(v)) for k,v in pred.items()}
    best=min(scores,key=lambda k: scores[k] if not np.isnan(scores[k]) else 1e9)
    if best=='Naive': f=y[-1]
    elif best=='MA3': f=np.mean(y[-3:])
    elif best=='SES':
        f=y[0]
        for v in y[1:]: f=.3*v+.7*f
    else: f=croston(y)
    bias=(np.array(pred[best])-np.array(actual)).sum()/max(1,np.abs(actual).sum())
    return best,float(f),float(scores[best]),float(bias)

def z_for_service(s):
    return 1.282 if s<=.90 else 1.645 if s<=.95 else 1.881 if s<=.97 else 2.054 if s<=.98 else 2.326

def round_order(qty,moq,multiple):
    if qty<=0:return 0
    qty=max(qty,float(moq or 0)); m=max(1,float(multiple or 1)); return int(math.ceil(qty/m)*m)

def simulate(onhand,weekly,safety,sku_po,today,weeks=52,extra_receipt=None):
    inv=float(onhand); rows=[]; first_risk=None; first_zero=None
    for w in range(weeks):
        ws=today+pd.Timedelta(days=7*w); we=ws+pd.Timedelta(days=6)
        receipts=float(sku_po.loc[(sku_po.EXPECTED_DATE>=ws)&(sku_po.EXPECTED_DATE<=we),'QUANTITY'].fillna(0).sum()) if len(sku_po) else 0
        if extra_receipt and ws<=extra_receipt[0]<=we: receipts+=extra_receipt[1]
        begin=inv; inv=begin+receipts-weekly
        status='Quiebre' if inv<=0 else ('Riesgo' if inv<safety else ('Exceso' if weekly>0 and inv>weekly*20 else 'Saludable'))
        if status in ('Riesgo','Quiebre') and first_risk is None:first_risk=ws
        if status=='Quiebre' and first_zero is None:first_zero=ws
        rows.append([ws,begin,weekly,receipts,inv,safety,status])
    return rows,first_risk,first_zero

def analyze(sales,items,po,today=None,demand_change=0.,lead_delay=0,review_weeks=4):
    sales=sales.copy(); items=items.copy(); po=po.copy()
    sales['PERIOD_START']=pd.to_datetime(sales['PERIOD_START']); po['EXPECTED_DATE']=pd.to_datetime(po['EXPECTED_DATE'],errors='coerce')
    today=pd.Timestamp(today).normalize() if today is not None else pd.Timestamp.today().normalize()
    out=[]; projections=[]
    for _,it in items.iterrows():
        sku=it['SKU']; hist=sales[sales.SKU==sku].sort_values('PERIOD_START')['QUANTITY'].astype(float).values
        model,monthly,err,bias=forecast(hist); monthly*=1+demand_change; weekly=max(0,monthly*12/52)
        lead=max(0,float(it.get('LEAD_TIME_DAYS',0))+lead_delay); service=float(it.get('SERVICE_LEVEL',.97) or .97)
        std=float(np.std(hist,ddof=1)) if len(hist)>1 else 0.; safety=z_for_service(service)*std*math.sqrt(max(1,lead/7*12/52))
        onhand=float(it.get('ON_HAND',0)); cost=float(it.get('UNIT_COST',0)); currency=str(it.get('CURRENCY','') or '').strip().upper(); moq=float(it.get('MOQ',0) or 0); multiple=float(it.get('ORDER_MULTIPLE',1) or 1)
        sku_po=po[po.SKU==sku].copy(); sku_po=sku_po[sku_po.EXPECTED_DATE.notna() & (sku_po.EXPECTED_DATE>=today)]
        base,risk,zero=simulate(onhand,weekly,safety,sku_po,today,52)
        for x in base[:26]: projections.append([sku]+x)
        arrival=today+pd.Timedelta(days=lead)
        pre=[x for x in base if x[0]<=arrival]
        inv_at_arrival=pre[-1][4] if pre else onhand
        order_up_to=safety+weekly*max(review_weeks,1)
        raw=max(0,order_up_to-inv_at_arrival)
        recommended=round_order(raw,moq,multiple)
        expedite=bool(zero is not None and zero<arrival)
        relevant_po=float(sku_po.loc[sku_po.EXPECTED_DATE<=arrival,'QUANTITY'].fillna(0).sum())
        # Inventory policy. Never invent ROP when lead time is unavailable.
        reorder_point=(weekly*(lead/7)+safety) if lead>0 else np.nan
        if onhand <= safety and weekly>0:
            policy_status='Bajo Safety Stock'
        elif lead>0 and onhand <= reorder_point and weekly>0:
            policy_status='Comprar / Bajo ROP'
        elif lead>0 and weekly>0:
            policy_status='Sobre ROP'
        else:
            policy_status='Agregar Lead Time'
        target_now=safety+weekly*max(lead/7,review_weeks)
        excess=max(0,onhand+relevant_po-target_now); excess_value=excess*cost
        conf='Alta' if not np.isnan(err) and err<=.10 else ('Media' if not np.isnan(err) and err<=.25 else 'Baja')
        if weekly==0:
            situation='Sin demanda'; action='No comprar; revisar inventario existente'; priority=4; recommended=0
            explanation='No hay demanda proyectada con el historial disponible. Revisa si el SKU está descontinuado, es nuevo o tuvo stockouts.'
        elif expedite:
            situation='Compra urgente / acelerar'; action=f'Comprar {recommended} y revisar opción expedita' if recommended else 'Acelerar suministro'; priority=1
            explanation=f'El stock podría agotarse antes de que una nueva orden con lead time normal llegue ({arrival:%d %b %Y}).'
        elif recommended>0:
            situation='Comprar pronto'; action=f'Comprar {recommended} unidades'; priority=2
            explanation=f'Una orden emitida ahora llegaría aproximadamente el {arrival:%d %b %Y}. La cantidad sugerida recupera inventario de seguridad + {review_weeks} semanas de cobertura.'
        elif excess>0:
            situation='Exceso'; action='No comprar por ahora'; priority=4; explanation=f'Hay aproximadamente ${excess_value:,.0f} por encima del nivel objetivo relevante.'
        else:
            situation='Saludable'; action='Mantener y monitorear'; priority=3; explanation='No se detecta una necesidad inmediata de compra con las PO y fechas actuales.'
        out.append(dict(SKU=sku,Situation=situation,Action=action,Confidence=conf,Forecast_weekly=weekly,Forecast_error=err,Bias=bias,On_hand=onhand,Unit_cost=cost,Currency=currency,Inventory_value=onhand*cost,Relevant_PO=relevant_po,Lead_time_days=lead,Service_level=service,Z_factor=z_for_service(service),Demand_std=std,Safety_stock=safety,Reorder_point=reorder_point,Inventory_policy_status=policy_status,Recommended_qty=recommended,Purchase_value=recommended*cost,Excess_value=excess_value,First_risk=risk,Stockout=zero,Normal_arrival=arrival,Expedite=expedite,Explanation=explanation,Priority=priority,Model=model))
    return pd.DataFrame(out).sort_values(['Priority','Purchase_value'],ascending=[True,False]),pd.DataFrame(projections,columns=['SKU','Week','Beginning','Demand','Receipts','Ending','Safety Stock','Status'])
