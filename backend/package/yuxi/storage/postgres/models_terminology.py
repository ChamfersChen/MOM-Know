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

from yuxi.storage.postgres.models_business import Base

class Terminology(Base):
    __tablename__ = "terminology"
    id = Column(BigInteger, Identity(always=True), primary_key=True)
    pid = Column(BigInteger, nullable=True)
    create_time = Column(DateTime(timezone=False), nullable=True)
    word = Column(String(255), nullable=True)
    description = Column(Text, nullable=True)
    embedding = Column(VECTOR(), nullable=True)
    specific_ds = Column(Boolean, default=False)
    datasource_host = Column(String(255), nullable=False)
    datasource_port= Column(Integer, nullable=False)
    enabled = Column(Boolean, default=True)


class TerminologyInfo(BaseModel):
    id: Optional[int] = None
    create_time: Optional[datetime] = None
    word: Optional[str] = None
    description: Optional[str] = None
    other_words: Optional[List[str]] = []
    specific_ds: Optional[bool] = False
    datasource_host: Optional[str] = None
    datasource_port: Optional[int] = None
    enabled: Optional[bool] = True
