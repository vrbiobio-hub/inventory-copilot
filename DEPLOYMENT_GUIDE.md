# Inventory Copilot V9 — Deployment Guide

## What to upload to GitHub
Upload the **contents of this folder** to the root of one GitHub repository.

The repository root should look exactly like:

```
inventory-copilot/
├── .streamlit/
│   └── config.toml
├── .gitignore
├── streamlit_app.py
├── engine.py
├── importer.py
├── i18n.py
├── requirements.txt
└── DEPLOYMENT_GUIDE.md
```

Do **not** upload the ZIP itself as the only repository file. Extract it first, then upload the files/folder structure above.

## Streamlit Community Cloud
1. Connect Streamlit Community Cloud to the GitHub account that owns the repository.
2. Click **Create app**.
3. Choose **Yup, I have an app**.
4. Select your GitHub repository.
5. Branch: `main`.
6. Main file path / entrypoint: `streamlit_app.py`.
7. Choose an optional URL such as `inventory-copilot`.
8. No secrets are required for V9.
9. Deploy.

## Privacy during pilot
If you will test with real company inventory, purchasing, customer, supplier, pricing, or sales data, use a private repository/private app and only grant access to intended testers. Otherwise use anonymized demo data.

## Updating the app
GitHub is the source of truth. Future committed changes to the repository are picked up by Streamlit Community Cloud automatically.
