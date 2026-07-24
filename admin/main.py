import os
import pathlib
from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.requests import Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import Optional
from contextlib import asynccontextmanager
from typing import AsyncIterator

from core.database import MasterDB

master_db = MasterDB()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    await master_db.connect()
    yield
    await master_db.close()


app = FastAPI(lifespan=lifespan)

ADMIN_SECRET = os.getenv("ADMIN_SECRET", "change-me-in-production")


def verify_admin(x_admin_secret: str = Header(...)):
    if x_admin_secret != ADMIN_SECRET:
        raise HTTPException(status_code=403, detail="Forbidden")


class CreateClientRequest(BaseModel):
    email: str
    db_type: str = "mysql"
    db_host: str
    db_port: int = 3306
    db_name: str
    db_user: str
    db_password: str
    db_schema: Optional[str] = None


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    html_file = pathlib.Path(__file__).parent / "templates" / "index.html"
    return HTMLResponse(content=html_file.read_text())


@app.post("/admin/clients", dependencies=[Depends(verify_admin)])
async def create_client(data: CreateClientRequest):
    try:
        base_url = os.getenv("MCP_BASE_URL", "http://localhost:8000")
        token = await master_db.create_client(
            email=data.email,
            db_type=data.db_type,
            db_host=data.db_host,
            db_port=data.db_port,
            db_name=data.db_name,
            db_user=data.db_user,
            db_password=data.db_password,
            db_schema=data.db_schema,
            mcp_url=f"{base_url}/mcp/TEMP",
        )
        mcp_url = f"{base_url}/mcp/{token}"
        async with master_db.pool.acquire() as conn:
            await conn.execute("UPDATE clients SET mcp_url = $1 WHERE email = $2", mcp_url, data.email)
        return {
            "email": data.email,
            "token": token,
            "mcp_url": mcp_url,
            "instructions": "Add this URL in your LLM MCP settings"
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))



@app.get("/admin/clients", dependencies=[Depends(verify_admin)])
async def list_clients():
    clients = await master_db.list_clients()
    return {"clients": clients}


@app.delete("/admin/clients/{email}", dependencies=[Depends(verify_admin)])
async def deactivate_client(email: str):
    await master_db.deactivate_client(email)
    return {"message": f"Client {email} deactivated"}

@app.post("/admin/clients/{email}/regenerate", dependencies=[Depends(verify_admin)])
async def regenerate_client(email: str):
    try:
        base_url = os.getenv("MCP_BASE_URL", "http://localhost:8000")
        token = await master_db.regenerate_token(email, mcp_url=f"{base_url}/mcp/TEMP")
        mcp_url = f"{base_url}/mcp/{token}"
        async with master_db.pool.acquire() as conn:
            await conn.execute("UPDATE clients SET mcp_url = $1 WHERE email = $2", mcp_url, email)
        return {"token": token, "mcp_url": mcp_url}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("ADMIN_PORT", 8001)))