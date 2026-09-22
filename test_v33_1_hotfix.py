import ast
from pathlib import Path
p=Path("streamlit_app.py")
s=p.read_text(encoding="utf-8")
assert "def ensure_category_key(view):" in s
assert 'view=ensure_category_key(view)\n\nif workspace in ["Resumen","Summary"]:' in s
ast.parse(s)
print("V33.1 category hotfix regression: PASS")
