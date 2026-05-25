-- 为导入日志表添加 mode 字段
ALTER TABLE finvue_operation_import_logs 
ADD COLUMN mode VARCHAR(16) DEFAULT 'increment' COMMENT '导入模式(increment/overwrite)' AFTER imported_by;
