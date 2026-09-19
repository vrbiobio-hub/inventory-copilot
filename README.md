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

## V22 Clean Onboarding + Purchasing Fix
- Removed the left onboarding sidebar. Language and the 4 preparation steps now live in the central page.
- Results remain a separate full-width decision workspace after Analyze.
- Hardened Purchasing against missing Supplier, Currency and Purchase_value fields and enriches analysis from ITEM_MASTER.
- Open-PO control checks required PO fields before rendering.
- Spanish UI wording cleaned up across the main experience.

## V22.1 Session-state hotfix
- Fixes NameError: items is not defined after Analyze.
- Restores sales, item master and open-PO datasets from Streamlit session_state when entering the separate Decision Workspace.
- Adds defensive DataFrame checks and clears persisted datasets on New Analysis.


## V23 Premium + Explainable UX
- Refined premium enterprise styling.
- Added plain-language explainers for WOS, safety stock, reorder point, lead time, forecast, confidence, projected stockout, excess, priority score, MOQ and order multiple.
- Relevant pages now explain what each concept means and why it matters to an entrepreneur.
- Core decision engine is unchanged.

## V24 Progressive Inventory Copilot
- Adds a Simple Mode for one-table spreadsheets with only product description, current inventory and recent monthly sales.
- Automatically creates internal item IDs; the entrepreneur does not need SKU/part numbers.
- Level 1 Basic: coverage, recent trend, low-stock/excess signals and priorities.
- Level 2 Planning: unlocked when cost and/or lead time are available.
- Level 3 Procurement: unlocked with supplier/open-PO data.
- Navigation adapts to the data available instead of showing empty modules.
- Basic Mode deliberately avoids false precision: no exact purchase quantity, financial excess or supplier claims without the required data.

## V25 Universal Smart Import
- Accepts Excel, CSV, TSV and delimited TXT files.
- Supports wide monthly tables and long transactional/database exports.
- Long format may repeat the same product on every sale; Inventory Copilot groups the product and sums sales by detected date/month/week.
- Current inventory is never summed across repeated transaction rows; the latest non-empty value is used once per product.
- Products without part numbers receive stable internal ITEM IDs while retaining the user's description.
- Optional cost, currency, lead time, supplier and location fields are detected/mapped when present and unlock richer analysis.
- The user sees how many raw rows, unique products and periods were detected before analysis.

## V26 Guided Procurement Upgrade
- Adds contextual, AI-like invitations to enrich the dataset without requiring an AI API.
- The app assesses which procurement capabilities are supported by the uploaded data.
- Missing fields are explained by business benefit, not technical requirement.
- Guides users toward lead time, cost/currency, supplier, MOQ, order multiple and open-PO data.
- Shows procurement data-maturity progress and recommends only fields that are actually missing.
- The current analysis remains usable; enrichment is optional and progressive.

## V27 Zero-Friction Copilot UX
- Removes the separate Validate Data action from the user workflow.
- Uses one primary Analyze my inventory action; validation now runs automatically behind that click.
- Reframes onboarding around “Upload what you have. Inventory Copilot will figure out the rest.”
- Keeps smart import for transactional/database exports and wide monthly files while reducing technical language.
- Shows detected rows/products near the primary action to build trust before analysis.
- Adds a lightweight “understanding your data” analysis state and only interrupts the user when an essential field truly blocks analysis.
- Keeps progressive procurement enrichment optional rather than presenting missing fields as errors.

## V28 Simple Decision Experience + Free/Premium Product Architecture
- Reduces the main results navigation to Overview, Products and Copilot.
- Overview leads with attention items and top actions instead of technical dashboards.
- Products combines inventory, demand, WOS and status in one simple place with contextual product detail.
- Forecast, scenario planning, purchasing, supplier and financial insights move into context instead of separate top-level modules.
- Copilot provides guided inventory questions in the current no-AI-API build.
- Establishes a monetization boundary: Free = core inventory health and guided answers; Premium = advanced planning, open-ended AI, scenarios, purchase recommendations, supplier/PO context and financial impact.


## V29 Adoption-First Product Experience
- Removes Free/Premium/upgrade language from the product experience.
- Keeps the strongest analysis capabilities available while product-market fit is being validated.
- Preserves the simple three-space navigation: Overview, Products, Copilot.
- Adds an adaptive “How Inventory Copilot helps” section that communicates value instead of exposing more modules.
- Shows capabilities contextually: attention prioritization, reorder timing when lead time exists, and financial visibility when cost exists.
- Missing data is framed as an optional way to improve the analysis, never as a blocker.
- Product detail keeps planning and scenario tools in context rather than behind a premium label.
- Monetization principle for a future release: keep analysis strong; charge later for continuity, automation, collaboration, integrations and operational workflow rather than weakening the core product.

## V30 Action Plan
- Adds a prominent Action Plan as the first results destination.
- Consolidates the portfolio into one executive/action report with a simple inventory-health chart.
- Converts exceptions into lightweight tasks with To do, In progress and Done states plus notes.
- Keeps healthy products visible without crowding the action list.
- Each task opens directly into the relevant product detail.
- Adds CSV export of the action report, including task status and notes.
- Preserves the simple Overview / Products / Copilot model; Action Plan acts as the first-review layer rather than another analytics module.


## V31 Conclusion-first UX
- Removes Action Plan as a top-level destination and restores Overview as the default first workspace.
- Main navigation is reduced to Overview, Products and Copilot.
- Adds a concise Inventory Copilot conclusion at the end of Overview after the supporting calculations and visuals.
- The conclusion identifies the dominant inventory issue, summarizes the evidence in minimal language, and states one priority.
- Recommended actions are hidden behind a compact expander so they are available without turning the product into a task manager.
- Removes the redundant action-summary chart, open/in-progress/completed KPI cards and task-management chrome.


## V32 Bilingual Product Status
- Product status labels now follow the selected interface language.
- Spanish UI shows Todos, Inventario bajo, Comprar pronto, Demasiado inventario and Saludable.
- English UI shows All, Running low, Reorder soon, Too much stock and Healthy.
- Canonical internal status values remain unchanged so filtering and analysis logic are unaffected.


## V33 Projection Planning
- Adds a clearly separate **Projection** mode alongside current-inventory analysis.
- Accepts future-demand files in long format (product, period, projected demand) or wide format (periods in columns).
- Product + future demand is enough to start; current inventory, unit cost, and lead time are optional enrichments.
- Keeps assumptions visually separate from actual inventory data.
- Shows one demand chart, total need, peak period, key products, and a concise Inventory Copilot conclusion.
- Includes simple -20%, -10%, Base, +10%, +20% scenario controls without exposing forecasting-model complexity.
- When current inventory is supplied, estimates coverage and the projected inventory gap; cost can translate that gap into estimated value.
