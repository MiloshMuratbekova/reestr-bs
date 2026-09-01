"""Каталог источников данных реестра БС.

Перечень источников и таблиц сверен с SQL алгоритмов — здесь только те
таблицы, которые действительно читаются в :mod:`app.algorithms.sql`.
Ключ источника совпадает с полем ``source`` алгоритма.

Количество записей и дата обновления не хранятся: они запрашиваются
у ClickHouse из ``system.tables`` при открытии страницы.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass(frozen=True)
class DataSource:
    #: Ключ источника, он же значение поля ``source`` алгоритма
    key: str
    #: Название источника
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


#: Справочники, которые подтягиваются почти каждым алгоритмом. Чтобы не
#: повторять их в каждом источнике, они вынесены сюда и показываются отдельной
#: карточкой.
COMMON_TABLES = [
    "AFM_2_1_TEST.AFM_2_1_5_1",
    "AFM_2_1_TEST.AFM_2_1_6_1",
    "AFM_2_1_TEST.AFM_2_1_9",
    "AFM_2_1_TEST.AFM_2_1_10",
    "AFM_2_1.AFM_2_1_8",
    "AFM_2_1.AFM_2_1_19",
    "AFM_2_1.AFM_2_1_59",
    "AFM_6_TEST.AFM_6_1_5_1",
]


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
        key="МЮ_учредители",
        name="Учредители юридических лиц МЮ",
        organization="Министерство юстиции РК",
        tables=["AFM_2_1_TEST.AFM_2_1_5_1"],
        algorithms=["БС-3", "БС-4", "БС-5"],
        note=(
            "Доли учредителей. БС-3 — корректная сумма долей, БС-4 — признак "
            "некорректности 3, БС-5 — косвенное владение через цепочку ЮЛ."
        ),
        extra_tables=["AFM_2_1.AFM_2_1_8"],
    ),
    DataSource(
        key="МЮ_директор",
        name="Руководители юридических лиц МЮ",
        organization="Министерство юстиции РК",
        tables=["AFM_2_1_TEST.AFM_2_1_6_1"],
        algorithms=["БС-24"],
        note=(
            "Замыкающий признак: применяется только к компаниям, по которым "
            "не сработал ни один другой алгоритм."
        ),
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
        key="ПО",
        name="Правоохранительные органы (websfm.kz)",
        organization="КНБ, МВД, прокуратура, ДЭР, антикоррупционная служба, АФМ",
        tables=["pfr_dashboard.bvu_beneficiary_info"],
        algorithms=["БС-6"],
        note="Записи той же системы от прочих поставщиков разбирает БС-18.",
    ),
    DataSource(
        key="СФМ",
        name="Субъекты финансового мониторинга",
        organization="Банки второго уровня и прочие субъекты финмониторинга",
        tables=[
            "pfr_dashboard.bvu_beneficiary_info",
            "pfr_dashboard.bvu_organization_info",
        ],
        algorithms=["БС-18"],
        note="Обратная сторона БС-6: все поставщики, кроме правоохранительных органов.",
    ),
    DataSource(
        key="ДЦБ",
        name="Депозитарий ценных бумаг",
        organization="АО «Центральный депозитарий ценных бумаг»",
        tables=["AFM_2_1_TEST.AFM_2_1_dcb"],
        algorithms=["БС-7"],
        note="Акционеры-физические лица.",
    ),
    DataSource(
        key="СФМ_ФМ1",
        name="Финансовый мониторинг (ФМ-1)",
        organization="Субъекты финансового мониторинга",
        tables=["pfr_dashboard.asloy", "pfr_dashboard.asloy_dopinfo"],
        algorithms=["БС-8", "БС-9", "БС-10", "БС-11", "БС-12"],
        note=(
            "Операции за последние 6 календарных месяцев: крупные переводы, "
            "действия от имени ЮЛ, финансовая помощь, дивиденды, выгодоприобретатели."
        ),
        extra_tables=["AFM_2_1.AFM_2_1_19"],
    ),
    DataSource(
        key="ЭСФ_связи",
        name="Электронные счета-фактуры и родственные связи",
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
        key="Прочие ведомства",
        name="Сведения государственных органов",
        organization="Государственные органы, кроме правоохранительных",
        tables=["AFM_2_6.AFM_2_6_7"],
        algorithms=["БС-15"],
        note="Ведомство-поставщик берётся из самих данных, а не задаётся константой.",
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
            "Если заявление подано юридическим лицом, конечный бенефициар "
            "устанавливается по регистрационным алгоритмам с учётом данных КГД "
            "по нерезидентам."
        ),
    ),
    DataSource(
        key="Ответ_ЮЛ",
        name="Ответы ЮЛ на запросы АФМ",
        organization="Агентство по финансовому мониторингу РК",
        tables=["AFM_2_6.AFM_2_6_9"],
        algorithms=["БС-16"],
        note="Компания сама называет своего бенефициара в ответ на запрос.",
    ),
    DataSource(
        key="КГД_нерезидент",
        name="Налоговые заявления о регистрации ЮЛ-нерезидентов",
        organization="КГД МФ РК",
        tables=["AFM_2_1_TEST.AFM_2_1_kgd_nonresident"],
        algorithms=["БС-22"],
        note="Бенефициары иностранных юридических лиц, состоящих на учёте в РК.",
    ),
    DataSource(
        key="ФНО_026",
        name="Форма налоговой отчётности 026",
        organization="КГД МФ РК",
        tables=["AFM_2_1_TEST.AFM_2_1_form026"],
        algorithms=["БС-23"],
    ),
    DataSource(
        key="МИИР_МЭ",
        name="Недропользователи",
        organization="МИИР РК, Министерство энергетики РК",
        tables=["AFM_2_13.AFM_2_13_me"],
        algorithms=["БС-19"],
        note="Гражданство и доля часто записаны одной строкой вместе с ФИО.",
    ),
    DataSource(
        key="МФ_госзакупки",
        name="Государственные закупки",
        organization="Министерство финансов РК",
        tables=["AFM_2_1_TEST.AFM_2_1_goszakup"],
        algorithms=["БС-20"],
        note="Две формы отчётности связываются по имени бенефициара.",
    ),
    DataSource(
        key="Самрук_Казына",
        name="Поставщики фонда «Самрук-Казына»",
        organization="АО «Самрук-Казына»",
        tables=["AFM_2_1_TEST.AFM_2_1_samruk"],
        algorithms=["БС-21"],
    ),
    DataSource(
        key="ГенПрок",
        name="Генеральная прокуратура",
        organization="Генеральная прокуратура РК",
        tables=["AFM_2_5.AFM_2_5_1"],
        algorithms=["БС-14"],
        note=(
            "Алгоритм БС-14 отключён и в реестре не участвует: в итоговой таблице "
            "его нет, а состав полей источника не подтверждён."
        ),
    ),
    DataSource(
        key="_справочники",
        name="Общие справочники",
        organization="Министерство юстиции РК, КГД МФ РК",
        tables=COMMON_TABLES,
        algorithms=[],
        note=(
            "Подтягиваются почти каждым алгоритмом: учредители, руководители, "
            "работники, наименования ЮЛ и ФЛ, тип собственности, документы, доли."
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
