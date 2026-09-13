# Единая точка входа для всех рутинных операций.
# Правило: всё, что ты делаешь чаще двух раз, должно стать целью в Makefile —
# тогда CI на этапе 4 будет вызывать ровно те же команды, что и ты локально.

VENV := .venv
PY := $(VENV)/bin/python
PIP := $(VENV)/bin/pip
COMPOSE := docker compose -f deploy/compose/docker-compose.dev.yml

.DEFAULT_GOAL := help
.PHONY: demo help venv install db-up db-down db-reset db-logs db-shell migrate migration downgrade run lint fmt typecheck test test-cov check clean

help: ## Показать список целей
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

venv: ## Создать виртуальное окружение
	python3 -m venv $(VENV)

install: venv ## Установить зависимости (приложение + dev)
	$(PIP) install --upgrade pip
	$(PIP) install -e ".[dev]"

db-up: ## Поднять Postgres в Docker
	$(COMPOSE) up -d
	@echo "Postgres поднимается, ждём готовности..."
	@until $(COMPOSE) exec -T postgres pg_isready -U finance -d finance >/dev/null 2>&1; do sleep 1; done
	@echo "Postgres готов."

db-down: ## Остановить Postgres (данные сохраняются в volume)
	$(COMPOSE) down

db-reset: ## Снести Postgres вместе с данными
	$(COMPOSE) down -v

db-logs: ## Логи Postgres
	$(COMPOSE) logs -f postgres

db-shell: ## Открыть psql внутри контейнера
	$(COMPOSE) exec postgres psql -U finance -d finance

migrate: ## Применить все миграции
	$(VENV)/bin/alembic upgrade head

migration: ## Создать миграцию: make migration m="add budgets"
	$(VENV)/bin/alembic revision --autogenerate -m "$(m)"

downgrade: ## Откатить последнюю миграцию
	$(VENV)/bin/alembic downgrade -1

demo: ## Наполнить базу демо-данными (demo@local / demo12345)
	$(PY) scripts/seed_demo.py

run: ## Запустить приложение с автоперезагрузкой
	$(VENV)/bin/uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

lint: ## Проверить стиль
	$(VENV)/bin/ruff check app tests
	$(VENV)/bin/ruff format --check app tests

fmt: ## Отформатировать и починить импорты
	$(VENV)/bin/ruff check --fix app tests
	$(VENV)/bin/ruff format app tests

typecheck: ## Проверить типы
	$(VENV)/bin/mypy app

test: ## Прогнать тесты
	$(VENV)/bin/pytest

test-cov: ## Тесты с отчётом покрытия
	$(VENV)/bin/pytest --cov=app --cov-report=term-missing --cov-report=html

check: lint typecheck test ## Полная проверка — то же самое сделает CI

clean: ## Убрать мусор
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage
	find . -type d -name __pycache__ -not -path "./.venv/*" -exec rm -rf {} +
