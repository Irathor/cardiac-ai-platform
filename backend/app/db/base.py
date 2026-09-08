"""Declarative base shared by every ORM model in the platform."""
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
