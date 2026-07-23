import os
from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.requests import Request
from pydantic import BaseModel, EmailStr
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
templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), "templates"))

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


@app.get("/")
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/admin/clients", dependencies=[Depends(verify_admin)])
async def create_client(data: CreateClientRequest):
    try:
        token = await master_db.create_client(
            email=data.email,
            db_type=data.db_type,
            db_host=data.db_host,
            db_port=data.db_port,
            db_name=data.db_name,
            db_user=data.db_user,
            db_password=data.db_password,
            db_schema=data.db_schema,
        )
        base_url = os.getenv("MCP_BASE_URL", "http://localhost:8000")
        return {
            "email": data.email,
            "token": token,
            "mcp_url": f"{base_url}/mcp/{token}",
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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("ADMIN_PORT", 8001)))