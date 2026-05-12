-- 客户数据索引优化
-- 用于提升核心用户运营趋势看板查询速度

-- 1. finvue_customer_profiles 索引
ALTER TABLE finvue_customer_profiles 
ADD INDEX idx_finvue_customer_profiles_anchor (latest_anchor_name);

-- 2. finvue_customer_sessions 索引
ALTER TABLE finvue_customer_sessions 
ADD INDEX idx_finvue_customer_sessions_customer (customer_id);

ALTER TABLE finvue_customer_sessions 
ADD INDEX idx_finvue_customer_sessions_room (room_id);

ALTER TABLE finvue_customer_sessions 
ADD INDEX idx_finvue_customer_sessions_analyzed_at (analyzed_at);

-- 复合索引：customer_id + analyzed_at（用于月度统计）
ALTER TABLE finvue_customer_sessions 
ADD INDEX idx_finvue_customer_sessions_cust_date (customer_id, analyzed_at);

-- 复合索引：customer_id + room_id（用于场次统计）
ALTER TABLE finvue_customer_sessions 
ADD INDEX idx_finvue_customer_sessions_cust_room (customer_id, room_id);