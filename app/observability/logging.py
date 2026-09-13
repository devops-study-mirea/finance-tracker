"""Настройка логирования.

Пока — обычный текстовый формат, читаемый глазами в терминале.
На этапе 5 здесь появится структурированный JSON: агрегаторы вроде Loki
или Elasticsearch умеют фильтровать по полям, а не по регулярке над строкой.
"""

from __future__ import annotations

import logging
import sys

from app.config import settings

LOG_FORMAT = "%(asctime)s %(levelname)-8s %(name)s: %(message)s"


def configure_logging() -> None:
    logging.basicConfig(
        level=getattr(logging, settings.log_level, logging.INFO),
        format=LOG_FORMAT,
        stream=sys.stdout,  # в контейнере логи идут в stdout, а не в файл
        force=True,
    )
    # SQLAlchemy на INFO печатает каждый SQL-запрос — шумно.
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
