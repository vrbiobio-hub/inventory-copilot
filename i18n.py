TEXT={
"es":{
"title":"Tu inventario, explicado de forma simple",
"subtitle":"Sube tus datos. Inventory Copilot identifica las columnas, revisa la calidad de la información y te muestra qué comprar, qué no comprar y dónde existe riesgo.",
"upload":"Sube tu Excel o CSV","progress":"Tu progreso","scenario":"Escenario",
"sales_change":"Cambio esperado en ventas","lead_change":"Cambio en tiempo de entrega (días)","coverage":"Cobertura deseada después de recibir",
"step1":"PASO 1 DE 3","where":"¿Dónde está cada tipo de información?","sales":"Historial de ventas","items":"Inventario / maestro de artículos","po":"Órdenes de compra abiertas",
"preview":"Vista previa de las tablas seleccionadas","step2":"PASO 2 DE 3","confirm":"Confirma qué significa cada columna",
"confirm_help":"Ya hicimos una primera sugerencia automática. Cambia solamente lo que no coincida con tus datos.",
"step3":"PASO 3 DE 3","review":"Revisión de datos","ready":"Listo para analizar","analyze":"Analizar mi inventario →",
"dashboard":"Tu inventario hoy","dashboard_help":"Primero mostramos decisiones. Los términos técnicos quedan disponibles cuando los necesites.",
"urgent":"Necesitan acción urgente","buysoon":"Comprar pronto","excess_products":"Productos con exceso","excess_money":"Dinero estimado en exceso","suggested_buy":"Compras sugeridas",
"attention":"Qué necesita tu atención","current":"Inventario actual","weekly":"Demanda esperada / semana","confidence":"Confianza",
"qty":"Cantidad sugerida","value":"Valor estimado","stockout":"Posible quiebre","all":"Todos los productos","detail":"Revisa un producto",
"executive":"Resumen ejecutivo","whatbuy":"Qué comprar","risk":"Riesgo de quiebre","excess":"Exceso","forecast":"Forecast","simulator":"Simulador",
"language":"Idioma / Language"
},
"en":{
"title":"Your inventory, explained simply",
"subtitle":"Upload your data. Inventory Copilot identifies the columns, checks data quality, and shows what to buy, what not to buy, and where stockout risk exists.",
"upload":"Upload your Excel or CSV","progress":"Your progress","scenario":"Scenario",
"sales_change":"Expected sales change","lead_change":"Lead-time change (days)","coverage":"Desired coverage after receipt",
"step1":"STEP 1 OF 3","where":"Where is each type of information?","sales":"Sales history","items":"Inventory / item master","po":"Open purchase orders",
"preview":"Preview selected tables","step2":"STEP 2 OF 3","confirm":"Confirm what each column means",
"confirm_help":"We made an automatic first suggestion. Change only what does not match your data.",
"step3":"STEP 3 OF 3","review":"Data review","ready":"Ready to analyze","analyze":"Analyze my inventory →",
"dashboard":"Your inventory today","dashboard_help":"We show decisions first. Technical terms are available when you need them.",
"urgent":"Need urgent action","buysoon":"Buy soon","excess_products":"Products with excess","excess_money":"Estimated excess value","suggested_buy":"Suggested purchases",
"attention":"What needs your attention","current":"Current inventory","weekly":"Expected demand / week","confidence":"Confidence",
"qty":"Suggested quantity","value":"Estimated value","stockout":"Possible stockout","all":"All products","detail":"Review a product",
"executive":"Executive summary","whatbuy":"What to buy","risk":"Stockout risk","excess":"Excess","forecast":"Forecast","simulator":"Simulator",
"language":"Idioma / Language"
}}
def tr(lang,key): return TEXT.get(lang,TEXT["es"]).get(key,key)
