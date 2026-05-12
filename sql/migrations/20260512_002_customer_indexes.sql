-- 客户数据索引优化
-- 用于提升核心用户运营趋势看板查询速度
-- 注意：由于PyMySQL不支持DELIMITER，索引添加由应用层处理幂等性

-- 索引添加语句（如果已存在会报错，但不影响应用启动）
-- 可通过 migrate.py 的错误处理自动跳过已存在的索引

ALTER TABLE finvue_customer_profiles ADD INDEX idx_finvue_customer_profiles_anchor (latest_anchor_name);
ALTER TABLE finvue_customer_sessions ADD INDEX idx_finvue_customer_sessions_customer (customer_id);
ALTER TABLE finvue_customer_sessions ADD INDEX idx_finvue_customer_sessions_room (room_id);
ALTER TABLE finvue_customer_sessions ADD INDEX idx_finvue_customer_sessions_analyzed_at (analyzed_at);
ALTER TABLE finvue_customer_sessions ADD INDEX idx_finvue_customer_sessions_cust_date (customer_id, analyzed_at);
ALTER TABLE finvue_customer_sessions ADD INDEX idx_finvue_customer_sessions_cust_room (customer_id, room_id);