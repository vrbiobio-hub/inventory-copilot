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

## V13 Category + Priority UX
- Category and priority ranking are separate concepts.
- Action Center can be filtered by category.
- Ranking remains global within the analyzed portfolio.
- Cleaner executive table.
- Validation and Analyze actions are visually promoted in the review step.
- Obvious demo/instruction rows are excluded before analysis.

## V14 Priority Engine + Top Workflow Actions
- Category and ranking remain independent.
- Global priority score (0–100) uses stockout timing, replenishment feasibility, financial exposure, and demand exposure.
- Forecast confidence is displayed but does not suppress a real operational urgency.
- Ranking is auditable with a visible score.
- Validate Data and Analyze Inventory controls are rendered above the file uploader; Analyze stays disabled until validation succeeds.

## V15 Workspace Navigation
- Results are split into separate workspaces: Summary, Actions, Inventory, Forecast, Simulator.
- Only one workspace is rendered at a time, reducing vertical scrolling.
- SKU detail is a dedicated screen with Back navigation.
- SKU detail uses tabs for Summary, Projection, Forecast, Open POs and Simulator.
- V14 ranking/category logic is preserved.
