import json
from pathlib import Path

import pymysql

from db_utils import get_connection


TABLE_DDL = """
CREATE TABLE IF NOT EXISTS `crs_tianxieshuju` (
  `区域` text,
  `目标填写客户数` bigint DEFAULT NULL,
  `总填写客户数` bigint DEFAULT NULL,
  `今日填写客户数` bigint DEFAULT NULL,
  `距离目标gap` bigint DEFAULT NULL,
  `完成度` double DEFAULT NULL,
  `时间` datetime DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
"""


def import_from_json(json_path: str = "data/crs.json", truncate: bool = True) -> None:
    path = Path(json_path)
    if not path.is_file():
        raise FileNotFoundError(f"JSON file not found: {path}")

    with path.open("r", encoding="utf-8") as f:
        records = json.load(f)

    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(TABLE_DDL)
            if truncate:
                cursor.execute("TRUNCATE TABLE `crs_tianxieshuju`")

            insert_sql = """
                INSERT INTO `crs_tianxieshuju` (
                    `区域`,
                    `目标填写客户数`,
                    `总填写客户数`,
                    `今日填写客户数`,
                    `距离目标gap`,
                    `完成度`,
                    `时间`
                ) VALUES (
                    %(区域)s,
                    %(目标填写客户数)s,
                    %(总填写客户数)s,
                    %(今日填写客户数)s,
                    %(距离目标gap)s,
                    %(完成度)s,
                    %(时间)s
                )
            """
            for record in records:
                cursor.execute(insert_sql, record)

        conn.commit()
        print(f"成功导入 {len(records)} 条记录")
    finally:
        conn.close()


if __name__ == "__main__":
    # 默认使用示例数据导入本地表
    import_from_json()
