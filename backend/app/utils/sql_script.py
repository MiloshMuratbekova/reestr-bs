"""Разбор SQL-скрипта на отдельные операторы.

ClickHouse по HTTP выполняет один оператор за запрос, а скрипт алгоритма
может состоять из нескольких (DROP / CREATE VIEW / CREATE TABLE / DROP TMP).
Делить по «;» наивно нельзя — точка с запятой встречается внутри строковых
литералов и комментариев.
"""

from __future__ import annotations

from typing import List


def split_statements(script: str) -> List[str]:
    """Разбивает скрипт на операторы, уважая строки и комментарии."""
    statements: List[str] = []
    buffer: List[str] = []

    in_single = False
    in_double = False
    in_backtick = False
    in_line_comment = False
    in_block_comment = False

    index = 0
    length = len(script)

    while index < length:
        char = script[index]
        next_char = script[index + 1] if index + 1 < length else ""

        if in_line_comment:
            buffer.append(char)
            if char == "\n":
                in_line_comment = False
            index += 1
            continue

        if in_block_comment:
            buffer.append(char)
            if char == "*" and next_char == "/":
                buffer.append(next_char)
                in_block_comment = False
                index += 2
                continue
            index += 1
            continue

        if in_single:
            buffer.append(char)
            if char == "\\" and next_char:
                buffer.append(next_char)
                index += 2
                continue
            if char == "'":
                in_single = False
            index += 1
            continue

        if in_double:
            buffer.append(char)
            if char == "\\" and next_char:
                buffer.append(next_char)
                index += 2
                continue
            if char == '"':
                in_double = False
            index += 1
            continue

        if in_backtick:
            buffer.append(char)
            if char == "`":
                in_backtick = False
            index += 1
            continue

        # обычный контекст
        if char == "-" and next_char == "-":
            in_line_comment = True
            buffer.append(char)
            index += 1
            continue
        if char == "/" and next_char == "*":
            in_block_comment = True
            buffer.append(char)
            buffer.append(next_char)
            index += 2
            continue
        if char == "'":
            in_single = True
            buffer.append(char)
            index += 1
            continue
        if char == '"':
            in_double = True
            buffer.append(char)
            index += 1
            continue
        if char == "`":
            in_backtick = True
            buffer.append(char)
            index += 1
            continue
        if char == ";":
            statement = "".join(buffer).strip()
            if _is_meaningful(statement):
                statements.append(statement)
            buffer = []
            index += 1
            continue

        buffer.append(char)
        index += 1

    tail = "".join(buffer).strip()
    if _is_meaningful(tail):
        statements.append(tail)

    return statements


def _is_meaningful(statement: str) -> bool:
    """Отсекает пустые фрагменты и куски, состоящие только из комментариев."""
    if not statement.strip():
        return False
    stripped_lines = []
    for line in statement.splitlines():
        line = line.strip()
        if not line or line.startswith("--"):
            continue
        stripped_lines.append(line)
    return bool(stripped_lines)


def describe_statement(statement: str, max_length: int = 90) -> str:
    """Короткое описание оператора для журнала выполнения."""
    compact = " ".join(
        line.strip()
        for line in statement.splitlines()
        if line.strip() and not line.strip().startswith("--")
    )
    if len(compact) <= max_length:
        return compact
    return compact[:max_length].rstrip() + "…"
