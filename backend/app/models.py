# SQLAlchemy 字段类型和 SQL 函数，用于声明 ORM 表结构。
from sqlalchemy import BigInteger, Column, DateTime, Integer, String, func

from app.database import Base


class Video(Base):
    __tablename__ = "videos"

    id = Column(Integer, primary_key=True, index=True)
    video_name = Column(String(255), nullable=False)
    file_path = Column(String(500), nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class MediaResource(Base):
    __tablename__ = "media_resources"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False, index=True)
    category = Column(String(100), nullable=True, index=True)
    media_kind = Column(String(20), nullable=False, index=True)
    media_type = Column(String(100), nullable=False)
    file_name = Column(String(255), nullable=False)
    file_path = Column(String(700), nullable=False)
    source_path = Column(String(700), nullable=True)
    size_bytes = Column(BigInteger, nullable=False)
    sha256 = Column(String(64), nullable=False, index=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class CalligraphyGlyph(Base):
    __tablename__ = "calligraphy_glyphs"

    id = Column(Integer, primary_key=True, index=True)
    character = Column(String(16), nullable=False, index=True)
    style = Column(String(64), nullable=False, index=True)
    author = Column(String(64), nullable=False, index=True)
    image_path = Column(String(700), nullable=False)
    width = Column(Integer, nullable=True)
    height = Column(Integer, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
