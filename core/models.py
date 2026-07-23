from dataclasses import dataclass
from typing import Optional
from enum import Enum


class DBType(str, Enum):
    MYSQL = "mysql"
    POSTGRES = "postgres"
    SQLITE = "sqlite"


@dataclass
class Client:
    id: int
    email: str
    token: str
    db_type: DBType
    db_host: str
    db_port: int
    db_name: str
    db_user: str
    db_password: str
    db_schema: Optional[str]
    is_active: bool

    def get_db_identifier(self) -> str:
        if self.db_schema:
            return self.db_schema
        return self.db_name