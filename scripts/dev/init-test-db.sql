-- 独立测试库（dev only）。复用 init-db.sql 建好的三个角色，只建一个隔离的库。
-- 目的：pytest 的 conftest 清库只动 rememate_test，绝不碰 rememate(dev)。

DROP DATABASE IF EXISTS rememate_test;
CREATE DATABASE rememate_test OWNER rememate_owner;

\connect rememate_test

ALTER SCHEMA public OWNER TO rememate_owner;
GRANT USAGE ON SCHEMA public TO rememate, rememate_dispatch;

ALTER DEFAULT PRIVILEGES FOR ROLE rememate_owner IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO rememate, rememate_dispatch;
ALTER DEFAULT PRIVILEGES FOR ROLE rememate_owner IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO rememate, rememate_dispatch;

REVOKE CREATE ON SCHEMA public FROM PUBLIC;
