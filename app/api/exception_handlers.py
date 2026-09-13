"""Перевод ошибок предметной области в HTTP-ответы.

Один раз описанное здесь соответствие избавляет каждый роутер от
`raise HTTPException(...)`: сервисы бросают осмысленное доменное исключение,
а как оно выглядит по HTTP — решает этот модуль.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request, status
from fastapi.responses import HTMLResponse, JSONResponse, Response

from app.services.errors import (
    AuthError,
    BusinessRuleError,
    ConflictError,
    DomainError,
    NotFoundError,
)

logger = logging.getLogger(__name__)

STATUS_BY_ERROR: dict[type[DomainError], int] = {
    NotFoundError: status.HTTP_404_NOT_FOUND,
    ConflictError: status.HTTP_409_CONFLICT,
    BusinessRuleError: 422,  # Unprocessable Content: запрос понят, но правилами запрещён
    AuthError: status.HTTP_401_UNAUTHORIZED,
}

ERROR_PAGE = """<!doctype html>
<html lang="ru"><head><meta charset="utf-8">
<title>{code} — Финансы</title>
<style>
body{{font:16px/1.6 system-ui,-apple-system,"Segoe UI",sans-serif;background:#f9f9f7;
color:#0b0b0b;display:grid;place-items:center;min-height:100vh;margin:0;padding:24px}}
.box{{background:#fcfcfb;border:1px solid rgba(11,11,11,.1);border-radius:12px;
padding:32px;max-width:520px}}
h1{{margin:0 0 8px;font-size:20px}}
p{{margin:0 0 20px;color:#52514e}}
a{{color:#2a78d6}}
@media (prefers-color-scheme:dark){{body{{background:#0d0d0d;color:#fff}}
.box{{background:#1a1a19;border-color:rgba(255,255,255,.1)}}p{{color:#c3c2b7}}}}
</style></head>
<body><div class="box"><h1>{code}</h1><p>{message}</p>
<a href="/">Вернуться на главную</a></div></body></html>
"""


def _wants_html(request: Request) -> bool:
    return not request.url.path.startswith("/api")


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def handle_domain_error(request: Request, exc: DomainError) -> Response:
        code = STATUS_BY_ERROR.get(type(exc), status.HTTP_400_BAD_REQUEST)

        if _wants_html(request):
            # Неаутентифицированного посетителя веб-интерфейса отправляем
            # логиниться, а не показываем ему голый 401.
            if isinstance(exc, AuthError):
                return Response(
                    status_code=status.HTTP_303_SEE_OTHER,
                    headers={"Location": f"/login?next={request.url.path}"},
                )
            return HTMLResponse(ERROR_PAGE.format(code=code, message=exc.message), status_code=code)

        headers = {"WWW-Authenticate": "Bearer"} if isinstance(exc, AuthError) else None
        return JSONResponse({"detail": exc.message}, status_code=code, headers=headers)

    @app.exception_handler(Exception)
    async def handle_unexpected(request: Request, exc: Exception) -> Response:
        # Наружу — обезличенное сообщение: текст исключения может содержать
        # фрагменты SQL, пути и прочее, чего клиенту знать не нужно.
        # Подробности уходят в лог с трассировкой.
        logger.exception("Необработанная ошибка на %s %s", request.method, request.url.path)
        if _wants_html(request):
            return HTMLResponse(
                ERROR_PAGE.format(code=500, message="Внутренняя ошибка сервера"),
                status_code=500,
            )
        return JSONResponse({"detail": "Внутренняя ошибка сервера"}, status_code=500)
