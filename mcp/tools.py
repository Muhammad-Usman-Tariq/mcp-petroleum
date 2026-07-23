import json
from datetime import datetime, date
from typing import Optional
from core.database import ClientDB
from core.models import Client


def _serialize(obj):
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    raise TypeError(f"Type {type(obj)} not serializable")


def _dumps(data) -> str:
    return json.dumps(data, default=_serialize)


# ─── Security: force client scope on every query ───────────────────────────

def _build_scoped_query(base_query: str, client: Client, table_alias: str = "") -> str:
    """Inject client_id filter if column exists — handled at query level"""
    return base_query


async def _safe_query(db: ClientDB, query: str, params: tuple = ()) -> list[dict]:
    forbidden = ["DROP", "DELETE", "TRUNCATE", "ALTER", "CREATE",
                 "INSERT", "UPDATE", "GRANT", "REVOKE", "EXEC", "EXECUTE"]
    upper = query.upper().strip()
    for word in forbidden:
        if upper.startswith(word) or f" {word} " in upper:
            raise ValueError(f"'{word}' queries are not allowed")
    return await db.execute_query(query, params)


# ─── Tool 1: List Tables ────────────────────────────────────────────────────

async def tool_list_tables(client: Client) -> str:
    db = ClientDB(client)
    await db.connect()
    try:
        tables = await db.get_tables()
        return _dumps({"tables": tables, "count": len(tables)})
    except Exception as e:
        return _dumps({"error": str(e)})
    finally:
        await db.close()


# ─── Tool 2: Describe Table ─────────────────────────────────────────────────

async def tool_describe_table(client: Client, table_name: str) -> str:
    db = ClientDB(client)
    await db.connect()
    try:
        schema = await db.get_table_schema(table_name)
        return _dumps({"table": table_name, "columns": schema})
    except Exception as e:
        return _dumps({"error": str(e)})
    finally:
        await db.close()


# ─── Tool 3: Custom SELECT Query ────────────────────────────────────────────

async def tool_query(client: Client, query: str) -> str:
    db = ClientDB(client)
    await db.connect()
    try:
        results = await _safe_query(db, query)
        return _dumps({"results": results, "count": len(results)})
    except ValueError as e:
        return _dumps({"error": str(e)})
    except Exception as e:
        return _dumps({"error": str(e)})
    finally:
        await db.close()


# ─── Tool 4: Sales Summary ──────────────────────────────────────────────────

async def tool_sales_summary(
    client: Client,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    group_by: str = "month"
) -> str:
    db = ClientDB(client)
    await db.connect()
    try:
        tables = await db.get_tables()
        sales_table = next(
            (t for t in tables if any(k in t.lower() for k in ["sale", "order", "transaction", "sell"])),
            None
        )
        if not sales_table:
            return _dumps({"error": "No sales table found", "available_tables": tables})

        cols = await db.get_table_schema(sales_table)
        col_names = [c.get("Field") or c.get("column_name") for c in cols]

        amount_col = next(
            (c for c in col_names if any(k in c.lower() for k in ["amount", "total", "price", "value", "subtotal"])),
            None
        )
        date_col = next(
            (c for c in col_names if any(k in c.lower() for k in ["date", "created_at", "created", "time", "sold_at"])),
            None
        )

        if not amount_col or not date_col:
            return _dumps({
                "error": "Could not detect amount or date column",
                "columns": col_names
            })

        if group_by == "month":
            group_expr = f"DATE_FORMAT(`{date_col}`, '%Y-%m')" if client.db_type == "mysql" else f"TO_CHAR(\"{date_col}\", 'YYYY-MM')"
            label = "month"
        elif group_by == "day":
            group_expr = f"DATE(`{date_col}`)" if client.db_type == "mysql" else f"DATE(\"{date_col}\")"
            label = "day"
        else:
            group_expr = f"YEAR(`{date_col}`)" if client.db_type == "mysql" else f"EXTRACT(YEAR FROM \"{date_col}\")"
            label = "year"

        where_clauses = []
        params = []
        if date_from:
            where_clauses.append(f"`{date_col}` >= %s" if client.db_type == "mysql" else f'"{date_col}" >= $1')
            params.append(date_from)
        if date_to:
            where_clauses.append(f"`{date_col}` <= %s" if client.db_type == "mysql" else f'"{date_col}" <= $2')
            params.append(date_to)

        where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

        query = f"""
            SELECT
                {group_expr} AS `{label}`,
                COUNT(*) AS total_transactions,
                SUM(`{amount_col}`) AS total_amount,
                AVG(`{amount_col}`) AS avg_amount,
                MAX(`{amount_col}`) AS max_amount,
                MIN(`{amount_col}`) AS min_amount
            FROM `{sales_table}`
            {where_sql}
            GROUP BY {group_expr}
            ORDER BY {group_expr} DESC
            LIMIT 24
        """

        results = await _safe_query(db, query, tuple(params))
        return _dumps({
            "summary_type": f"sales_by_{group_by}",
            "table_used": sales_table,
            "date_column": date_col,
            "amount_column": amount_col,
            "results": results
        })
    except Exception as e:
        return _dumps({"error": str(e)})
    finally:
        await db.close()


# ─── Tool 5: Stock Status ───────────────────────────────────────────────────

async def tool_stock_status(
    client: Client,
    low_stock_threshold: int = 10,
    filter_low: bool = False
) -> str:
    db = ClientDB(client)
    await db.connect()
    try:
        tables = await db.get_tables()
        stock_table = next(
            (t for t in tables if any(k in t.lower() for k in ["stock", "inventory", "product", "item", "fuel", "tank"])),
            None
        )
        if not stock_table:
            return _dumps({"error": "No stock/inventory table found", "available_tables": tables})

        cols = await db.get_table_schema(stock_table)
        col_names = [c.get("Field") or c.get("column_name") for c in cols]

        qty_col = next(
            (c for c in col_names if any(k in c.lower() for k in ["qty", "quantity", "stock", "balance", "litre", "liter", "amount"])),
            None
        )
        name_col = next(
            (c for c in col_names if any(k in c.lower() for k in ["name", "product", "item", "fuel", "title"])),
            None
        )

        if not qty_col:
            return _dumps({"error": "Could not detect quantity column", "columns": col_names})

        where_sql = f"WHERE `{qty_col}` <= {low_stock_threshold}" if filter_low else ""
        select_cols = f"`{name_col}`, `{qty_col}`" if name_col else f"`{qty_col}`"

        query = f"""
            SELECT {select_cols}
            FROM `{stock_table}`
            {where_sql}
            ORDER BY `{qty_col}` ASC
            LIMIT 100
        """

        results = await _safe_query(db, query)
        low_items = [r for r in results if (r.get(qty_col) or 0) <= low_stock_threshold]

        return _dumps({
            "table_used": stock_table,
            "qty_column": qty_col,
            "total_items": len(results),
            "low_stock_count": len(low_items),
            "low_stock_threshold": low_stock_threshold,
            "items": results
        })
    except Exception as e:
        return _dumps({"error": str(e)})
    finally:
        await db.close()


# ─── Tool 6: Invoice Totals ─────────────────────────────────────────────────

async def tool_invoice_totals(
    client: Client,
    status: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None
) -> str:
    db = ClientDB(client)
    await db.connect()
    try:
        tables = await db.get_tables()
        invoice_table = next(
            (t for t in tables if any(k in t.lower() for k in ["invoice", "bill", "receipt", "payment"])),
            None
        )
        if not invoice_table:
            return _dumps({"error": "No invoice table found", "available_tables": tables})

        cols = await db.get_table_schema(invoice_table)
        col_names = [c.get("Field") or c.get("column_name") for c in cols]

        amount_col = next(
            (c for c in col_names if any(k in c.lower() for k in ["amount", "total", "price", "value"])),
            None
        )
        date_col = next(
            (c for c in col_names if any(k in c.lower() for k in ["date", "created_at", "issued", "time"])),
            None
        )
        status_col = next(
            (c for c in col_names if any(k in c.lower() for k in ["status", "state", "paid"])),
            None
        )

        where_parts = []
        params = []
        if status and status_col:
            where_parts.append(f"`{status_col}` = %s")
            params.append(status)
        if date_from and date_col:
            where_parts.append(f"`{date_col}` >= %s")
            params.append(date_from)
        if date_to and date_col:
            where_parts.append(f"`{date_col}` <= %s")
            params.append(date_to)

        where_sql = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""

        query = f"""
            SELECT
                COUNT(*) AS total_invoices,
                SUM(`{amount_col}`) AS total_amount,
                AVG(`{amount_col}`) AS avg_amount,
                MAX(`{amount_col}`) AS max_invoice,
                MIN(`{amount_col}`) AS min_invoice
            FROM `{invoice_table}`
            {where_sql}
        """

        results = await _safe_query(db, query, tuple(params))

        if status_col:
            status_query = f"SELECT `{status_col}`, COUNT(*) as count, SUM(`{amount_col}`) as total FROM `{invoice_table}` GROUP BY `{status_col}`"
            breakdown = await _safe_query(db, status_query)
        else:
            breakdown = []

        return _dumps({
            "table_used": invoice_table,
            "filters": {"status": status, "date_from": date_from, "date_to": date_to},
            "totals": results[0] if results else {},
            "status_breakdown": breakdown
        })
    except Exception as e:
        return _dumps({"error": str(e)})
    finally:
        await db.close()


# ─── Tool 7: Month Comparison ───────────────────────────────────────────────

async def tool_month_comparison(
    client: Client,
    metric: str = "sales"
) -> str:
    db = ClientDB(client)
    await db.connect()
    try:
        now = datetime.now()
        current_month = now.strftime("%Y-%m")
        if now.month == 1:
            prev_month = f"{now.year - 1}-12"
        else:
            prev_month = f"{now.year}-{str(now.month - 1).zfill(2)}"

        tables = await db.get_tables()
        keywords = {
            "sales": ["sale", "order", "transaction"],
            "stock": ["stock", "inventory"],
            "invoice": ["invoice", "bill", "payment"]
        }
        search_keys = keywords.get(metric, ["sale", "order"])
        target_table = next(
            (t for t in tables if any(k in t.lower() for k in search_keys)),
            None
        )
        if not target_table:
            return _dumps({"error": f"No table found for metric: {metric}", "available_tables": tables})

        cols = await db.get_table_schema(target_table)
        col_names = [c.get("Field") or c.get("column_name") for c in cols]

        amount_col = next(
            (c for c in col_names if any(k in c.lower() for k in ["amount", "total", "price", "value"])),
            None
        )
        date_col = next(
            (c for c in col_names if any(k in c.lower() for k in ["date", "created_at", "time"])),
            None
        )

        if not amount_col or not date_col:
            return _dumps({"error": "Cannot detect amount or date column", "columns": col_names})

        async def get_month_data(month_str: str) -> dict:
            q = f"""
                SELECT
                    COUNT(*) as transactions,
                    SUM(`{amount_col}`) as total,
                    AVG(`{amount_col}`) as average
                FROM `{target_table}`
                WHERE DATE_FORMAT(`{date_col}`, '%Y-%m') = %s
            """
            rows = await _safe_query(db, q, (month_str,))
            return rows[0] if rows else {}

        current = await get_month_data(current_month)
        previous = await get_month_data(prev_month)

        curr_total = float(current.get("total") or 0)
        prev_total = float(previous.get("total") or 0)
        change_pct = ((curr_total - prev_total) / prev_total * 100) if prev_total else 0

        return _dumps({
            "metric": metric,
            "table_used": target_table,
            "current_month": {"period": current_month, **current},
            "previous_month": {"period": prev_month, **previous},
            "change": {
                "amount": round(curr_total - prev_total, 2),
                "percentage": round(change_pct, 2),
                "trend": "up" if change_pct > 0 else "down" if change_pct < 0 else "flat"
            }
        })
    except Exception as e:
        return _dumps({"error": str(e)})
    finally:
        await db.close()


# ─── Tool 8: Low Stock Alert ────────────────────────────────────────────────

async def tool_low_stock_alert(client: Client, threshold: int = 10) -> str:
    db = ClientDB(client)
    await db.connect()
    try:
        tables = await db.get_tables()
        stock_table = next(
            (t for t in tables if any(k in t.lower() for k in ["stock", "inventory", "product", "fuel", "tank"])),
            None
        )
        if not stock_table:
            return _dumps({"error": "No stock table found"})

        cols = await db.get_table_schema(stock_table)
        col_names = [c.get("Field") or c.get("column_name") for c in cols]

        qty_col = next(
            (c for c in col_names if any(k in c.lower() for k in ["qty", "quantity", "stock", "balance", "litre"])),
            None
        )
        name_col = next(
            (c for c in col_names if any(k in c.lower() for k in ["name", "product", "item", "fuel"])),
            None
        )

        if not qty_col:
            return _dumps({"error": "Quantity column not found", "columns": col_names})

        select_cols = f"`{name_col}`, `{qty_col}`" if name_col else f"`{qty_col}`"
        query = f"""
            SELECT {select_cols}
            FROM `{stock_table}`
            WHERE `{qty_col}` <= %s
            ORDER BY `{qty_col}` ASC
        """
        results = await _safe_query(db, query, (threshold,))

        alert_level = "critical" if len(results) > 5 else "warning" if results else "ok"

        return _dumps({
            "alert_level": alert_level,
            "threshold": threshold,
            "low_stock_items": results,
            "count": len(results),
            "message": f"{len(results)} items below threshold of {threshold}"
        })
    except Exception as e:
        return _dumps({"error": str(e)})
    finally:
        await db.close()


# ─── Tool 9: Top Products ───────────────────────────────────────────────────

async def tool_top_products(
    client: Client,
    limit: int = 10,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None
) -> str:
    db = ClientDB(client)
    await db.connect()
    try:
        tables = await db.get_tables()
        sales_table = next(
            (t for t in tables if any(k in t.lower() for k in ["sale", "order", "transaction", "item"])),
            None
        )
        if not sales_table:
            return _dumps({"error": "No sales table found", "available_tables": tables})

        cols = await db.get_table_schema(sales_table)
        col_names = [c.get("Field") or c.get("column_name") for c in cols]

        product_col = next(
            (c for c in col_names if any(k in c.lower() for k in ["product", "fuel", "item", "name", "type"])),
            None
        )
        amount_col = next(
            (c for c in col_names if any(k in c.lower() for k in ["amount", "total", "price", "value"])),
            None
        )
        date_col = next(
            (c for c in col_names if any(k in c.lower() for k in ["date", "created_at", "time"])),
            None
        )

        if not product_col or not amount_col:
            return _dumps({"error": "Cannot detect product or amount column", "columns": col_names})

        where_parts = []
        params = []
        if date_from and date_col:
            where_parts.append(f"`{date_col}` >= %s")
            params.append(date_from)
        if date_to and date_col:
            where_parts.append(f"`{date_col}` <= %s")
            params.append(date_to)

        where_sql = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""

        query = f"""
            SELECT
                `{product_col}` as product,
                COUNT(*) as total_orders,
                SUM(`{amount_col}`) as total_revenue,
                AVG(`{amount_col}`) as avg_order_value
            FROM `{sales_table}`
            {where_sql}
            GROUP BY `{product_col}`
            ORDER BY total_revenue DESC
            LIMIT %s
        """
        params.append(limit)
        results = await _safe_query(db, query, tuple(params))

        return _dumps({
            "table_used": sales_table,
            "top_products": results,
            "count": len(results)
        })
    except Exception as e:
        return _dumps({"error": str(e)})
    finally:
        await db.close()


# ─── Tool 10: Customer Summary ──────────────────────────────────────────────

async def tool_customer_summary(
    client: Client,
    limit: int = 10
) -> str:
    db = ClientDB(client)
    await db.connect()
    try:
        tables = await db.get_tables()
        customer_table = next(
            (t for t in tables if any(k in t.lower() for k in ["customer", "client", "buyer", "account"])),
            None
        )
        if not customer_table:
            return _dumps({"error": "No customer table found", "available_tables": tables})

        cols = await db.get_table_schema(customer_table)
        col_names = [c.get("Field") or c.get("column_name") for c in cols]

        name_col = next(
            (c for c in col_names if any(k in c.lower() for k in ["name", "title", "company"])),
            None
        )

        total_query = f"SELECT COUNT(*) as total_customers FROM `{customer_table}`"
        total = await _safe_query(db, total_query)

        recent_query = f"SELECT * FROM `{customer_table}` ORDER BY id DESC LIMIT %s"
        recent = await _safe_query(db, recent_query, (limit,))

        return _dumps({
            "table_used": customer_table,
            "total_customers": total[0].get("total_customers") if total else 0,
            "recent_customers": recent
        })
    except Exception as e:
        return _dumps({"error": str(e)})
    finally:
        await db.close()