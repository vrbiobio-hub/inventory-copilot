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

## V16 Focus Workspace
- Sidebar hides automatically after a successful analysis.
- Upload / mapping / validation steps disappear after analysis.
- A compact "New analysis" action restores the upload workflow.
- Summary, Actions, Inventory, Forecast and Simulator are large workspace buttons.
- Only one workspace renders at a time, giving each module the full page width.
- Prepared datasets are persisted in session state so SKU detail and simulations still work.

## V17 Category Drill-down
- Four category cards in Action Center: Urgent, Buy soon, Excess, Monitor.
- Each category opens a dedicated full-width workspace.
- Category detail explains why SKUs are there and what operational actions to execute.
- KPI summary by category: SKU count, financial impact, average WOS and average days to stockout.
- Ranking within category preserves global priority and shows the reason behind each SKU position.
- Category and ranking remain separate concepts.

## V17.1 Fix
- Verified category cards render at the top of Action Center.
- Each card opens a dedicated category workspace.
- Category workspace includes KPIs, explanation, execution guidance, ranked SKUs and direct SKU detail access.

## V18 Currency + Inventory Value
- Validate Data now needs only one click; a successful validation reruns immediately and enables Analyze.
- ITEM_MASTER supports CURRENCY / MONEDA with ISO-style 3-letter codes such as USD, CLP, COP and MXN.
- Engine calculates current inventory value = ON_HAND × UNIT_COST.
- Portfolio inventory value is displayed after analysis.
- Different currencies are never added together or silently converted.
- Missing currency is shown separately as Unspecified / Sin moneda rather than assuming USD.

## V19
Adds Purchase Planner, Open PO Control Tower, Supplier Exposure, Inventory Capital and Data Health using the existing input model. Currency values are always kept separate.

## V21 Decision Workspace
- Onboarding/upload/validation and analysis results are now separate application states.
- Clicking Analyze successfully transitions directly to the Decision Center; setup steps no longer remain above results.
- Results hide the sidebar and use a full-width workspace.
- New Analysis returns to onboarding.
- Summary is reframed as a Decision Center while preserving all V20 modules and category drill-down.
