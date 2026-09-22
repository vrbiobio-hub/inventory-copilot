import unittest, math
import numpy as np, pandas as pd
from engine import analyze, infer_period_days, round_order

TODAY=pd.Timestamp("2026-09-21")
def items(lead=28,on=500,cost=10,moq=0,multiple=1):
    return pd.DataFrame([dict(SKU="A",DESCRIPTION="A",ON_HAND=on,UNIT_COST=cost,CURRENCY="USD",
        LEAD_TIME_DAYS=lead,MOQ=moq,ORDER_MULTIPLE=multiple,SERVICE_LEVEL=.97)])
def po(q=0,date="2026-10-01"):
    return pd.DataFrame([dict(SKU="A",QUANTITY=q,EXPECTED_DATE=date)]) if q is not None else pd.DataFrame(columns=["SKU","QUANTITY","EXPECTED_DATE"])
def weekly(q=100,n=12):
    d=pd.date_range("2026-06-29",periods=n,freq="7D")
    return pd.DataFrame({"SKU":"A","PERIOD_START":d,"PERIOD_END":d,"QUANTITY":q})
def daily(q=10,n=30):
    d=pd.date_range("2026-08-01",periods=n,freq="D")
    return pd.DataFrame({"SKU":"A","PERIOD_START":d,"PERIOD_END":d,"QUANTITY":q})
def monthly(q=400,n=12):
    d=pd.date_range("2025-10-01",periods=n,freq="MS")
    return pd.DataFrame({"SKU":"A","PERIOD_START":d,"PERIOD_END":d+pd.offsets.MonthEnd(0),"QUANTITY":q})

class Reliability(unittest.TestCase):
    def test_weekly_frequency(self):
        r,_=analyze(weekly(),items(),po(None),TODAY); self.assertAlmostEqual(r.iloc[0].Forecast_weekly,100,places=4)
    def test_daily_frequency(self):
        r,_=analyze(daily(),items(),po(None),TODAY); self.assertAlmostEqual(r.iloc[0].Forecast_weekly,70,places=4)
    def test_monthly_frequency(self):
        r,_=analyze(monthly(),items(),po(None),TODAY); self.assertTrue(85 <= r.iloc[0].Forecast_weekly <= 95)
    def test_frequency_labels(self):
        self.assertEqual(infer_period_days(weekly())[1],"Weekly"); self.assertEqual(infer_period_days(daily())[1],"Daily"); self.assertEqual(infer_period_days(monthly())[1],"Monthly")
    def test_missing_lead_no_ss(self):
        r,_=analyze(weekly(),items(lead=np.nan),po(None),TODAY); self.assertTrue(pd.isna(r.iloc[0].Safety_stock))
    def test_missing_lead_no_rop(self):
        r,_=analyze(weekly(),items(lead=np.nan),po(None),TODAY); self.assertTrue(pd.isna(r.iloc[0].Reorder_point))
    def test_missing_lead_no_precise_buy(self):
        r,_=analyze(weekly(),items(lead=np.nan,on=10),po(None),TODAY); self.assertEqual(r.iloc[0].Recommended_qty,0); self.assertIn("Lead Time",r.iloc[0].Action)
    def test_bad_po_qty_does_not_crash(self):
        p=pd.DataFrame([{"SKU":"A","QUANTITY":"bad","EXPECTED_DATE":"2026-10-01"}]); r,_=analyze(weekly(),items(),p,TODAY); self.assertEqual(r.iloc[0].Relevant_PO,0)
    def test_bad_po_date_does_not_crash(self):
        p=pd.DataFrame([{"SKU":"A","QUANTITY":100,"EXPECTED_DATE":"bad"}]); r,_=analyze(weekly(),items(),p,TODAY); self.assertEqual(r.iloc[0].Relevant_PO,0)
    def test_negative_po_clipped(self):
        p=pd.DataFrame([{"SKU":"A","QUANTITY":-100,"EXPECTED_DATE":"2026-10-01"}]); r,_=analyze(weekly(),items(),p,TODAY); self.assertEqual(r.iloc[0].Relevant_PO,0)
    def test_negative_sales_clipped(self):
        s=weekly(); s.loc[0,"QUANTITY"]=-999; r,_=analyze(s,items(),po(None),TODAY); self.assertGreaterEqual(r.iloc[0].Forecast_weekly,0)
    def test_negative_onhand_clipped(self):
        r,_=analyze(weekly(),items(on=-5),po(None),TODAY); self.assertEqual(r.iloc[0].On_hand,0)
    def test_moq(self): self.assertEqual(round_order(30,100,1),100)
    def test_multiple(self): self.assertEqual(round_order(101,0,25),125)
    def test_zero_demand(self):
        r,_=analyze(weekly(0),items(),po(None),TODAY); self.assertEqual(r.iloc[0].Recommended_qty,0); self.assertEqual(r.iloc[0].Situation,"Sin demanda")
    def test_rop_ge_ss(self):
        r,_=analyze(weekly(),items(),po(None),TODAY); self.assertGreaterEqual(r.iloc[0].Reorder_point,r.iloc[0].Safety_stock)
    def test_open_po_before_arrival_counts(self):
        r,_=analyze(weekly(),items(),po(200,"2026-10-01"),TODAY); self.assertEqual(r.iloc[0].Relevant_PO,200)
    def test_open_po_after_arrival_not_relevant(self):
        r,_=analyze(weekly(),items(),po(200,"2027-01-01"),TODAY); self.assertEqual(r.iloc[0].Relevant_PO,0)
    def test_projection_26_rows(self):
        _,p=analyze(weekly(),items(),po(None),TODAY); self.assertEqual(len(p),26)
    def test_service_z(self):
        r,_=analyze(weekly(),items(),po(None),TODAY); self.assertAlmostEqual(r.iloc[0].Z_factor,1.881)
    def test_demand_change(self):
        r,_=analyze(weekly(),items(),po(None),TODAY,demand_change=.2); self.assertAlmostEqual(r.iloc[0].Forecast_weekly,120,places=4)
    def test_lead_delay(self):
        r,_=analyze(weekly(),items(),po(None),TODAY,lead_delay=7); self.assertEqual(r.iloc[0].Lead_time_days,35)
    def test_cost_missing_safe(self):
        i=items(); i["UNIT_COST"]="bad"; r,_=analyze(weekly(),i,po(None),TODAY); self.assertEqual(r.iloc[0].Unit_cost,0)
    def test_onhand_bad_safe(self):
        i=items(); i["ON_HAND"]="bad"; r,_=analyze(weekly(),i,po(None),TODAY); self.assertEqual(r.iloc[0].On_hand,0)
    def test_custom_period(self):
        d=pd.date_range("2026-01-01",periods=6,freq="60D"); s=pd.DataFrame({"SKU":"A","PERIOD_START":d,"PERIOD_END":d,"QUANTITY":600})
        r,_=analyze(s,items(),po(None),TODAY); self.assertEqual(r.iloc[0].Demand_frequency,"Custom")
    def test_month_ranges_preferred(self):
        days,label=infer_period_days(monthly()); self.assertTrue(28<=days<=31); self.assertEqual(label,"Monthly")
    def test_inventory_value(self):
        r,_=analyze(weekly(),items(on=100,cost=12),po(None),TODAY); self.assertEqual(r.iloc[0].Inventory_value,1200)
    def test_currency_preserved(self):
        i=items(); i["CURRENCY"]="clp"; r,_=analyze(weekly(),i,po(None),TODAY); self.assertEqual(r.iloc[0].Currency,"CLP")
    def test_no_history_safe(self):
        s=weekly().iloc[0:0]; r,_=analyze(s,items(),po(None),TODAY); self.assertEqual(r.iloc[0].Forecast_weekly,0)
    def test_single_history_safe(self):
        s=weekly().iloc[:1]; r,_=analyze(s,items(),po(None),TODAY); self.assertGreaterEqual(r.iloc[0].Forecast_weekly,0)

if __name__=="__main__": unittest.main(verbosity=2)
