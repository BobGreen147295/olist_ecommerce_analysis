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

CREATE TABLE IF NOT EXISTS commerce_data_sources (
    source_id VARCHAR(32) PRIMARY KEY,
    display_name VARCHAR(120) NOT NULL,
    source_type VARCHAR(24) NOT NULL,
    status VARCHAR(24) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT FALSE,
    created_by VARCHAR(32) NOT NULL,
    created_at VARCHAR(40) NOT NULL,
    record_count INTEGER NOT NULL,
    coverage_start VARCHAR(40),
    coverage_end VARCHAR(40),
    mapping_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS commerce_orders (
    source_id VARCHAR(32) NOT NULL,
    order_id VARCHAR(120) NOT NULL,
    customer_id VARCHAR(120),
    ordered_at VARCHAR(40) NOT NULL,
    total_amount DOUBLE PRECISION NOT NULL,
    currency VARCHAR(12),
    status VARCHAR(48),
    market VARCHAR(16),
    timezone VARCHAR(64),
    customer_locale VARCHAR(32),
    marketing_consent VARCHAR(16),
    PRIMARY KEY (source_id, order_id)
);

CREATE INDEX IF NOT EXISTS idx_commerce_orders_source_time
    ON commerce_orders (source_id, ordered_at ASC);

CREATE TABLE IF NOT EXISTS agent_feedback (
    feedback_id VARCHAR(32) PRIMARY KEY,
    message_id VARCHAR(32) UNIQUE NOT NULL,
    conversation_id VARCHAR(32) NOT NULL,
    username VARCHAR(32) NOT NULL,
    rating INTEGER NOT NULL,
    reason TEXT,
    feedback_type VARCHAR(24) NOT NULL DEFAULT 'content',
    status VARCHAR(24) NOT NULL DEFAULT 'open',
    resolution TEXT,
    resolved_by VARCHAR(32),
    created_at VARCHAR(40) NOT NULL,
    resolved_at VARCHAR(40)
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
    has_error BOOLEAN NOT NULL,
    evidence_coverage DOUBLE PRECISION,
    source_citation_rate DOUBLE PRECISION,
    action_completeness DOUBLE PRECISION,
    quality_score DOUBLE PRECISION,
    model_provider VARCHAR(24),
    model_name VARCHAR(80),
    evaluation_version VARCHAR(24)
);
