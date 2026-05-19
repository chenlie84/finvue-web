-- 热搜追踪模块数据表
-- 用于存储多平台热搜数据，支持历史趋势对比和AI分析

-- 1. 热搜条目表：存储每条热搜的详细信息
CREATE TABLE IF NOT EXISTS finvue_hotspot_items (
    id VARCHAR(64) PRIMARY KEY,
    platform VARCHAR(32) NOT NULL COMMENT '平台标识：weibo/zhihu/baidu/douyin/bilibili等',
    title VARCHAR(255) NOT NULL COMMENT '热搜标题',
    url TEXT COMMENT '热搜链接',
    `rank` INT DEFAULT 0 COMMENT '当前排名',
    hot_value VARCHAR(64) COMMENT '热度值（各平台格式不同）',
    keywords JSON COMMENT '提取的关键词',
    first_seen_at DATETIME NOT NULL COMMENT '首次发现时间',
    last_seen_at DATETIME NOT NULL COMMENT '最后出现时间',
    appearance_count INT DEFAULT 1 COMMENT '出现次数',
    ai_analysis TEXT COMMENT 'AI分析结果',
    ai_analyzed_at DATETIME COMMENT 'AI分析时间',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_platform (platform),
    INDEX idx_first_seen (first_seen_at),
    INDEX idx_last_seen (last_seen_at),
    INDEX idx_title (title(100))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='热搜条目表';

-- 2. 热搜历史快照表：存储每小时/每时刻的排名快照，用于趋势分析
CREATE TABLE IF NOT EXISTS finvue_hotspot_snapshots (
    id VARCHAR(64) PRIMARY KEY,
    item_id VARCHAR(64) NOT NULL COMMENT '关联热搜条目',
    platform VARCHAR(32) NOT NULL,
    title VARCHAR(255) NOT NULL,
    `rank` INT DEFAULT 0 COMMENT '该时刻排名',
    hot_value VARCHAR(64) COMMENT '该时刻热度值',
    snapshot_time DATETIME NOT NULL COMMENT '快照时间',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_item (item_id),
    INDEX idx_platform_time (platform, snapshot_time),
    INDEX idx_snapshot_time (snapshot_time)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='热搜排名快照表';

-- 3. 热搜监控配置表：存储用户关注的平台和关键词
CREATE TABLE IF NOT EXISTS finvue_hotspot_settings (
    id VARCHAR(64) PRIMARY KEY DEFAULT 'default',
    enabled_platforms JSON COMMENT '启用的平台列表',
    tracked_keywords JSON COMMENT '追踪的关键词列表',
    fetch_interval_minutes INT DEFAULT 60 COMMENT '抓取间隔（分钟）',
    retention_days INT DEFAULT 30 COMMENT '数据保留天数',
    auto_analyze BOOLEAN DEFAULT FALSE COMMENT '是否自动AI分析',
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='热搜监控配置';

-- 4. 初始化默认配置
INSERT IGNORE INTO finvue_hotspot_settings (id, enabled_platforms, tracked_keywords, fetch_interval_minutes, retention_days, auto_analyze)
VALUES (
    'default',
    '["weibo", "zhihu", "baidu", "douyin", "bilibili", "toutiao", "cls", "wallstreetcn"]',
    '[]',
    60,
    30,
    FALSE
);

-- 5. 平台信息表：存储各平台的元信息
CREATE TABLE IF NOT EXISTS finvue_hotspot_platforms (
    id VARCHAR(32) PRIMARY KEY COMMENT '平台标识',
    name VARCHAR(64) NOT NULL COMMENT '平台名称',
    category VARCHAR(32) COMMENT '分类：social/news/finance/video',
    icon VARCHAR(16) COMMENT '图标emoji',
    enabled BOOLEAN DEFAULT TRUE,
    priority INT DEFAULT 100 COMMENT '显示优先级',
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='平台信息表';

-- 6. 初始化平台信息
INSERT IGNORE INTO finvue_hotspot_platforms (id, name, category, icon, priority) VALUES
('weibo', '微博热搜', 'social', '📱', 1),
('zhihu', '知乎热榜', 'social', '💡', 2),
('baidu', '百度热搜', 'search', '🔍', 3),
('douyin', '抖音热点', 'video', '🎬', 4),
('bilibili', 'B站热搜', 'video', '📺', 5),
('toutiao', '今日头条', 'news', '📰', 6),
('cls', '财联社', 'finance', '💰', 7),
('wallstreetcn', '华尔街见闻', 'finance', '📈', 8),
('ifeng', '凤凰网', 'news', '🔥', 9),
('pengpai', '澎湃新闻', 'news', '🌊', 10),
('tieba', '贴吧热议', 'social', '💬', 11);