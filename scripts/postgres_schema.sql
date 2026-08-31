-- Olist AI 运营分析系统 PostgreSQL 初始化脚本
-- 应用首次连接时会自动执行同等建表逻辑；此文件用于审计和手动初始化。

CREATE TABLE IF NOT EXISTS operation_tasks (
    task_id VARCHAR(32) PRIMARY KEY,
    status VARCHAR(20) NOT NULL,
    created_at VARCHAR(40) NOT NULL,
    updated_at VARCHAR(40) NOT NULL,
    payload TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_operation_tasks_created_at
    ON operation_tasks (created_at DESC);
