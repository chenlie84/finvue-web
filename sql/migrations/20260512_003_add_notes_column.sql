-- 添加 notes 字段到 finvue_operation_live_stats 表（用于手工录入备注）

ALTER TABLE finvue_operation_live_stats ADD COLUMN notes VARCHAR(512) COMMENT '备注（手工录入标识）' AFTER earn_score;