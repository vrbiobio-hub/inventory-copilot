# Inventory Copilot

Bilingual inventory decision-support MVP for Excel/CSV users.

## Capabilities
- Spanish / English interface
- Flexible bilingual column mapping
- Data validation before analysis
- Forecast model selection
- Purchase recommendations
- Stockout risk
- Excess inventory
- 26-week projection
- Scenario testing
- No AI API required

## Local run
```bash
pip install -r requirements.txt
streamlit run streamlit_app.py
```

See `DEPLOYMENT_GUIDE.md` for Streamlit Community Cloud deployment.

## V10 UX corrections
- Explicit Validate Data button before analysis
- Blank spreadsheet rows ignored
- Friendly mapping labels
- Validation counts invalid business rows instead of treating formatting tails as data

## V11 Enterprise UI
- ERP-inspired enterprise visual language (original Inventory Copilot styling; no SAP/Oracle branding copied)
- Compact KPI cards and data-forward layout
- Exact numeric scenario inputs instead of sliders
- Apply Scenario and Reset Scenario controls
- Scenario controls only appear after analysis
- Current scenario always visible

## V12 Exception Management
- Action Center is now the primary dashboard.
- Top 25 exceptions are ranked before SKU-level detail.
- Search and action filters support large SKU portfolios.
- Priority reason is visible and auditable.
- SKU detail is opened on demand rather than rendered for every item.
- SKU detail includes projection, forecast, open POs, explanation, and scenario controls.
