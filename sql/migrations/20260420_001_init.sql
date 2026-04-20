-- SOP 执行台数据库建表脚本
-- 要求 MySQL 8.0+（使用 utf8mb4_0900_ai_ci 字符序）
-- 幂等执行：可重复运行，不会报错

CREATE TABLE IF NOT EXISTS sop_anchors (
  anchor_name      VARCHAR(64)   NOT NULL COMMENT '主播名，天然主键',
  operator_name    VARCHAR(64)   NOT NULL COMMENT '当前负责的运营',
  start_date       DATE          NOT NULL COMMENT '开始带新日期',
  last_saved_date  DATE          DEFAULT NULL COMMENT '最近一次保存日期',
  current_week     TINYINT       NOT NULL DEFAULT 1 COMMENT '当前周次 1-4',
  status           VARCHAR(16)   NOT NULL DEFAULT '进行中',
  note             TEXT          DEFAULT NULL COMMENT '主播级备注',
  current_blocker  VARCHAR(128)  DEFAULT NULL,
  created_at       DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at       DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (anchor_name),
  KEY idx_operator (operator_name),
  KEY idx_status   (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS sop_action_progress (
  id           BIGINT       NOT NULL AUTO_INCREMENT,
  anchor_name  VARCHAR(64)  NOT NULL,
  week         TINYINT      NOT NULL COMMENT '1-4',
  action_index TINYINT      NOT NULL COMMENT '周内第几个动作',
  sub_index    TINYINT      NOT NULL DEFAULT -1 COMMENT '子步骤序号，-1 表示非子步骤层',
  child_index  TINYINT      NOT NULL DEFAULT -1 COMMENT '子子步骤序号，-1 表示非子子层',
  checked      TINYINT(1)   NOT NULL DEFAULT 0,
  note         TEXT         DEFAULT NULL,
  updated_at   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uk_item (anchor_name, week, action_index, sub_index, child_index),
  CONSTRAINT fk_progress_anchor FOREIGN KEY (anchor_name)
    REFERENCES sop_anchors(anchor_name) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS sop_week_completion (
  anchor_name   VARCHAR(64)  NOT NULL,
  week          TINYINT      NOT NULL,
  completed_at  DATE         NOT NULL COMMENT '手动标记"本周达标"的日期',
  created_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (anchor_name, week),
  CONSTRAINT fk_completion_anchor FOREIGN KEY (anchor_name)
    REFERENCES sop_anchors(anchor_name) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
