from mcpserver.tools import (
    tool_list_tables, tool_describe_table, tool_query,
    tool_sales_summary, tool_stock_status, tool_invoice_totals,
    tool_month_comparison, tool_low_stock_alert, tool_top_products,
    tool_customer_summary
)


async def call_tool(tool_name: str, arguments: dict, client):
    if tool_name == "list_tables":
        return await tool_list_tables(client)
    elif tool_name == "describe_table":
        return await tool_describe_table(client, arguments["table_name"])
    elif tool_name == "query":
        return await tool_query(client, arguments["query"])
    elif tool_name == "sales_summary":
        return await tool_sales_summary(client,
            date_from=arguments.get("date_from"),
            date_to=arguments.get("date_to"),
            group_by=arguments.get("group_by", "month"))
    elif tool_name == "stock_status":
        return await tool_stock_status(client,
            low_stock_threshold=arguments.get("low_stock_threshold", 10),
            filter_low=arguments.get("filter_low", False))
    elif tool_name == "invoice_totals":
        return await tool_invoice_totals(client,
            status=arguments.get("status"),
            date_from=arguments.get("date_from"),
            date_to=arguments.get("date_to"))
    elif tool_name == "month_comparison":
        return await tool_month_comparison(client,
            metric=arguments.get("metric", "sales"))
    elif tool_name == "low_stock_alert":
        return await tool_low_stock_alert(client,
            threshold=arguments.get("threshold", 10))
    elif tool_name == "top_products":
        return await tool_top_products(client,
            limit=arguments.get("limit", 10),
            date_from=arguments.get("date_from"),
            date_to=arguments.get("date_to"))
    elif tool_name == "customer_summary":
        return await tool_customer_summary(client,
            limit=arguments.get("limit", 10))
    return "Tool not found"


TOOLS_OPENAI = [
    {"type": "function", "function": {"name": "list_tables", "description": "List all tables in the database", "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {"name": "describe_table", "description": "Get structure of a table", "parameters": {"type": "object", "properties": {"table_name": {"type": "string"}}, "required": ["table_name"]}}},
    {"type": "function", "function": {"name": "query", "description": "Run any SELECT query", "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}},
    {"type": "function", "function": {"name": "sales_summary", "description": "Sales summary by month/day/year", "parameters": {"type": "object", "properties": {"date_from": {"type": "string"}, "date_to": {"type": "string"}, "group_by": {"type": "string", "enum": ["month", "day", "year"]}}, "required": []}}},
    {"type": "function", "function": {"name": "stock_status", "description": "Current stock/inventory levels", "parameters": {"type": "object", "properties": {"low_stock_threshold": {"type": "integer"}, "filter_low": {"type": "boolean"}}, "required": []}}},
    {"type": "function", "function": {"name": "invoice_totals", "description": "Invoice totals with filters", "parameters": {"type": "object", "properties": {"status": {"type": "string"}, "date_from": {"type": "string"}, "date_to": {"type": "string"}}, "required": []}}},
    {"type": "function", "function": {"name": "month_comparison", "description": "Compare current vs previous month", "parameters": {"type": "object", "properties": {"metric": {"type": "string", "enum": ["sales", "stock", "invoice"]}}, "required": []}}},
    {"type": "function", "function": {"name": "low_stock_alert", "description": "Items below stock threshold", "parameters": {"type": "object", "properties": {"threshold": {"type": "integer"}}, "required": []}}},
    {"type": "function", "function": {"name": "top_products", "description": "Top selling products by revenue", "parameters": {"type": "object", "properties": {"limit": {"type": "integer"}, "date_from": {"type": "string"}, "date_to": {"type": "string"}}, "required": []}}},
    {"type": "function", "function": {"name": "customer_summary", "description": "Customer list and total count", "parameters": {"type": "object", "properties": {"limit": {"type": "integer"}}, "required": []}}},
]

TOOLS_GEMINI = [
    {"name": "list_tables", "description": "List all tables in the database", "parameters": {"type": "object", "properties": {}, "required": []}},
    {"name": "describe_table", "description": "Get structure of a table", "parameters": {"type": "object", "properties": {"table_name": {"type": "string"}}, "required": ["table_name"]}},
    {"name": "query", "description": "Run any SELECT query", "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}},
    {"name": "sales_summary", "description": "Sales summary by month/day/year", "parameters": {"type": "object", "properties": {"date_from": {"type": "string"}, "date_to": {"type": "string"}, "group_by": {"type": "string"}}, "required": []}},
    {"name": "stock_status", "description": "Current stock levels", "parameters": {"type": "object", "properties": {"low_stock_threshold": {"type": "integer"}, "filter_low": {"type": "boolean"}}, "required": []}},
    {"name": "invoice_totals", "description": "Invoice totals with filters", "parameters": {"type": "object", "properties": {"status": {"type": "string"}, "date_from": {"type": "string"}, "date_to": {"type": "string"}}, "required": []}},
    {"name": "month_comparison", "description": "Compare current vs previous month", "parameters": {"type": "object", "properties": {"metric": {"type": "string"}}, "required": []}},
    {"name": "low_stock_alert", "description": "Items below stock threshold", "parameters": {"type": "object", "properties": {"threshold": {"type": "integer"}}, "required": []}},
    {"name": "top_products", "description": "Top selling products", "parameters": {"type": "object", "properties": {"limit": {"type": "integer"}, "date_from": {"type": "string"}, "date_to": {"type": "string"}}, "required": []}},
    {"name": "customer_summary", "description": "Customer list", "parameters": {"type": "object", "properties": {"limit": {"type": "integer"}}, "required": []}},
]