CREATE TABLE IF NOT EXISTS sop_custom_options (
  id            BIGINT       NOT NULL AUTO_INCREMENT,
  week          TINYINT      NOT NULL COMMENT '1-4',
  action_index  TINYINT      NOT NULL COMMENT '周内第几个动作',
  sub_index     TINYINT      NOT NULL COMMENT '子步骤序号',
  label         VARCHAR(64)  NOT NULL COMMENT '人工添加的选项文案',
  sort_order    INT          NOT NULL DEFAULT 0,
  created_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uk_custom_option_path_label (week, action_index, sub_index, label),
  KEY idx_custom_option_path (week, action_index, sub_index, sort_order)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
