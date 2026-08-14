-- ============================================================================
-- Реестр БС — схема базы bs_registry
--
-- Приложение создаёт эти таблицы автоматически при первом старте.
-- Скрипт нужен, если схему требуется развернуть заранее или проверить вручную:
--   psql -U bs_registry -d bs_registry -f 02_create_tables.sql
-- ============================================================================

-- ---------------------------------------------------------------------------
-- SQL алгоритмов выявления БС
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS bs_algorithms (
    id                      SERIAL PRIMARY KEY,
    code                    VARCHAR(16)  NOT NULL UNIQUE,
    name                    VARCHAR(255) NOT NULL,
    description             TEXT         NOT NULL DEFAULT '',
    sql_script              TEXT         NOT NULL,
    clickhouse_result_table VARCHAR(128) NOT NULL DEFAULT '',
    source                  VARCHAR(64)  NOT NULL DEFAULT '',
    priority_score          INTEGER      NOT NULL DEFAULT 0,
    is_active               BOOLEAN      NOT NULL DEFAULT TRUE,
    version                 INTEGER      NOT NULL DEFAULT 1,
    created_at              TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ  NOT NULL DEFAULT now(),

    -- служебные поля, не влияющие на логику выявления БС
    depends_on              VARCHAR(255) NOT NULL DEFAULT '',
    order_index             INTEGER      NOT NULL DEFAULT 0,
    last_run_at             TIMESTAMPTZ,
    last_run_status         VARCHAR(16),
    last_row_count          INTEGER,
    last_error              TEXT
);

CREATE INDEX IF NOT EXISTS ix_bs_algorithms_code ON bs_algorithms (code);

COMMENT ON TABLE  bs_algorithms IS 'Алгоритмы выявления бенефициарных собственников';
COMMENT ON COLUMN bs_algorithms.code IS 'Код алгоритма из ТЗ, например БС-1';
COMMENT ON COLUMN bs_algorithms.sql_script IS 'Полный SQL код для выполнения в ClickHouse';
COMMENT ON COLUMN bs_algorithms.clickhouse_result_table IS 'Таблица результата, например AFM_6_TEST.AFM_6_1_7';
COMMENT ON COLUMN bs_algorithms.priority_score IS 'Балл приоритетности (0 — балл не присваивается)';
COMMENT ON COLUMN bs_algorithms.depends_on IS 'Коды алгоритмов, рассчитываемых раньше, через запятую';

-- ---------------------------------------------------------------------------
-- История изменений SQL
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS bs_algorithm_history (
    id           SERIAL PRIMARY KEY,
    algorithm_id INTEGER     NOT NULL REFERENCES bs_algorithms (id) ON DELETE CASCADE,
    sql_script   TEXT        NOT NULL,
    changed_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    reason       TEXT        NOT NULL DEFAULT '',
    version      INTEGER,
    changed_by   VARCHAR(64)
);

CREATE INDEX IF NOT EXISTS ix_bs_algorithm_history_algorithm_id
    ON bs_algorithm_history (algorithm_id);

COMMENT ON TABLE  bs_algorithm_history IS 'Предыдущие версии SQL алгоритмов';
COMMENT ON COLUMN bs_algorithm_history.sql_script IS 'SQL код, действовавший до изменения';

-- ---------------------------------------------------------------------------
-- Пользователи системы
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS bs_users (
    id            SERIAL PRIMARY KEY,
    username      VARCHAR(64)  NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    role          VARCHAR(16)  NOT NULL DEFAULT 'user',
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT now(),

    -- служебные поля
    full_name     VARCHAR(255) NOT NULL DEFAULT '',
    is_active     BOOLEAN      NOT NULL DEFAULT TRUE,
    last_login_at TIMESTAMPTZ,

    CONSTRAINT ck_bs_users_role CHECK (role IN ('administrator', 'user'))
);

CREATE INDEX IF NOT EXISTS ix_bs_users_username ON bs_users (username);

COMMENT ON TABLE  bs_users IS 'Пользователи системы';
COMMENT ON COLUMN bs_users.role IS 'administrator — полный доступ; user — просмотр и чат';
