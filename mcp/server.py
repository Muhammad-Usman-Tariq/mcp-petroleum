import os
from contextlib import asynccontextmanager
from typing import AsyncIterator

from mcp.types import Tool
from core.database import MasterDB
from core.auth import validate_token, AuthError
from mcp.tools import (
    tool_list_tables, tool_describe_table, tool_query,
    tool_sales_summary, tool_stock_status, tool_invoice_totals,
    tool_month_comparison, tool_low_stock_alert, tool_top_products,
    tool_customer_summary
)

from fastapi import FastAPI, Request, HTTPException

master_db = MasterDB()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    await master_db.connect()
    yield
    await master_db.close()


app = FastAPI(lifespan=lifespan)

TOOLS = [
    Tool(name="list_tables", description="List all tables in the database",
         inputSchema={"type": "object", "properties": {}, "required": []}),

    Tool(name="describe_table", description="Get structure of a table",
         inputSchema={"type": "object", "properties": {
             "table_name": {"type": "string"}}, "required": ["table_name"]}),

    Tool(name="query", description="Run any SELECT query",
         inputSchema={"type": "object", "properties": {
             "query": {"type": "string"}}, "required": ["query"]}),

    Tool(name="sales_summary", description="Sales summary grouped by month, day or year with totals",
         inputSchema={"type": "object", "properties": {
             "date_from": {"type": "string", "description": "YYYY-MM-DD"},
             "date_to": {"type": "string", "description": "YYYY-MM-DD"},
             "group_by": {"type": "string", "enum": ["month", "day", "year"]}},
             "required": []}),

    Tool(name="stock_status", description="Current stock/inventory levels",
         inputSchema={"type": "object", "properties": {
             "low_stock_threshold": {"type": "integer"},
             "filter_low": {"type": "boolean"}}, "required": []}),

    Tool(name="invoice_totals", description="Invoice totals with optional status and date filters",
         inputSchema={"type": "object", "properties": {
             "status": {"type": "string"},
             "date_from": {"type": "string"},
             "date_to": {"type": "string"}}, "required": []}),

    Tool(name="month_comparison", description="Compare current month vs previous month",
         inputSchema={"type": "object", "properties": {
             "metric": {"type": "string", "enum": ["sales", "stock", "invoice"]}},
             "required": []}),

    Tool(name="low_stock_alert", description="Get items below stock threshold",
         inputSchema={"type": "object", "properties": {
             "threshold": {"type": "integer"}}, "required": []}),

    Tool(name="top_products", description="Top selling products by revenue",
         inputSchema={"type": "object", "properties": {
             "limit": {"type": "integer"},
             "date_from": {"type": "string"},
             "date_to": {"type": "string"}}, "required": []}),

    Tool(name="customer_summary", description="Customer list and total count",
         inputSchema={"type": "object", "properties": {
             "limit": {"type": "integer"}}, "required": []}),
]


@app.post("/mcp/{token}")
async def mcp_endpoint(token: str, request: Request):
    try:
        client = await validate_token(token, master_db)
    except AuthError as e:
        raise HTTPException(status_code=401, detail=str(e))

    body = await request.json()
    method = body.get("method")
    params = body.get("params", {})

    if method == "tools/list":
        return {"tools": [t.model_dump() for t in TOOLS]}

    if method == "tools/call":
        tool_name = params.get("name")
        arguments = params.get("arguments", {})

        if tool_name == "list_tables":
            result = await tool_list_tables(client)
        elif tool_name == "describe_table":
            result = await tool_describe_table(client, arguments["table_name"])
        elif tool_name == "query":
            result = await tool_query(client, arguments["query"])
        elif tool_name == "sales_summary":
            result = await tool_sales_summary(
                client,
                date_from=arguments.get("date_from"),
                date_to=arguments.get("date_to"),
                group_by=arguments.get("group_by", "month")
            )
        elif tool_name == "stock_status":
            result = await tool_stock_status(
                client,
                low_stock_threshold=arguments.get("low_stock_threshold", 10),
                filter_low=arguments.get("filter_low", False)
            )
        elif tool_name == "invoice_totals":
            result = await tool_invoice_totals(
                client,
                status=arguments.get("status"),
                date_from=arguments.get("date_from"),
                date_to=arguments.get("date_to")
            )
        elif tool_name == "month_comparison":
            result = await tool_month_comparison(
                client,
                metric=arguments.get("metric", "sales")
            )
        elif tool_name == "low_stock_alert":
            result = await tool_low_stock_alert(
                client,
                threshold=arguments.get("threshold", 10)
            )
        elif tool_name == "top_products":
            result = await tool_top_products(
                client,
                limit=arguments.get("limit", 10),
                date_from=arguments.get("date_from"),
                date_to=arguments.get("date_to")
            )
        elif tool_name == "customer_summary":
            result = await tool_customer_summary(
                client,
                limit=arguments.get("limit", 10)
            )
        else:
            raise HTTPException(status_code=404, detail="Tool not found")

        return {
            "content": [{"type": "text", "text": result}]
        }

    if method == "initialize":
        return {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "petroleum-mcp", "version": "1.0.0"}
        }

    raise HTTPException(status_code=400, detail="Unknown method")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("MCP_PORT", 8000)))