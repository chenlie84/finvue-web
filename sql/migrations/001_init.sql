CREATE TABLE IF NOT EXISTS finvue_app_kv (
  `key` VARCHAR(191) NOT NULL PRIMARY KEY,
  value JSON NOT NULL,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

CREATE TABLE IF NOT EXISTS finvue_users (
  username VARCHAR(191) NOT NULL PRIMARY KEY,
  password_salt VARCHAR(255) NOT NULL,
  password_hash VARCHAR(255) NOT NULL,
  role VARCHAR(32) NOT NULL DEFAULT 'user',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

CREATE TABLE IF NOT EXISTS finvue_auth_rate_limits (
  `key` VARCHAR(191) NOT NULL PRIMARY KEY,
  value JSON NOT NULL,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

CREATE TABLE IF NOT EXISTS finvue_sessions (
  token_hash VARCHAR(191) NOT NULL PRIMARY KEY,
  username VARCHAR(191) NOT NULL,
  role VARCHAR(32) NOT NULL DEFAULT 'user',
  expires_at DATETIME NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_finvue_sessions_user FOREIGN KEY (username) REFERENCES finvue_users(username) ON DELETE CASCADE,
  INDEX idx_finvue_sessions_expires_at (expires_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

CREATE TABLE IF NOT EXISTS finvue_anchor_profiles (
  id VARCHAR(191) NOT NULL PRIMARY KEY,
  anchor_name VARCHAR(255) NOT NULL,
  raw JSON NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX idx_finvue_anchor_profiles_name (anchor_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

CREATE TABLE IF NOT EXISTS finvue_transcripts (
  id VARCHAR(191) NOT NULL PRIMARY KEY,
  anchor_name VARCHAR(255),
  title VARCHAR(512),
  content LONGTEXT,
  raw JSON NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX idx_finvue_transcripts_anchor_time (anchor_name, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

CREATE TABLE IF NOT EXISTS finvue_analysis_reports (
  id VARCHAR(191) NOT NULL PRIMARY KEY,
  anchor_name VARCHAR(255),
  report_type VARCHAR(128),
  title VARCHAR(512),
  markdown LONGTEXT,
  html LONGTEXT,
  summary TEXT,
  raw JSON NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX idx_finvue_reports_anchor_time (anchor_name, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

CREATE TABLE IF NOT EXISTS finvue_customer_profiles (
  customer_id VARCHAR(191) NOT NULL PRIMARY KEY,
  customer_name VARCHAR(255) NOT NULL,
  latest_anchor_name VARCHAR(255),
  latest_analyzed_at DATETIME,
  latest_live_theme VARCHAR(512),
  latest_rank INT,
  best_rank INT,
  avg_watch_seconds INT,
  labels JSON NOT NULL,
  tags JSON NOT NULL,
  raw JSON NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX idx_finvue_customer_profiles_anchor_time (latest_anchor_name, latest_analyzed_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

CREATE TABLE IF NOT EXISTS finvue_customer_sessions (
  session_id VARCHAR(191) NOT NULL PRIMARY KEY,
  customer_id VARCHAR(191) NOT NULL,
  anchor_name VARCHAR(255),
  room_id VARCHAR(191),
  live_theme VARCHAR(512),
  report_type VARCHAR(128),
  metric_type VARCHAR(128),
  metric_value VARCHAR(255),
  watch_rank INT,
  watch_duration_seconds INT,
  analyzed_at DATETIME,
  source_file VARCHAR(1024),
  raw JSON NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  CONSTRAINT fk_finvue_customer_sessions_profile FOREIGN KEY (customer_id) REFERENCES finvue_customer_profiles(customer_id) ON DELETE CASCADE,
  INDEX idx_finvue_customer_sessions_anchor_time (anchor_name, analyzed_at),
  INDEX idx_finvue_customer_sessions_customer (customer_id),
  INDEX idx_finvue_customer_sessions_metric (metric_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

CREATE TABLE IF NOT EXISTS finvue_compliance_entries (
  id VARCHAR(191) NOT NULL PRIMARY KEY,
  level VARCHAR(64),
  title VARCHAR(512),
  phrase TEXT,
  context LONGTEXT,
  suggestion LONGTEXT,
  raw JSON NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX idx_finvue_compliance_entries_level_time (level, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

CREATE TABLE IF NOT EXISTS finvue_case_entries (
  id VARCHAR(191) NOT NULL PRIMARY KEY,
  category VARCHAR(128),
  title VARCHAR(512),
  phrase TEXT,
  context LONGTEXT,
  raw JSON NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX idx_finvue_case_entries_category_time (category, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

CREATE TABLE IF NOT EXISTS finvue_jobs (
  id VARCHAR(191) NOT NULL PRIMARY KEY,
  type VARCHAR(128) NOT NULL,
  status VARCHAR(32) NOT NULL DEFAULT 'queued',
  progress INT NOT NULL DEFAULT 0,
  payload JSON NOT NULL,
  result JSON,
  error TEXT,
  attempts INT NOT NULL DEFAULT 0,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  started_at DATETIME,
  finished_at DATETIME,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX idx_finvue_jobs_status_created (status, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
