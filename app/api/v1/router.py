"""Сборка всех роутеров версии v1.

Версия зашита в префикс осознанно: когда контракт придётся ломать, появится
/api/v2, а старые клиенты продолжат работать на /api/v1 до миграции.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import accounts, analytics, auth, budgets, categories, transactions

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(accounts.router)
api_router.include_router(categories.router)
api_router.include_router(transactions.router)
api_router.include_router(budgets.router)
api_router.include_router(analytics.router)
