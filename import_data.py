import json
from pathlib import Path

import pymysql

from db_utils import get_connection


TABLE_DDL = """
CREATE TABLE IF NOT EXISTS `crs_tianxieshuju` (
  `区域` text,
  `目标填写客户数` bigint DEFAULT NULL,
  `总填写客户数` bigint DEFAULT NULL,
  `上传资产证明图片客户数` bigint DEFAULT NULL,
  `今日填写客户数` bigint DEFAULT NULL,
  `距离目标gap` bigint DEFAULT NULL,
  `填写销售数` bigint DEFAULT NULL,
  `完成度` double DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
"""


def import_from_json(json_path: str = "example/demo.json", truncate: bool = True) -> None:
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
                    `上传资产证明图片客户数`,
                    `今日填写客户数`,
                    `距离目标gap`,
                    `填写销售数`,
                    `完成度`
                ) VALUES (
                    %(区域)s,
                    %(目标填写客户数)s,
                    %(总填写客户数)s,
                    %(上传资产证明图片客户数)s,
                    %(今日填写客户数)s,
                    %(距离目标gap)s,
                    %(填写销售数)s,
                    %(完成度)s
                )
            """
            for record in records:
                cursor.execute(insert_sql, record)

        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    # 默认使用示例数据导入本地表
    import_from_json()
