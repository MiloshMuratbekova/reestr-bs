"""Каталог источников данных реестра БС.

Перечень источников и таблиц взят из ТЗ и сверен с SQL алгоритмов —
здесь только те таблицы, которые действительно читаются в
:mod:`app.algorithms.sql`. Ничего не досочинено: если по источнику
алгоритма в ТЗ нет, у него пустой список алгоритмов и об этом сказано
в примечании.

Количество записей и дата обновления не хранятся — они запрашиваются
у ClickHouse из ``system.tables`` при открытии страницы.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass(frozen=True)
class DataSource:
    #: Короткий ключ источника, он же значение поля ``source`` алгоритма
    key: str
    #: Название источника, как в ТЗ
    name: str
    #: Организация — поставщик данных
    organization: str
    #: Таблицы ClickHouse, из которых читают алгоритмы
    tables: List[str]
    #: Коды алгоритмов, использующих источник
    algorithms: List[str]
    #: Примечание для интерфейса
    note: str = ""
    #: Вспомогательные таблицы (справочники, связи) — показываются отдельно
    extra_tables: List[str] = field(default_factory=list)


SOURCES: List[DataSource] = [
    DataSource(
        key="МЮ_бс",
        name="Реестр бенефициарных собственников МЮ",
        organization="Министерство юстиции РК",
        tables=["AFM_2_10_TEST.AFM_2_10_2"],
        algorithms=["БС-1"],
        note="Официальный реестр, в котором компании сами декларируют бенефициаров.",
    ),
    DataSource(
        key="МФЦА",
        name="МФЦА — акционеры",
        organization="Международный финансовый центр «Астана»",
        tables=["AFM_2_11.AFM_2_11_2"],
        algorithms=["БС-2"],
        note="Акционеры компаний, зарегистрированных в МФЦА.",
    ),
    DataSource(
        key="МЮ_учредители",
        name="Учредители юридических лиц МЮ",
        organization="Министерство юстиции РК",
        tables=["AFM_2_1_TEST.AFM_2_1_5_1"],
        algorithms=["БС-3", "БС-4"],
        note="Доли учредителей. БС-3 — корректная сумма долей, БС-4 — признак некорректности 3.",
        extra_tables=["AFM_2_1.AFM_2_1_8"],
    ),
    DataSource(
        key="ПО",
        name="Правоохранительные органы (websfm.kz)",
        organization="КНБ, МВД, Прокуратура, ДЭР, Антикоррупционная служба, АФМ",
        tables=["pfr_dashboard.bvu_beneficiary_info"],
        algorithms=["БС-6"],
        note="Сведения, поступившие через систему websfm.kz.",
    ),
    DataSource(
        key="ДЦБ",
        name="Депозитарий ценных бумаг",
        organization="АО «Центральный депозитарий ценных бумаг»",
        tables=["AFM_2_12.AFM_2_12_1"],
        algorithms=["БС-7"],
        note="Акционеры публичных компаний с долей более 10 процентов.",
    ),
    DataSource(
        key="СФМ_ФМ1",
        name="Финансовый мониторинг (ФМ-1)",
        organization="Субъекты финансового мониторинга",
        tables=["pfr_dashboard.asloy", "pfr_dashboard.asloy_dopinfo"],
        algorithms=["БС-8", "БС-9", "БС-10", "БС-11"],
        note="Операции за последние 6 календарных месяцев: переводы, помощь, дивиденды.",
        extra_tables=["AFM_2_1.AFM_2_1_19"],
    ),
    DataSource(
        key="ЭСФ_связи",
        name="Электронные счета-фактуры и связи",
        organization="КГД МФ РК, АФМ",
        tables=["AFM_2_1.esf_2025", "AFM_2_1.esf_2026"],
        algorithms=["БС-13"],
        note=(
            "Самый объёмный источник: расчёт идёт через промежуточные таблицы, "
            "которые удаляются по завершении."
        ),
        extra_tables=["pfr_dashboard.svz_overroll_table", "AFM_2_1.AFM_2_1_19"],
    ),
    DataSource(
        key="Ответ_ЮЛ",
        name="Ответы ЮЛ на запросы АФМ",
        organization="Агентство по финансовому мониторингу РК",
        tables=["AFM_2_6.AFM_2_6_9"],
        algorithms=["БС-16"],
        note="Дата актуальности — дата получения ответа от юридического лица.",
    ),
    DataSource(
        key="Заявление КИК",
        name="Заявления о контролируемых иностранных компаниях",
        organization="КГД МФ РК",
        tables=[
            "AFM_2_1.AFM_2_1_45_1",
            "AFM_2_1.AFM_2_1_45_2",
            "AFM_2_1.AFM_2_1_45_3",
        ],
        algorithms=["БС-17"],
        note=(
            "Если заявление подано ЮЛ, конечный бенефициар устанавливается "
            "в порядке БС-1, БС-2, БС-22, БС-3, БС-4."
        ),
    ),
    DataSource(
        key="КГД_нерезидент",
        name="Налоговые заявления о регистрации ЮЛ-нерезидентов",
        organization="КГД МФ РК",
        tables=["AFM_2_1.AFM_2_1_kgd_nonresident"],
        algorithms=["БС-22"],
        note="Бенефициары иностранных юридических лиц, состоящих на учёте в РК.",
    ),
    DataSource(
        key="МИИР",
        name="МИИР — недропользователи",
        organization="Министерство индустрии и инфраструктурного развития РК",
        tables=[],
        algorithms=[],
        note=(
            "Источник указан в перечне, но алгоритм выявления по нему в ТЗ "
            "не описан — данные в расчёте реестра не участвуют."
        ),
    ),
]

SOURCES_BY_KEY: Dict[str, DataSource] = {s.key: s for s in SOURCES}


def all_tables() -> List[str]:
    """Полный перечень таблиц источников — для одного запроса к system.tables."""
    tables: List[str] = []
    for source in SOURCES:
        for table in list(source.tables) + list(source.extra_tables):
            if table not in tables:
                tables.append(table)
    return tables
