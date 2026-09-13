"""Веб-интерфейс поверх той же бизнес-логики, что и API.

Мутации сделаны по схеме POST → Redirect → GET: после отправки формы браузер
получает 303 и делает GET. Без этого F5 на странице результата повторяет
отправку, и в базе появляются дубли операций.

Аутентификация — тот же JWT, что и в API, но в httpOnly-куке: формам неоткуда
взять заголовок Authorization, а httpOnly защищает токен от кражи через XSS.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Form, Request, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError

from app.api.dependencies import COOKIE_NAME, DbSession, OptionalUser
from app.config import settings
from app.models import Account, CategoryKind, TransactionKind, User
from app.palette import PALETTE
from app.schemas.account import AccountCreate
from app.schemas.budget import BudgetCreate
from app.schemas.category import CategoryCreate
from app.schemas.transaction import TransactionCreate
from app.security import create_access_token
from app.services import accounts, analytics, budgets, categories, transactions, users
from app.services.errors import AuthError, DomainError
from app.services.transactions import TransactionFilters

TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

router = APIRouter(include_in_schema=False)

PAGE_SIZE = 25

# Неразрывный пробел: «1 500 ₽» не должно разрываться переносом строки.
NBSP = "\u00a0"

CURRENCY_SYMBOLS = {
    "RUB": "₽",
    "USD": "$",
    "EUR": "€",
    "GBP": "£",
    "KZT": "₸",
    "UAH": "₴",
    "BYN": "Br",
    "TRY": "₺",
}

MONTHS_GENITIVE = (
    "января",
    "февраля",
    "марта",
    "апреля",
    "мая",
    "июня",
    "июля",
    "августа",
    "сентября",
    "октября",
    "ноября",
    "декабря",
)
MONTHS_NOMINATIVE = (
    "Январь",
    "Февраль",
    "Март",
    "Апрель",
    "Май",
    "Июнь",
    "Июль",
    "Август",
    "Сентябрь",
    "Октябрь",
    "Ноябрь",
    "Декабрь",
)

KIND_LABELS = {"income": "Доход", "expense": "Расход", "transfer": "Перевод"}
ACCOUNT_KIND_LABELS = {
    "cash": "Наличные",
    "card": "Карта",
    "savings": "Накопительный",
    "credit": "Кредитный",
}


# ----------------------------------------------------------------- фильтры Jinja
def format_money(value: Decimal | int | float | None, currency: str | None = None) -> str:
    """1234.5 → «1 234,50 ₽».

    Разделители — неразрывные пробелы (\u00a0), заданные явной константой:
    невидимый символ прямо в исходнике невозможно ни увидеть при ревью,
    ни надёжно повторить в тесте.
    """
    amount = Decimal(value or 0).quantize(Decimal("0.01"))
    sign = "\u2212" if amount < 0 else ""  # настоящий минус, а не дефис
    whole, _, fraction = f"{abs(amount):.2f}".partition(".")
    groups = [whole[max(index - 3, 0) : index] for index in range(len(whole), 0, -3)][::-1]
    grouped = NBSP.join(groups)
    code = (currency or settings.default_currency).upper()
    return f"{sign}{grouped},{fraction}{NBSP}{CURRENCY_SYMBOLS.get(code, code)}"


def format_date(value: date | None) -> str:
    return value.strftime("%d.%m.%Y") if value else ""


def format_day_month(value: date | None) -> str:
    return f"{value.day} {MONTHS_GENITIVE[value.month - 1]}" if value else ""


def format_month(value: date | None) -> str:
    return f"{MONTHS_NOMINATIVE[value.month - 1]} {value.year}" if value else ""


def format_short_month(value: date | None) -> str:
    return (
        f"{MONTHS_NOMINATIVE[value.month - 1][:3].lower()} {str(value.year)[2:]}" if value else ""
    )


def plural(count: int, one: str, few: str, many: str) -> str:
    """Русское склонение: 1 счёт, 2 счёта, 5 счетов.

    «2 активных счетов» в интерфейсе выглядит как недоделка, хотя работает
    приложение при этом идеально. Правило простое и стоит двадцати строк.
    """
    remainder = abs(count) % 100
    if 11 <= remainder <= 14:
        return many
    remainder %= 10
    if remainder == 1:
        return one
    if 2 <= remainder <= 4:
        return few
    return many


templates.env.filters["money"] = format_money
templates.env.filters["plural"] = plural
templates.env.filters["rudate"] = format_date
templates.env.filters["daymonth"] = format_day_month
templates.env.filters["rumonth"] = format_month
templates.env.filters["shortmonth"] = format_short_month


# ----------------------------------------------------------------- утилиты
def see_other(path: str, *, ok: str | None = None, error: str | None = None) -> RedirectResponse:
    if ok:
        path += ("&" if "?" in path else "?") + "ok=" + quote(ok)
    if error:
        path += ("&" if "?" in path else "?") + "error=" + quote(error)
    return RedirectResponse(path, status_code=status.HTTP_303_SEE_OTHER)


def run_action(action: Callable[[], Any], *, back: str, ok: str) -> RedirectResponse:
    """Выполнить действие и вернуться назад с сообщением.

    Ошибки бизнес-логики и валидации показываются пользователю на той же
    странице обычным текстом — а не страницей 422, из которой непонятно,
    что именно он ввёл не так.
    """
    try:
        action()
    except DomainError as exc:
        return see_other(back, error=exc.message)
    except ValidationError as exc:
        messages = "; ".join(error["msg"].removeprefix("Value error, ") for error in exc.errors())
        return see_other(back, error=messages)
    return see_other(back, ok=ok)


def _int(raw: str | None) -> int | None:
    if raw is None or not raw.strip():
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _date(raw: str | None) -> date | None:
    if raw is None or not raw.strip():
        return None
    try:
        return date.fromisoformat(raw.strip())
    except ValueError:
        return None


def _decimal(raw: str) -> Decimal:
    """Принимает и «1234.50», и «1 234,50» — люди пишут запятую."""
    cleaned = raw.strip().replace(" ", "").replace(" ", "").replace(" ", "")
    cleaned = cleaned.replace(",", ".")
    try:
        return Decimal(cleaned)
    except InvalidOperation as exc:
        raise DomainError(f"«{raw}» не похоже на сумму") from exc


def hx_or_redirect(request: Request, path: str, *, ok: str | None = None) -> Response:
    """Ответ на действие: HTMX получает заголовок редиректа, обычная форма — 303."""
    target = path
    if ok:
        target += ("&" if "?" in target else "?") + "ok=" + quote(ok)
    if request.headers.get("HX-Request"):
        return Response(status_code=status.HTTP_204_NO_CONTENT, headers={"HX-Redirect": target})
    return see_other(target)


def render(
    request: Request, template: str, user: User | None, context: dict[str, Any]
) -> HTMLResponse:
    base: dict[str, Any] = {
        "request": request,
        "user": user,
        "ok": request.query_params.get("ok"),
        "error": request.query_params.get("error"),
        "path": request.url.path,
        "palette": PALETTE,
        "kind_labels": KIND_LABELS,
        "account_kind_labels": ACCOUNT_KIND_LABELS,
        "today": analytics.today(),
        "currency": settings.default_currency,
    }
    base.update(context)
    return templates.TemplateResponse(request, template, base)


def require(user: User | None) -> User:
    if user is None:
        raise AuthError("Требуется вход")
    return user


def _account_currency(account_list: list[Account]) -> str:
    return account_list[0].currency if account_list else settings.default_currency


# ----------------------------------------------------------------- вход и регистрация
@router.get("/login")
def login_page(request: Request, user: OptionalUser) -> Response:
    if user is not None:
        return see_other("/")
    return render(request, "login.html", None, {"next": request.query_params.get("next", "/")})


@router.post("/login")
def login_submit(
    request: Request,
    session: DbSession,
    email: str = Form(...),
    password: str = Form(...),
    next: str = Form("/"),
) -> Response:
    try:
        account_user = users.authenticate(session, email, password)
    except DomainError as exc:
        return render(
            request, "login.html", None, {"next": next, "error": exc.message, "email": email}
        )
    return _login_response(account_user.id, next)


@router.get("/register")
def register_page(request: Request, user: OptionalUser) -> Response:
    if user is not None:
        return see_other("/")
    return render(request, "register.html", None, {})


@router.post("/register")
def register_submit(
    request: Request,
    session: DbSession,
    email: str = Form(...),
    password: str = Form(...),
) -> Response:
    if len(password) < 8:
        return render(
            request,
            "register.html",
            None,
            {"error": "Пароль должен быть не короче 8 символов", "email": email},
        )
    try:
        new_user = users.register(session, email, password)
    except DomainError as exc:
        return render(request, "register.html", None, {"error": exc.message, "email": email})
    return _login_response(new_user.id, "/")


def _login_response(user_id: int, next_path: str) -> RedirectResponse:
    # Внешние адреса в next не пускаем: иначе ссылка вида
    # /login?next=https://evil.example уводит пользователя после входа на чужой сайт.
    target = next_path if next_path.startswith("/") and not next_path.startswith("//") else "/"
    response = RedirectResponse(target, status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(
        COOKIE_NAME,
        create_access_token(user_id),
        max_age=settings.jwt_expire_minutes * 60,
        httponly=True,
        samesite="lax",
        secure=not settings.is_local,
        path="/",
    )
    return response


@router.get("/logout")
def logout() -> Response:
    response = see_other("/login")
    response.delete_cookie(COOKIE_NAME, path="/")
    return response


# ----------------------------------------------------------------- дашборд
@router.get("/")
def dashboard(request: Request, session: DbSession, user: OptionalUser) -> Response:
    current = require(user)
    period_start, period_end = analytics.month_bounds(analytics.today())

    account_list = list(accounts.list_accounts(session, current.id))
    balances = accounts.compute_balances(session, current.id)
    recent, _ = transactions.list_transactions(session, current.id, TransactionFilters(), limit=8)

    return render(
        request,
        "dashboard.html",
        current,
        {
            "summary": analytics.period_summary(session, current.id, period_start, period_end),
            "accounts": account_list,
            "balances": balances,
            "total_balance": accounts.total_balance(
                {a.id: balances.get(a.id, Decimal("0")) for a in account_list}
            ),
            "breakdown": analytics.category_breakdown(
                session, current.id, CategoryKind.expense, period_start, period_end
            ),
            "budget_status": analytics.budget_status(session, current.id),
            "recent": recent,
            "period_start": period_start,
            "currency": _account_currency(account_list),
        },
    )


# ----------------------------------------------------------------- операции
@router.get("/transactions")
def transactions_page(request: Request, session: DbSession, user: OptionalUser) -> Response:
    current = require(user)
    params = request.query_params

    kind_raw = params.get("kind")
    filters = TransactionFilters(
        date_from=_date(params.get("date_from")),
        date_to=_date(params.get("date_to")),
        account_id=_int(params.get("account_id")),
        category_id=_int(params.get("category_id")),
        kind=(
            TransactionKind(kind_raw)
            if kind_raw is not None and kind_raw in TransactionKind.__members__
            else None
        ),
        search=params.get("search") or None,
    )
    page = max(1, _int(params.get("page")) or 1)
    items, total = transactions.list_transactions(
        session, current.id, filters, limit=PAGE_SIZE, offset=(page - 1) * PAGE_SIZE
    )

    account_list = list(accounts.list_accounts(session, current.id))
    return render(
        request,
        "transactions.html",
        current,
        {
            "items": items,
            "total": total,
            "page": page,
            "pages": max(1, -(-total // PAGE_SIZE)),
            "filters": filters,
            "accounts": account_list,
            "categories": list(categories.list_categories(session, current.id)),
            "query": {key: value for key, value in params.items() if key != "page"},
            "currency": _account_currency(account_list),
        },
    )


@router.post("/transactions")
def transactions_create(
    session: DbSession,
    user: OptionalUser,
    kind: str = Form(...),
    amount: str = Form(...),
    account_id: int = Form(...),
    counter_account_id: str = Form(""),
    category_id: str = Form(""),
    occurred_on: str = Form(...),
    note: str = Form(""),
) -> Response:
    current = require(user)

    def create() -> None:
        data = TransactionCreate(
            kind=TransactionKind(kind),
            amount=_decimal(amount),
            account_id=account_id,
            counter_account_id=_int(counter_account_id),
            category_id=_int(category_id),
            occurred_on=_date(occurred_on) or analytics.today(),
            note=note.strip() or None,
        )
        transactions.create_transaction(session, current.id, data)

    return run_action(create, back="/transactions", ok="Операция добавлена")


@router.post("/transactions/{transaction_id}/delete")
def transactions_delete(
    request: Request, transaction_id: int, session: DbSession, user: OptionalUser
) -> Response:
    current = require(user)
    transactions.delete_transaction(session, current.id, transaction_id)
    return hx_or_redirect(request, "/transactions", ok="Операция удалена")


# ----------------------------------------------------------------- счета
@router.get("/accounts")
def accounts_page(request: Request, session: DbSession, user: OptionalUser) -> Response:
    current = require(user)
    account_list = list(accounts.list_accounts(session, current.id, include_archived=True))
    balances = accounts.compute_balances(session, current.id)
    return render(
        request,
        "accounts.html",
        current,
        {
            "accounts": account_list,
            "balances": balances,
            "total_balance": accounts.total_balance(
                {a.id: balances.get(a.id, Decimal("0")) for a in account_list if not a.is_archived}
            ),
            "currency": _account_currency(account_list),
        },
    )


@router.post("/accounts")
def accounts_create(
    session: DbSession,
    user: OptionalUser,
    name: str = Form(...),
    kind: str = Form("card"),
    currency: str = Form(...),
    initial_balance: str = Form("0"),
) -> Response:
    current = require(user)

    def create() -> None:
        accounts.create_account(
            session,
            current.id,
            AccountCreate(
                name=name,
                kind=kind,
                currency=currency,
                initial_balance=_decimal(initial_balance or "0"),
            ),
        )

    return run_action(create, back="/accounts", ok="Счёт создан")


@router.post("/accounts/{account_id}/archive")
def accounts_archive(
    request: Request,
    account_id: int,
    session: DbSession,
    user: OptionalUser,
    archived: str = Form("true"),
) -> Response:
    current = require(user)
    from app.schemas.account import AccountUpdate

    accounts.update_account(
        session, current.id, account_id, AccountUpdate(is_archived=archived == "true")
    )
    return hx_or_redirect(request, "/accounts", ok="Счёт обновлён")


@router.post("/accounts/{account_id}/delete")
def accounts_delete(account_id: int, session: DbSession, user: OptionalUser) -> Response:
    current = require(user)
    return run_action(
        lambda: accounts.delete_account(session, current.id, account_id),
        back="/accounts",
        ok="Счёт удалён",
    )


# ----------------------------------------------------------------- категории
@router.get("/categories")
def categories_page(request: Request, session: DbSession, user: OptionalUser) -> Response:
    current = require(user)
    all_categories = list(categories.list_categories(session, current.id, include_archived=True))
    return render(
        request,
        "categories.html",
        current,
        {
            "expense_categories": [c for c in all_categories if c.kind is CategoryKind.expense],
            "income_categories": [c for c in all_categories if c.kind is CategoryKind.income],
        },
    )


@router.post("/categories")
def categories_create(
    session: DbSession,
    user: OptionalUser,
    name: str = Form(...),
    kind: str = Form(...),
    color_slot: int = Form(0),
) -> Response:
    current = require(user)
    return run_action(
        lambda: categories.create_category(
            session,
            current.id,
            CategoryCreate(name=name, kind=CategoryKind(kind), color_slot=color_slot),
        ),
        back="/categories",
        ok="Категория создана",
    )


@router.post("/categories/{category_id}/delete")
def categories_delete(
    request: Request, category_id: int, session: DbSession, user: OptionalUser
) -> Response:
    current = require(user)
    categories.delete_category(session, current.id, category_id)
    return hx_or_redirect(request, "/categories", ok="Категория удалена")


# ----------------------------------------------------------------- бюджеты
@router.get("/budgets")
def budgets_page(request: Request, session: DbSession, user: OptionalUser) -> Response:
    current = require(user)
    status_data = analytics.budget_status(session, current.id)
    used_categories = {item.category_id for item in status_data.items}
    return render(
        request,
        "budgets.html",
        current,
        {
            "status": status_data,
            "budgets": list(budgets.list_budgets(session, current.id)),
            "available_categories": [
                category
                for category in categories.list_categories(
                    session, current.id, kind=CategoryKind.expense
                )
                if category.id not in used_categories
            ],
        },
    )


@router.post("/budgets")
def budgets_create(
    session: DbSession,
    user: OptionalUser,
    category_id: int = Form(...),
    limit_amount: str = Form(...),
) -> Response:
    current = require(user)
    return run_action(
        lambda: budgets.create_budget(
            session,
            current.id,
            BudgetCreate(category_id=category_id, limit_amount=_decimal(limit_amount)),
        ),
        back="/budgets",
        ok="Лимит установлен",
    )


@router.post("/budgets/{budget_id}/delete")
def budgets_delete(
    request: Request, budget_id: int, session: DbSession, user: OptionalUser
) -> Response:
    current = require(user)
    budgets.delete_budget(session, current.id, budget_id)
    return hx_or_redirect(request, "/budgets", ok="Лимит снят")


# ----------------------------------------------------------------- отчёты
@router.get("/reports")
def reports_page(request: Request, session: DbSession, user: OptionalUser) -> Response:
    current = require(user)
    params = request.query_params

    default_start, default_end = analytics.month_bounds(analytics.today())
    date_from = _date(params.get("date_from")) or default_start.replace(month=1, day=1)
    date_to = _date(params.get("date_to")) or default_end
    granularity = params.get("granularity", "month")
    if granularity not in analytics.GRANULARITIES:
        granularity = "month"

    account_list = list(accounts.list_accounts(session, current.id))
    summary = analytics.period_summary(session, current.id, date_from, date_to)
    timeline_data = analytics.timeline(session, current.id, date_from, date_to, granularity)

    # Обе серии графика делят одну шкалу, поэтому пик считается по обеим сразу.
    # Две независимые шкалы визуально «уравняли» бы доходы и расходы,
    # даже если они отличаются в разы.
    peak = max(
        (value for point in timeline_data.points for value in (point.income, point.expense)),
        default=Decimal("0"),
    )

    return render(
        request,
        "reports.html",
        current,
        {
            "summary": summary,
            "expenses": analytics.category_breakdown(
                session, current.id, CategoryKind.expense, date_from, date_to
            ),
            "incomes": analytics.category_breakdown(
                session, current.id, CategoryKind.income, date_from, date_to
            ),
            "timeline": timeline_data,
            "timeline_peak": peak,
            "savings_rate": (
                round(float(summary.net / summary.income) * 100, 1) if summary.income > 0 else 0.0
            ),
            "date_from": date_from,
            "date_to": date_to,
            "granularity": granularity,
            "currency": _account_currency(account_list),
        },
    )
