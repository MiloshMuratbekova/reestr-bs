-- ============================================================================
-- Реестр БС — создание базы данных PostgreSQL на сервере 10.10.31.35
--
-- Выполнять от суперпользователя:
--   sudo -u postgres psql -f 01_create_database.sql
-- ============================================================================

CREATE ROLE bs_registry WITH LOGIN PASSWORD 'CHANGE_ME';

CREATE DATABASE bs_registry
    WITH OWNER = bs_registry
         ENCODING = 'UTF8'
         LC_COLLATE = 'ru_RU.UTF-8'
         LC_CTYPE = 'ru_RU.UTF-8'
         TEMPLATE = template0;

COMMENT ON DATABASE bs_registry IS
    'Метаданные системы «Реестр БС»: SQL алгоритмов, история изменений, пользователи';
