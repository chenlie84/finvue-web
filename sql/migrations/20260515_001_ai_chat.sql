-- AI 对话系统数据表
-- 创建时间: 2025-05-15

-- AI 对话会话表
CREATE TABLE IF NOT EXISTS finvue_ai_chat_sessions (
    id INT AUTO_INCREMENT PRIMARY KEY COMMENT '会话ID',
    session_id VARCHAR(64) NOT NULL UNIQUE COMMENT '会话唯一标识',
    title VARCHAR(255) DEFAULT '新对话' COMMENT '会话标题',
    system_prompt TEXT COMMENT '系统提示词',
    model VARCHAR(128) COMMENT '使用的模型',
    created_by VARCHAR(64) NOT NULL COMMENT '创建者',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    is_deleted TINYINT(1) DEFAULT 0 COMMENT '是否删除',
    INDEX idx_session_id (session_id),
    INDEX idx_created_by (created_by),
    INDEX idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='AI对话会话表';

-- AI 对话消息表
CREATE TABLE IF NOT EXISTS finvue_ai_chat_messages (
    id INT AUTO_INCREMENT PRIMARY KEY COMMENT '消息ID',
    session_id VARCHAR(64) NOT NULL COMMENT '所属会话',
    role VARCHAR(16) NOT NULL COMMENT '角色: user/assistant/system',
    content TEXT NOT NULL COMMENT '消息内容',
    model VARCHAR(128) COMMENT '使用的模型',
    tokens INT DEFAULT 0 COMMENT 'token数量',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    INDEX idx_session_id (session_id),
    INDEX idx_created_at (created_at),
    FOREIGN KEY (session_id) REFERENCES finvue_ai_chat_sessions(session_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='AI对话消息表';

-- AI 提示词模板表
CREATE TABLE IF NOT EXISTS finvue_ai_prompt_templates (
    id INT AUTO_INCREMENT PRIMARY KEY COMMENT '模板ID',
    name VARCHAR(128) NOT NULL COMMENT '模板名称',
    description VARCHAR(512) COMMENT '模板描述',
    content TEXT NOT NULL COMMENT '提示词内容',
    category VARCHAR(64) DEFAULT 'general' COMMENT '分类',
    is_system TINYINT(1) DEFAULT 0 COMMENT '是否为系统提示词',
    is_default TINYINT(1) DEFAULT 0 COMMENT '是否默认',
    created_by VARCHAR(64) NOT NULL COMMENT '创建者',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    INDEX idx_category (category),
    INDEX idx_created_by (created_by)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='AI提示词模板表';

-- AI 知识库表
CREATE TABLE IF NOT EXISTS finvue_ai_knowledge_base (
    id INT AUTO_INCREMENT PRIMARY KEY COMMENT '知识库ID',
    name VARCHAR(128) NOT NULL COMMENT '知识库名称',
    description VARCHAR(512) COMMENT '知识库描述',
    file_name VARCHAR(255) COMMENT '文件名',
    file_type VARCHAR(32) COMMENT '文件类型',
    file_size BIGINT COMMENT '文件大小',
    content TEXT COMMENT '文件内容摘要',
    status VARCHAR(16) DEFAULT 'pending' COMMENT '状态: pending/ready/error',
    created_by VARCHAR(64) NOT NULL COMMENT '创建者',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    INDEX idx_created_by (created_by),
    INDEX idx_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='AI知识库表';

-- 插入默认提示词模板
INSERT INTO finvue_ai_prompt_templates (name, description, content, category, is_system, is_default, created_by) VALUES
('通用助手', '默认的通用AI助手提示词', '你是一位专业、友好的AI助手。请用清晰、准确的语言回答用户的问题。如果不确定答案，请如实告知。', 'general', 1, 1, 'system'),
('财经分析师', '专注于财经领域的分析助手', '你是一位资深投资顾问分析专家，精通A股、基金、固收等资产，具备CFA等专业资质。请对投顾直播内容进行客观、专业的分析评估。', 'finance', 1, 0, 'system'),
('文案优化', '帮助优化文案的助手', '你是一位专业文案专家，擅长优化和改写各种类型的内容。请在保持原意的基础上，提升文案的质量、表达力和感染力。', 'writing', 1, 0, 'system');
