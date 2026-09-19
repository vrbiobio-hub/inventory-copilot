import pandas as pd
from importer import validate_dataset
sales=pd.DataFrame({"SKU":["A100","B200",None,None],"QUANTITY":[10,20,None,None],"PERIOD_START":["2026-01-01","2026-01-08",None,None]})
assert not any(level=="error" for level,msg in validate_dataset(sales,"sales"))
items=pd.DataFrame({"SKU":["A100",None],"DESCRIPTION":["Door",None],"ON_HAND":[100,None],"UNIT_COST":[50,None],"LEAD_TIME_DAYS":[30,None]})
assert not any(level=="error" for level,msg in validate_dataset(items,"items"))
po=pd.DataFrame({"SKU":["A100",None],"QUANTITY":[50,None],"EXPECTED_DATE":["2026-10-01",None]})
assert not any(level=="error" for level,msg in validate_dataset(po,"po"))
print("3/3 V10 blank-row regression tests passed")
