import math
import numpy as np
import pandas as pd

def wape(a,p):
    den=np.abs(a).sum()
    return np.abs(a-p).sum()/den if den else np.nan

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
    qty=max(qty,float(moq or 0)); m=max(1,float(multiple or 1))
    return int(math.ceil(qty/m)*m)

def _num(v,default=0.0):
    x=pd.to_numeric(pd.Series([v]),errors="coerce").iloc[0]
    return float(x) if pd.notna(x) else float(default)

def infer_period_days(sku_sales):
    """Infer the demand bucket length. Uses explicit period ranges first, then median start-date spacing."""
    if sku_sales.empty: return 7.0, "Unknown"
    x=sku_sales.sort_values("PERIOD_START").copy()
    if "PERIOD_END" in x:
        end=pd.to_datetime(x["PERIOD_END"],errors="coerce")
        start=pd.to_datetime(x["PERIOD_START"],errors="coerce")
        durations=(end-start).dt.days+1
        valid=durations[(durations>0)&durations.notna()]
        # Only trust explicit ranges when they actually span more than a point-date.
        if len(valid) and valid.median()>1:
            days=float(valid.median())
        else:
            days=np.nan
    else:
        days=np.nan
    if pd.isna(days):
        dates=pd.to_datetime(x["PERIOD_START"],errors="coerce").dropna().drop_duplicates().sort_values()
        diffs=dates.diff().dt.days.dropna()
        diffs=diffs[diffs>0]
        days=float(diffs.median()) if len(diffs) else 30.4375
    days=max(1.0,days)
    label="Daily" if days<=2 else ("Weekly" if days<=10 else ("Monthly" if days<=45 else "Custom"))
    return days,label

def simulate(onhand,weekly,safety,sku_po,today,weeks=52,extra_receipt=None):
    inv=float(onhand); rows=[]; first_risk=None; first_zero=None
    safety_cmp=0.0 if pd.isna(safety) else float(safety)
    for w in range(weeks):
        ws=today+pd.Timedelta(days=7*w); we=ws+pd.Timedelta(days=6)
        receipts=float(sku_po.loc[(sku_po.EXPECTED_DATE>=ws)&(sku_po.EXPECTED_DATE<=we),'QUANTITY'].fillna(0).sum()) if len(sku_po) else 0
        if extra_receipt and ws<=extra_receipt[0]<=we: receipts+=extra_receipt[1]
        begin=inv; inv=begin+receipts-weekly
        status='Quiebre' if inv<=0 else ('Riesgo' if inv<safety_cmp else ('Exceso' if weekly>0 and inv>weekly*20 else 'Saludable'))
        if status in ('Riesgo','Quiebre') and first_risk is None:first_risk=ws
        if status=='Quiebre' and first_zero is None:first_zero=ws
        rows.append([ws,begin,weekly,receipts,inv,safety,status])
    return rows,first_risk,first_zero

def analyze(sales,items,po,today=None,demand_change=0.,lead_delay=0,review_weeks=4):
    sales=sales.copy(); items=items.copy(); po=po.copy()
    if "PERIOD_START" not in sales: sales["PERIOD_START"]=pd.NaT
    sales["PERIOD_START"]=pd.to_datetime(sales["PERIOD_START"],errors="coerce")
    sales["QUANTITY"]=pd.to_numeric(sales.get("QUANTITY",0),errors="coerce").fillna(0).clip(lower=0)
    if "EXPECTED_DATE" not in po: po["EXPECTED_DATE"]=pd.NaT
    if "QUANTITY" not in po: po["QUANTITY"]=0.0
    if "SKU" not in po: po["SKU"]=""
    po["EXPECTED_DATE"]=pd.to_datetime(po["EXPECTED_DATE"],errors="coerce")
    po["QUANTITY"]=pd.to_numeric(po["QUANTITY"],errors="coerce").fillna(0).clip(lower=0)
    today=pd.Timestamp(today).normalize() if today is not None else pd.Timestamp.today().normalize()
    out=[]; projections=[]
    for _,it in items.iterrows():
        sku=it['SKU']
        sku_sales=sales[sales.SKU==sku].sort_values('PERIOD_START')
        hist=sku_sales['QUANTITY'].astype(float).values
        model,period_fcst,err,bias=forecast(hist)
        period_fcst*=max(0,1+demand_change)
        period_days,frequency=infer_period_days(sku_sales)
        weekly=max(0,period_fcst*7/period_days)
        # Scale historical variability to the same weekly unit used by the policy.
        std_period=float(np.std(hist,ddof=1)) if len(hist)>1 else 0.
        std_weekly=max(0,std_period*7/period_days)

        raw_lead=pd.to_numeric(pd.Series([it.get('LEAD_TIME_DAYS',np.nan)]),errors="coerce").iloc[0]
        has_lead=pd.notna(raw_lead) and float(raw_lead)>0
        lead=max(0,float(raw_lead)+lead_delay) if has_lead else np.nan
        service=_num(it.get('SERVICE_LEVEL',.97),.97)
        safety=(z_for_service(service)*std_weekly*math.sqrt(lead/7)) if has_lead else np.nan

        onhand=max(0,_num(it.get('ON_HAND',0),0)); cost=max(0,_num(it.get('UNIT_COST',0),0))
        currency=str(it.get('CURRENCY','') or '').strip().upper()
        moq=max(0,_num(it.get('MOQ',0),0)); multiple=max(1,_num(it.get('ORDER_MULTIPLE',1),1))

        sku_po=po[po.SKU==sku].copy()
        sku_po=sku_po[sku_po.EXPECTED_DATE.notna() & (sku_po.EXPECTED_DATE>=today)]
        base,risk,zero=simulate(onhand,weekly,safety,sku_po,today,52)
        for x in base[:26]: projections.append([sku]+x)

        if has_lead:
            arrival=today+pd.Timedelta(days=lead)
            pre=[x for x in base if x[0]<=arrival]
            inv_at_arrival=pre[-1][4] if pre else onhand
            order_up_to=safety+weekly*max(review_weeks,1)
            raw=max(0,order_up_to-inv_at_arrival)
            recommended=round_order(raw,moq,multiple)
            expedite=bool(zero is not None and zero<arrival)
            relevant_po=float(sku_po.loc[sku_po.EXPECTED_DATE<=arrival,'QUANTITY'].fillna(0).sum())
            reorder_point=weekly*(lead/7)+safety
            target_now=safety+weekly*max(lead/7,review_weeks)
            excess=max(0,onhand+relevant_po-target_now)
        else:
            arrival=pd.NaT; recommended=0; expedite=False; relevant_po=0.0
            reorder_point=np.nan
            # Without LT, excess is directional using review coverage only, not a replenishment policy.
            target_now=weekly*max(review_weeks,1)
            excess=max(0,onhand-target_now) if weekly>0 else onhand

        excess_value=excess*cost
        if not has_lead and weekly>0: policy_status='Agregar Lead Time'
        elif onhand <= safety and weekly>0: policy_status='Bajo Safety Stock'
        elif onhand <= reorder_point and weekly>0: policy_status='Comprar / Bajo ROP'
        elif weekly>0: policy_status='Sobre ROP'
        else: policy_status='Sin demanda'

        conf='Alta' if not np.isnan(err) and err<=.10 else ('Media' if not np.isnan(err) and err<=.25 else 'Baja')
        if weekly==0:
            situation='Sin demanda'; action='No comprar; revisar inventario existente'; priority=4; recommended=0
            explanation='No hay demanda proyectada con el historial disponible. Revisa si el SKU está descontinuado, es nuevo o tuvo stockouts.'
        elif not has_lead:
            # Directional signal only: no precise purchase quantity without replenishment time.
            wos=onhand/weekly if weekly else np.inf
            if wos<2: situation='Urgente'; priority=1
            elif wos<4: situation='Comprar pronto'; priority=2
            elif wos>12: situation='Exceso'; priority=4
            else: situation='Monitorear'; priority=3
            action='Agregar Lead Time para calcular compra'
            explanation=f'Hay aproximadamente {wos:.1f} semanas de cobertura, pero falta Lead Time. No se calcula Safety Stock, ROP ni una cantidad de compra precisa.'
        elif expedite:
            situation='Compra urgente / acelerar'; action=f'Comprar {recommended} y revisar opción expedita' if recommended else 'Acelerar suministro'; priority=1
            explanation=f'El stock podría agotarse antes de que una nueva orden con lead time normal llegue ({arrival:%d %b %Y}).'
        elif recommended>0:
            situation='Comprar pronto'; action=f'Comprar {recommended} unidades'; priority=2
            explanation=f'Una orden emitida ahora llegaría aproximadamente el {arrival:%d %b %Y}. La cantidad sugerida recupera inventario de seguridad + {review_weeks} semanas de cobertura.'
        elif excess>0:
            situation='Exceso'; action='No comprar por ahora'; priority=4
            explanation=(f'Hay aproximadamente {excess:,.0f} unidades por encima del nivel objetivo relevante.'
                         if cost<=0 else f'Hay aproximadamente ${excess_value:,.0f} por encima del nivel objetivo relevante.')
        else:
            situation='Saludable'; action='Mantener y monitorear'; priority=3
            explanation='No se detecta una necesidad inmediata de compra con las PO y fechas actuales.'

        out.append(dict(SKU=sku,Situation=situation,Action=action,Confidence=conf,
            Forecast_weekly=weekly,Forecast_error=err,Bias=bias,Demand_frequency=frequency,Period_days=period_days,
            On_hand=onhand,Unit_cost=cost,Currency=currency,Inventory_value=onhand*cost,Relevant_PO=relevant_po,
            Lead_time_days=lead,Service_level=service,Z_factor=z_for_service(service),Demand_std=std_weekly,
            Safety_stock=safety,Reorder_point=reorder_point,Inventory_policy_status=policy_status,
            Recommended_qty=recommended,Purchase_value=recommended*cost,Excess_value=excess_value,
            First_risk=risk,Stockout=zero,Normal_arrival=arrival,Expedite=expedite,Explanation=explanation,
            Priority=priority,Model=model))
    return pd.DataFrame(out).sort_values(['Priority','Purchase_value'],ascending=[True,False]),pd.DataFrame(
        projections,columns=['SKU','Week','Beginning','Demand','Receipts','Ending','Safety Stock','Status'])
