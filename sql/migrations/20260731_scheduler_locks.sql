CREATE TABLE IF NOT EXISTS finvue_scheduler_locks (
    `key` VARCHAR(191) NOT NULL PRIMARY KEY,
    owner VARCHAR(191) NOT NULL,
    locked_until DATETIME NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    KEY idx_finvue_scheduler_locks_locked_until (locked_until)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
