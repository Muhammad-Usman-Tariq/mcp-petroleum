import aiomysql
import asyncpg
import os
import re
from typing import Optional
from core.models import Client, DBType
from core.auth import hash_token


# ─── Query Security Layer ────────────────────────────────────────────────────

FORBIDDEN_KEYWORDS = [
    "DROP", "DELETE", "TRUNCATE", "ALTER", "CREATE",
    "INSERT", "UPDATE", "GRANT", "REVOKE", "EXEC",
    "EXECUTE", "CALL", "LOAD", "OUTFILE", "DUMPFILE",
    "INTO", "INFORMATION_SCHEMA", "SLEEP", "BENCHMARK"
]

MAX_QUERY_LENGTH = 2000
MAX_ROWS_RETURNED = 500


def validate_query(query: str) -> str:
    if len(query) > MAX_QUERY_LENGTH:
        raise ValueError(f"Query too long. Max {MAX_QUERY_LENGTH} chars allowed.")

    cleaned = query.upper().strip()

    if not cleaned.startswith("SELECT") and not cleaned.startswith("SHOW") and not cleaned.startswith("DESCRIBE"):
        raise ValueError("Only SELECT, SHOW, DESCRIBE queries are allowed.")

    for keyword in FORBIDDEN_KEYWORDS:
        pattern = rf'\b{keyword}\b'
        if re.search(pattern, cleaned):
            raise ValueError(f"Forbidden keyword '{keyword}' detected in query.")

    if "--" in query or "/*" in query or "*/" in query:
        raise ValueError("SQL comments are not allowed.")

    if ";" in query.rstrip(";"):
        raise ValueError("Multiple statements are not allowed.")

    return query.rstrip(";")


# ─── Master DB ───────────────────────────────────────────────────────────────

class MasterDB:
    def __init__(self):
        self.pool = None

    async def connect(self):
        self.pool = await aiomysql.create_pool(
            host=os.getenv("MASTER_DB_HOST"),
            port=int(os.getenv("MASTER_DB_PORT", 3306)),
            user=os.getenv("MASTER_DB_USER"),
            password=os.getenv("MASTER_DB_PASSWORD"),
            db=os.getenv("MASTER_DB_NAME"),
            autocommit=True,
            minsize=1,
            maxsize=10,
        )
        await self._init_tables()

    async def _init_tables(self):
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("""
                    CREATE TABLE IF NOT EXISTS clients (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        email VARCHAR(255) UNIQUE NOT NULL,
                        token_hash VARCHAR(255) UNIQUE NOT NULL,
                        db_type VARCHAR(20) NOT NULL DEFAULT 'mysql',
                        db_host VARCHAR(255) NOT NULL,
                        db_port INT NOT NULL DEFAULT 3306,
                        db_name VARCHAR(255) NOT NULL,
                        db_user VARCHAR(255) NOT NULL,
                        db_password VARCHAR(255) NOT NULL,
                        db_schema VARCHAR(255),
                        is_active BOOLEAN DEFAULT TRUE,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                await cur.execute("""
                    CREATE TABLE IF NOT EXISTS query_logs (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        client_id INT NOT NULL,
                        query_text TEXT,
                        tool_name VARCHAR(100),
                        status VARCHAR(20),
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        INDEX idx_client_id (client_id),
                        INDEX idx_created_at (created_at)
                    )
                """)
                await cur.execute("""
                    CREATE TABLE IF NOT EXISTS rate_limits (
                        client_id INT NOT NULL,
                        window_start TIMESTAMP NOT NULL,
                        request_count INT DEFAULT 1,
                        PRIMARY KEY (client_id, window_start)
                    )
                """)

    async def get_client_by_token(self, token_hash: str) -> Optional[Client]:
        async with self.pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(
                    "SELECT * FROM clients WHERE token_hash = %s AND is_active = TRUE",
                    (token_hash,)
                )
                row = await cur.fetchone()
                if not row:
                    return None
                return Client(
                    id=row["id"],
                    email=row["email"],
                    token=token_hash,
                    db_type=DBType(row["db_type"]),
                    db_host=row["db_host"],
                    db_port=row["db_port"],
                    db_name=row["db_name"],
                    db_user=row["db_user"],
                    db_password=row["db_password"],
                    db_schema=row["db_schema"],
                    is_active=row["is_active"]
                )

    async def check_rate_limit(self, client_id: int, max_requests: int = 60) -> bool:
        """60 requests per minute per client"""
        async with self.pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute("""
                    INSERT INTO rate_limits (client_id, window_start, request_count)
                    VALUES (%s, DATE_FORMAT(NOW(), '%Y-%m-%d %H:%i:00'), 1)
                    ON DUPLICATE KEY UPDATE request_count = request_count + 1
                """, (client_id,))

                await cur.execute("""
                    SELECT request_count FROM rate_limits
                    WHERE client_id = %s
                    AND window_start = DATE_FORMAT(NOW(), '%Y-%m-%d %H:%i:00')
                """, (client_id,))

                row = await cur.fetchone()
                if row and row["request_count"] > max_requests:
                    return False
                return True

    async def log_query(self, client_id: int, tool_name: str, query_text: str, status: str):
        try:
            async with self.pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute("""
                        INSERT INTO query_logs (client_id, tool_name, query_text, status)
                        VALUES (%s, %s, %s, %s)
                    """, (client_id, tool_name, query_text[:1000], status))
        except Exception:
            pass

    async def create_client(self, email: str, db_type: str, db_host: str,
                            db_port: int, db_name: str, db_user: str,
                            db_password: str, db_schema: Optional[str] = None) -> str:
        from core.auth import generate_token, hash_token
        token = generate_token()
        t_hash = hash_token(token)
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("""
                    INSERT INTO clients (email, token_hash, db_type, db_host, db_port,
                    db_name, db_user, db_password, db_schema)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (email, t_hash, db_type, db_host, db_port,
                      db_name, db_user, db_password, db_schema))
        return token

    async def list_clients(self) -> list:
        async with self.pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(
                    "SELECT id, email, db_type, db_host, db_name, db_schema, is_active, created_at FROM clients"
                )
                return await cur.fetchall()

    async def deactivate_client(self, email: str):
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "UPDATE clients SET is_active = FALSE WHERE email = %s", (email,)
                )

    async def close(self):
        if self.pool:
            self.pool.close()
            await self.pool.wait_closed()


# ─── Client DB ───────────────────────────────────────────────────────────────

class ClientDB:
    def __init__(self, client: Client):
        self.client = client
        self.pool = None

    async def connect(self):
        if self.client.db_type == DBType.MYSQL:
            self.pool = await aiomysql.create_pool(
                host=self.client.db_host,
                port=self.client.db_port,
                user=self.client.db_user,
                password=self.client.db_password,
                db=self.client.db_name,
                autocommit=True,
                minsize=1,
                maxsize=5,
                connect_timeout=10,
            )
        elif self.client.db_type == DBType.POSTGRES:
            self.pool = await asyncpg.create_pool(
                host=self.client.db_host,
                port=self.client.db_port,
                user=self.client.db_user,
                password=self.client.db_password,
                database=self.client.db_name,
                timeout=10,
            )

    async def execute_query(self, query: str, params: tuple = ()) -> list[dict]:
        safe_query = validate_query(query)

        if self.client.db_type == DBType.MYSQL:
            return await self._mysql_query(safe_query, params)
        elif self.client.db_type == DBType.POSTGRES:
            return await self._postgres_query(safe_query, params)
        return []

    async def _mysql_query(self, query: str, params: tuple) -> list[dict]:
        schema = self.client.db_schema or self.client.db_name
        async with self.pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(f"USE `{schema}`")
                await cur.execute(query, params or None)
                rows = await cur.fetchmany(MAX_ROWS_RETURNED)
                return list(rows)

    async def _postgres_query(self, query: str, params: tuple) -> list[dict]:
        schema = self.client.db_schema or "public"
        async with self.pool.acquire() as conn:
            await conn.execute(f"SET search_path TO {schema}, public")
            await conn.execute("SET statement_timeout = '10s'")
            rows = await conn.fetch(query, *params)
            return [dict(r) for r in rows[:MAX_ROWS_RETURNED]]

    async def get_tables(self) -> list[str]:
        if self.client.db_type == DBType.MYSQL:
            schema = self.client.db_schema or self.client.db_name
            rows = await self._mysql_query("SHOW TABLES", ())
            return [list(r.values())[0] for r in rows]
        elif self.client.db_type == DBType.POSTGRES:
            schema = self.client.db_schema or "public"
            rows = await self._postgres_query(
                "SELECT tablename FROM pg_tables WHERE schemaname = $1", (schema,)
            )
            return [r["tablename"] for r in rows]
        return []

    async def get_table_schema(self, table_name: str) -> list[dict]:
        clean_table = re.sub(r'[^a-zA-Z0-9_]', '', table_name)
        if not clean_table:
            raise ValueError("Invalid table name")

        if self.client.db_type == DBType.MYSQL:
            rows = await self._mysql_query(f"DESCRIBE `{clean_table}`", ())
            return list(rows)
        elif self.client.db_type == DBType.POSTGRES:
            rows = await self._postgres_query("""
                SELECT column_name, data_type, is_nullable
                FROM information_schema.columns
                WHERE table_name = $1 AND table_schema = $2
            """, (clean_table, self.client.db_schema or "public"))
            return list(rows)
        return []

    async def close(self):
        if self.pool:
            if self.client.db_type == DBType.MYSQL:
                self.pool.close()
                await self.pool.wait_closed()
            else:
                await self.pool.close()