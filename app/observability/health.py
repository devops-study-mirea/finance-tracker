"""Пробы состояния.

Различие принципиальное, его спрашивают на собеседованиях и оно реально
меняет поведение оркестратора:

  /health (liveness)  — «процесс жив». Провал ⇒ Kubernetes ПЕРЕЗАПУСКАЕТ под.
                        Поэтому сюда нельзя тащить проверку базы: при недоступной
                        БД под начнёт бесконечно перезапускаться, хотя виноват не он.

  /ready  (readiness) — «готов принимать трафик». Провал ⇒ под ВЫВОДИТСЯ
                        из балансировки, но не убивается. Вот сюда проверка базы
                        уместна: без БД обслуживать запросы бессмысленно.
"""

from __future__ import annotations

from fastapi import APIRouter, Response, status

from app.config import settings
from app.db import check_database

router = APIRouter(tags=["health"])


@router.get("/health", summary="Liveness: процесс жив")
def health() -> dict[str, str]:
    return {"status": "ok", "app": settings.app_name, "environment": settings.environment}


@router.get("/ready", summary="Readiness: готов обслуживать трафик")
def ready(response: Response) -> dict[str, object]:
    database_ok = check_database()
    if not database_ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {"status": "ok" if database_ok else "degraded", "checks": {"database": database_ok}}
