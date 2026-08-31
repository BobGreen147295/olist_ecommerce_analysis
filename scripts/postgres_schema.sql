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

CREATE TABLE IF NOT EXISTS app_users (
    username VARCHAR(32) PRIMARY KEY,
    password_hash TEXT NOT NULL,
    role VARCHAR(20) NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at VARCHAR(40) NOT NULL
);

CREATE TABLE IF NOT EXISTS chat_conversations (
    conversation_id VARCHAR(32) PRIMARY KEY,
    username VARCHAR(32) NOT NULL,
    title VARCHAR(120) NOT NULL,
    created_at VARCHAR(40) NOT NULL,
    updated_at VARCHAR(40) NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_chat_conversations_user_updated
    ON chat_conversations (username, updated_at DESC);

CREATE TABLE IF NOT EXISTS chat_messages (
    message_id VARCHAR(32) PRIMARY KEY,
    conversation_id VARCHAR(32) NOT NULL,
    role VARCHAR(16) NOT NULL,
    content TEXT NOT NULL,
    created_at VARCHAR(40) NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_chat_messages_conversation
    ON chat_messages (conversation_id, created_at ASC);

CREATE TABLE IF NOT EXISTS agent_feedback (
    feedback_id VARCHAR(32) PRIMARY KEY,
    message_id VARCHAR(32) UNIQUE NOT NULL,
    conversation_id VARCHAR(32) NOT NULL,
    username VARCHAR(32) NOT NULL,
    rating INTEGER NOT NULL,
    reason TEXT,
    created_at VARCHAR(40) NOT NULL
);

CREATE TABLE IF NOT EXISTS agent_run_metrics (
    run_id VARCHAR(32) PRIMARY KEY,
    conversation_id VARCHAR(32),
    username VARCHAR(32) NOT NULL,
    created_at VARCHAR(40) NOT NULL,
    duration_ms INTEGER NOT NULL,
    tool_count INTEGER NOT NULL,
    successful_tool_count INTEGER NOT NULL,
    finding_count INTEGER NOT NULL,
    action_count INTEGER NOT NULL,
    structured_output BOOLEAN NOT NULL,
    has_error BOOLEAN NOT NULL
);
