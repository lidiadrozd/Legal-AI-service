"""CRUD операции"""
from . import user, chat
from app.db.base_class import CRUDBase

__all__ = ["user", "chat", "CRUDBase"]
