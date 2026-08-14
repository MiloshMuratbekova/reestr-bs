"""Управление алгоритмами: загрузка из PostgreSQL, запуск в ClickHouse,
версионирование SQL и полный пересчёт реестра.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.algorithms.definitions import ALGORITHMS, ALGORITHMS_BY_CODE
from app.core.config import settings
from app.core.logging_config import get_logger
from app.db.clickhouse import ClickHouseError, clickhouse, heavy_settings
from app.models import BsAlgorithm, BsAlgorithmHistory
from app.utils.sql_script import describe_statement, split_statements

logger = get_logger("app.algorithms.service")


class AlgorithmNotFound(Exception):
    pass


# ---------------------------------------------------------------------------
# Загрузка начальных данных
# ---------------------------------------------------------------------------
async def seed_algorithms(session: AsyncSession) -> int:
    """Заполняет bs_algorithms начальными данными из каталога.

    Уже существующие записи не трогаются — правки администратора сохраняются.

    Приложение запускается несколькими воркерами uvicorn, и заполнение
    выполняется в каждом из них одновременно. Поэтому нарушение уникальности
    по коду алгоритма — не ошибка, а признак того, что другой воркер успел
    раньше: такая ситуация просто пропускается.
    """
    existing = set(
        (await session.execute(select(BsAlgorithm.code))).scalars().all()
    )
    created = 0

    for definition in ALGORITHMS:
        if definition.code in existing:
            continue
        try:
            sql_script = definition.load_sql()
        except OSError as exc:
            logger.error("Не удалось прочитать SQL алгоритма %s: %s", definition.code, exc)
            continue

        session.add(
            BsAlgorithm(
                code=definition.code,
                name=definition.name,
                description=definition.description,
                sql_script=sql_script,
                clickhouse_result_table=definition.result_table,
                source=definition.source,
                priority_score=definition.priority_score,
                is_active=True,
                version=1,
                depends_on=",".join(definition.depends_on),
                order_index=definition.order_index,
            )
        )
        created += 1

    if not created:
        return 0

    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        logger.info("Каталог алгоритмов заполнен другим процессом приложения")
        return 0

    logger.info("В bs_algorithms добавлено алгоритмов: %d", created)
    return created


# ---------------------------------------------------------------------------
# Чтение
# ---------------------------------------------------------------------------
async def list_algorithms(
    session: AsyncSession, *, only_active: bool = False
) -> List[BsAlgorithm]:
    query = select(BsAlgorithm).order_by(BsAlgorithm.order_index, BsAlgorithm.code)
    if only_active:
        query = query.where(BsAlgorithm.is_active.is_(True))
    return list((await session.execute(query)).scalars().all())


async def get_algorithm(session: AsyncSession, code: str) -> BsAlgorithm:
    algorithm = (
        await session.execute(select(BsAlgorithm).where(BsAlgorithm.code == code))
    ).scalar_one_or_none()
    if algorithm is None:
        raise AlgorithmNotFound(f"Алгоритм {code} не найден")
    return algorithm


async def active_result_tables(session: AsyncSession) -> List[str]:
    """Таблицы результатов активных алгоритмов, реально существующие в ClickHouse.

    Отсутствующая таблица (алгоритм ещё ни разу не запускался) исключается,
    иначе UNION в реестре упадёт целиком.
    """
    algorithms = await list_algorithms(session, only_active=True)
    tables: List[str] = []
    for algorithm in algorithms:
        fqn = algorithm.clickhouse_result_table
        if not fqn or "." not in fqn:
            continue
        database, table = fqn.split(".", 1)
        if await clickhouse.table_exists(database, table):
            tables.append(fqn)
        else:
            logger.warning(
                "Таблица результата %s алгоритма %s отсутствует — исключена из реестра",
                fqn,
                algorithm.code,
            )
    return tables


# ---------------------------------------------------------------------------
# Выполнение
# ---------------------------------------------------------------------------
async def ensure_registry_database() -> None:
    await clickhouse.execute(f"CREATE DATABASE IF NOT EXISTS {settings.REGISTRY_DATABASE}")


async def run_algorithm(
    session: AsyncSession,
    code: str,
    *,
    triggered_by: Optional[str] = None,
) -> Dict[str, Any]:
    """Выполняет SQL алгоритма в ClickHouse.

    Скрипт может состоять из нескольких операторов — они выполняются
    последовательно. Возвращает количество строк в таблице результата.
    """
    algorithm = await get_algorithm(session, code)
    await ensure_registry_database()

    statements = split_statements(algorithm.sql_script)
    if not statements:
        raise ClickHouseError(f"SQL алгоритма {code} пуст")

    logger.info(
        "Запуск алгоритма %s (%d операторов), инициатор: %s",
        code,
        len(statements),
        triggered_by or "система",
    )

    started = time.perf_counter()
    executed: List[Dict[str, Any]] = []

    try:
        for index, statement in enumerate(statements, start=1):
            step_started = time.perf_counter()
            logger.info("  %s шаг %d/%d: %s", code, index, len(statements), describe_statement(statement))
            # Настройки памяти и переливания на диск нужны именно здесь:
            # алгоритмы соединяют сотни млн строк. Остальным запросам системы
            # они не передаются — сервер может их отклонить, и тогда падал бы
            # даже обычный поиск (см. heavy_settings в db/clickhouse.py)
            await clickhouse.execute(statement, query_settings=heavy_settings())
            executed.append(
                {
                    "step": index,
                    "sql": describe_statement(statement),
                    "duration_ms": int((time.perf_counter() - step_started) * 1000),
                }
            )
    except ClickHouseError as exc:
        duration_ms = int((time.perf_counter() - started) * 1000)
        algorithm.last_run_at = datetime.now(timezone.utc)
        algorithm.last_run_status = "failed"
        algorithm.last_error = str(exc)[:4000]
        await session.commit()
        logger.error("Алгоритм %s завершился ошибкой за %d мс: %s", code, duration_ms, exc)
        raise

    duration_ms = int((time.perf_counter() - started) * 1000)
    row_count = await _result_row_count(algorithm.clickhouse_result_table)

    algorithm.last_run_at = datetime.now(timezone.utc)
    algorithm.last_run_status = "success"
    algorithm.last_row_count = row_count
    algorithm.last_error = None
    await session.commit()

    logger.info("Алгоритм %s выполнен за %d мс, строк: %s", code, duration_ms, row_count)
    return {
        "code": code,
        "status": "success",
        "row_count": row_count,
        "duration_ms": duration_ms,
        "steps": executed,
        "result_table": algorithm.clickhouse_result_table,
    }


async def _result_row_count(result_table: str) -> Optional[int]:
    if not result_table or "." not in result_table:
        return None
    database, table = result_table.split(".", 1)
    try:
        if not await clickhouse.table_exists(database, table):
            return None
        return await clickhouse.table_row_count(database, table)
    except ClickHouseError as exc:
        logger.warning("Не удалось получить число строк %s: %s", result_table, exc)
        return None


def order_by_dependencies(algorithms: Sequence[BsAlgorithm]) -> List[BsAlgorithm]:
    """Топологическая сортировка: зависимые алгоритмы считаются после базовых.

    БС-11 читает результаты БС-1 и БС-3, БС-13 — БС-1 и БС-3,
    БС-17 — БС-1, БС-2, БС-22, БС-3 и БС-4.
    """
    by_code = {a.code: a for a in algorithms}
    ordered: List[BsAlgorithm] = []
    visited: Dict[str, str] = {}

    def visit(code: str) -> None:
        state = visited.get(code)
        if state == "done":
            return
        if state == "visiting":
            logger.warning("Обнаружена циклическая зависимость алгоритмов на %s", code)
            return
        algorithm = by_code.get(code)
        if algorithm is None:
            return
        visited[code] = "visiting"
        for dependency in algorithm.depends_on_list:
            if dependency in by_code:
                visit(dependency)
        visited[code] = "done"
        ordered.append(algorithm)

    for algorithm in sorted(algorithms, key=lambda a: (a.order_index, a.code)):
        visit(algorithm.code)
    return ordered


async def recalculate_all(
    session: AsyncSession, *, triggered_by: Optional[str] = None
) -> Dict[str, Any]:
    """Последовательный пересчёт всех активных алгоритмов.

    Ошибка одного алгоритма не останавливает остальные — но алгоритмы,
    зависящие от упавшего, пропускаются, иначе они посчитаются по устаревшим
    или отсутствующим данным.
    """
    algorithms = await list_algorithms(session, only_active=True)
    ordered = order_by_dependencies(algorithms)

    started = time.perf_counter()
    results: List[Dict[str, Any]] = []
    failed: set[str] = set()

    logger.info(
        "Пересчёт реестра: %d алгоритмов, порядок: %s",
        len(ordered),
        ", ".join(a.code for a in ordered),
    )

    for algorithm in ordered:
        blocked = [d for d in algorithm.depends_on_list if d in failed]
        if blocked:
            logger.warning(
                "Алгоритм %s пропущен: не рассчитаны зависимости %s",
                algorithm.code,
                ", ".join(blocked),
            )
            results.append(
                {
                    "code": algorithm.code,
                    "status": "skipped",
                    "error": f"Не рассчитаны зависимости: {', '.join(blocked)}",
                }
            )
            failed.add(algorithm.code)
            continue

        try:
            results.append(await run_algorithm(session, algorithm.code, triggered_by=triggered_by))
        except ClickHouseError as exc:
            failed.add(algorithm.code)
            results.append({"code": algorithm.code, "status": "failed", "error": str(exc)[:2000]})

    duration_ms = int((time.perf_counter() - started) * 1000)
    succeeded = [r for r in results if r.get("status") == "success"]

    logger.info(
        "Пересчёт завершён за %d мс: успешно %d, ошибок %d",
        duration_ms,
        len(succeeded),
        len(results) - len(succeeded),
    )

    return {
        "duration_ms": duration_ms,
        "total": len(results),
        "succeeded": len(succeeded),
        "failed": len(results) - len(succeeded),
        "total_rows": sum(r.get("row_count") or 0 for r in succeeded),
        "results": results,
    }


# ---------------------------------------------------------------------------
# Изменение
# ---------------------------------------------------------------------------
async def create_algorithm(session: AsyncSession, payload: Dict[str, Any]) -> BsAlgorithm:
    algorithm = BsAlgorithm(
        code=payload["code"],
        name=payload["name"],
        description=payload.get("description", ""),
        sql_script=payload["sql_script"],
        clickhouse_result_table=payload.get("clickhouse_result_table", ""),
        source=payload.get("source", ""),
        priority_score=payload.get("priority_score", 0),
        is_active=payload.get("is_active", True),
        version=1,
        depends_on=",".join(payload.get("depends_on", []) or []),
        order_index=payload.get("order_index", 100),
    )
    session.add(algorithm)
    await session.commit()
    await session.refresh(algorithm)
    logger.info("Создан алгоритм %s", algorithm.code)
    return algorithm


async def update_algorithm(
    session: AsyncSession,
    code: str,
    payload: Dict[str, Any],
    *,
    changed_by: Optional[str] = None,
    execute: bool = True,
) -> Dict[str, Any]:
    """Обновляет алгоритм, сохраняет прежний SQL в историю и запускает новый.

    Если новый SQL падает в ClickHouse, изменение остаётся сохранённым
    (администратор увидит ошибку и сможет откатиться на версию из истории),
    но об ошибке сообщается явно.
    """
    algorithm = await get_algorithm(session, code)
    new_sql = payload.get("sql_script")
    sql_changed = new_sql is not None and new_sql.strip() != algorithm.sql_script.strip()

    if sql_changed:
        session.add(
            BsAlgorithmHistory(
                algorithm_id=algorithm.id,
                sql_script=algorithm.sql_script,
                reason=payload.get("reason", "") or "Изменение через интерфейс",
                version=algorithm.version,
                changed_by=changed_by,
            )
        )
        algorithm.sql_script = new_sql
        algorithm.version += 1

    for field in (
        "name",
        "description",
        "clickhouse_result_table",
        "source",
        "priority_score",
        "is_active",
        "order_index",
    ):
        if field in payload and payload[field] is not None:
            setattr(algorithm, field, payload[field])

    if payload.get("depends_on") is not None:
        algorithm.depends_on = ",".join(payload["depends_on"])

    await session.commit()
    await session.refresh(algorithm)
    logger.info("Алгоритм %s обновлён до версии %d", code, algorithm.version)

    run_result: Optional[Dict[str, Any]] = None
    run_error: Optional[str] = None
    if execute and sql_changed and algorithm.is_active:
        try:
            run_result = await run_algorithm(session, code, triggered_by=changed_by)
        except ClickHouseError as exc:
            run_error = str(exc)

    return {"algorithm": algorithm, "run": run_result, "run_error": run_error}


async def rollback_algorithm(
    session: AsyncSession, code: str, history_id: int, *, changed_by: Optional[str] = None
) -> BsAlgorithm:
    """Возврат к сохранённой версии SQL."""
    algorithm = await get_algorithm(session, code)
    entry = (
        await session.execute(
            select(BsAlgorithmHistory).where(
                BsAlgorithmHistory.id == history_id,
                BsAlgorithmHistory.algorithm_id == algorithm.id,
            )
        )
    ).scalar_one_or_none()
    if entry is None:
        raise AlgorithmNotFound(f"Версия {history_id} алгоритма {code} не найдена")

    session.add(
        BsAlgorithmHistory(
            algorithm_id=algorithm.id,
            sql_script=algorithm.sql_script,
            reason=f"Откат на версию из истории #{history_id}",
            version=algorithm.version,
            changed_by=changed_by,
        )
    )
    algorithm.sql_script = entry.sql_script
    algorithm.version += 1
    await session.commit()
    await session.refresh(algorithm)
    return algorithm


async def get_history(session: AsyncSession, code: str) -> List[BsAlgorithmHistory]:
    algorithm = await get_algorithm(session, code)
    result = await session.execute(
        select(BsAlgorithmHistory)
        .where(BsAlgorithmHistory.algorithm_id == algorithm.id)
        .order_by(BsAlgorithmHistory.changed_at.desc())
    )
    return list(result.scalars().all())


def algorithm_hint(code: str) -> str:
    """Расшифровка алгоритма для промптов Qwen."""
    definition = ALGORITHMS_BY_CODE.get(code)
    return definition.ai_hint if definition else ""
