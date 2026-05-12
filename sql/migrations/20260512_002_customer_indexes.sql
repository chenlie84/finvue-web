-- 客户数据索引优化
-- 用于提升核心用户运营趋势看板查询速度
-- 使用存储过程实现幂等性（可重复执行）

DELIMITER //

-- 创建安全添加索引的存储过程
DROP PROCEDURE IF EXISTS safe_add_index //
CREATE PROCEDURE safe_add_index(
    IN table_name VARCHAR(64),
    IN index_name VARCHAR(64),
    IN index_columns VARCHAR(255)
)
BEGIN
    DECLARE index_exists INT DEFAULT 0;
    
    -- 检查索引是否存在
    SELECT COUNT(*) INTO index_exists
    FROM information_schema.statistics
    WHERE table_schema = DATABASE()
      AND table_name = table_name
      AND index_name = index_name;
    
    -- 如果不存在则添加
    IF index_exists = 0 THEN
        SET @sql = CONCAT('ALTER TABLE ', table_name, ' ADD INDEX ', index_name, ' (', index_columns, ')');
        PREPARE stmt FROM @sql;
        EXECUTE stmt;
        DEALLOCATE PREPARE stmt;
    END IF;
END //

DELIMITER ;

-- 执行索引添加
CALL safe_add_index('finvue_customer_profiles', 'idx_finvue_customer_profiles_anchor', 'latest_anchor_name');
CALL safe_add_index('finvue_customer_sessions', 'idx_finvue_customer_sessions_customer', 'customer_id');
CALL safe_add_index('finvue_customer_sessions', 'idx_finvue_customer_sessions_room', 'room_id');
CALL safe_add_index('finvue_customer_sessions', 'idx_finvue_customer_sessions_analyzed_at', 'analyzed_at');
CALL safe_add_index('finvue_customer_sessions', 'idx_finvue_customer_sessions_cust_date', 'customer_id, analyzed_at');
CALL safe_add_index('finvue_customer_sessions', 'idx_finvue_customer_sessions_cust_room', 'customer_id, room_id');

-- 清理存储过程
DROP PROCEDURE IF EXISTS safe_add_index;