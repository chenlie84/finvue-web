# CSV 导入模板

## 模板列表

| 文件 | 用途 | 导入类型参数 |
|------|------|-------------|
| live_data_template.csv | 直播数据 | `live` |
| video_data_template.csv | 短视频数据 | `video` |
| customer_profiles_template.csv | 客户档案 | `customer_profile` |
| customer_sessions_template.csv | 客户会话 | `customer_session` |

## 导入命令

```bash
python import_csv_to_production.py <csv文件> <类型>

# 示例
python import_csv_to_production.py live_data.csv live
python import_csv_to_production.py video_data.csv video
python import_csv_to_production.py customer_profiles.csv customer_profile
python import_csv_to_production.py customer_sessions.csv customer_session
```

## 字段说明

### 直播数据 (live)

- **主播账号**: 必填
- **直播间ID**: 必填（如无可自动生成）
- **开播时间**: 格式 `YYYY-MM-DD HH:MM:SS`
- **关播时间**: 格式 `YYYY-MM-DD HH:MM:SS`
- 人数类字段: 峰值人数、观看人数等
- 时长类字段: 单位为分钟
- 比率类字段: 百分比数值（如 2.5 表示 2.5%）

### 短视频数据 (video)

- **主播账号**: 必填
- **发布时间**: 格式 `YYYY-MM-DD HH:MM:SS`
- **体裁**: 1min-/1-3min/3-5min/5min+
- 完播率、互动率: 百分比数值

### 客户档案 (customer_profile)

- **客户ID**: 必填，唯一标识
- **客户姓名**: 可选，默认用客户ID
- **标签/标记**: JSON 数组格式，如 `["VIP","高频"]`

### 客户会话 (customer_session)

- **客户ID**: 必填，需先导入客户档案
- **会话ID**: 可自动生成
- **观看时长(秒)**: 单位为秒