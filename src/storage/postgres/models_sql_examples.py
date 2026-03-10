from datetime import datetime
from typing import List, Optional

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from pgvector.sqlalchemy import VECTOR
from pydantic import BaseModel
from sqlalchemy import Column, Text, BigInteger, DateTime, Identity, Boolean
from sqlalchemy.dialects.postgresql import JSONB

from src.storage.postgres.models_business import Base

class SqlExample(Base):
    __tablename__ = "sql_examples"
    id = Column(BigInteger, Identity(always=True), primary_key=True)
    create_time = Column(DateTime(timezone=False), nullable=True)
    description = Column(Text, nullable=True)
    embedding = Column(VECTOR(), nullable=True)
    sql = Column(Text, nullable=True)
    datasource_host = Column(String(255), nullable=False)
    datasource_port= Column(Integer, nullable=False)
    enabled = Column(Boolean, default=True)


class SqlExampleInfo(BaseModel):
    id: Optional[int] = None
    create_time: Optional[datetime] = None
    description: Optional[str] = None
    sql: Optional[str] = None
    datasource_host: Optional[str] = None
    datasource_port: Optional[int] = None
    enabled: Optional[bool] = True
