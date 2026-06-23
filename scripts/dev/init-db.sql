-- RemeMate 本地开发数据库初始化（dev only，密码仅本机用）
-- 三角色分工见 docs/design/data-isolation-security.md §角色分离

-- 幂等：先删后建（仅 dev 环境可这样做）
DROP DATABASE IF EXISTS rememate;
DROP ROLE IF EXISTS rememate;
DROP ROLE IF EXISTS rememate_dispatch;
DROP ROLE IF EXISTS rememate_owner;

-- 1. owner：建表、跑 migration，是所有表 owner，不被 app 用于运行时连接
CREATE ROLE rememate_owner LOGIN PASSWORD 'dev_owner_pw';

-- 2. app：gunicorn 运行时连接，非 owner，受 FORCE RLS 约束
CREATE ROLE rememate LOGIN PASSWORD 'dev_app_pw';

-- 3. dispatch：后台任务，BYPASSRLS，靠显式 user_id 过滤兜底
CREATE ROLE rememate_dispatch LOGIN PASSWORD 'dev_dispatch_pw' BYPASSRLS;

-- 数据库归 owner 所有
CREATE DATABASE rememate OWNER rememate_owner;

-- 切到 rememate 库配置 schema 权限与默认权限
\connect rememate

-- public schema 归 owner，app/dispatch 只用不建
ALTER SCHEMA public OWNER TO rememate_owner;
GRANT USAGE ON SCHEMA public TO rememate, rememate_dispatch;

-- 默认权限：今后 owner 在 public 建的表/序列，app 与 dispatch 自动获得 DML
ALTER DEFAULT PRIVILEGES FOR ROLE rememate_owner IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO rememate, rememate_dispatch;
ALTER DEFAULT PRIVILEGES FOR ROLE rememate_owner IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO rememate, rememate_dispatch;

-- 不给 app/dispatch CREATE，建表只能 owner 来（强化角色分离）
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
