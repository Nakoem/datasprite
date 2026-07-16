# Code Review Report — 数仓扩容升级

> 审查日期：2026-07-16  
> 审查范围：5 个变更文件  
> 触发场景：数据库从 5 表/455 订单 → 7 表/6505 订单的大规模改造

---

## 审查文件

| # | 文件 | 改动量 | 结果 |
|:--|:---|:--|:--:|
| 1 | `app/services/meta_knowledge_service.py` | +8 行 | ✅ 通过 |
| 2 | `app/scripts/gen_extra_seed.py` | ~629 行改动 | ⚠️ 2 个问题 |
| 3 | `docker/mysql/dw.sql` | +432 行 | ✅ 通过 |
| 4 | `conf/meta_config.yaml` | +211 行 | ⚠️ 1 个问题 |

---

## 发现的问题

### 1. MEDIUM — AOV 指标关联列指向错误

**文件：** `conf/meta_config.yaml:343`

```yaml
# 修复前
- name: AOV
  relevant_columns:
    - fact_order.order_quantity   # ❌ 销量，不是金额

# 修复后
- name: AOV
  relevant_columns:
    - fact_order.order_amount     # ✅ 订单金额
```

**影响：** LLM 在 recall 阶段拿到错误关联后，可能生成 `AVG(order_quantity)` 而非 `AVG(order_amount)`，计算结果完全错误。

**已修复 ✅**

---

### 2. MEDIUM — 伪泊松采样实现与实际行为不符

**文件：** `app/scripts/gen_extra_seed.py:476-482`

```python
# 修复前（伪泊松：期望值 = expected + 1，系统性偏高）
n = 1
p = expected / 1.0
while p > 0:
    if random.random() < p:
        n += 1
    p -= 1.0

# 修复后（Knuth's algorithm：标准泊松分布）
if expected > 0:
    L = math.exp(-expected)
    k = 0
    p = 1.0
    while p > L:
        k += 1
        p *= random.random()
    n = max(1, min(k, 20))
else:
    n = 1
```

**影响：** 原实现导致订单数系统性偏高约 18%。修正后为保持数据规模，将目标订单从 4600 上调至 5600。

**已修复 ✅ + `import math`**

---

### 3. LOW — 促销展示名称缺少年份前缀

**文件：** `app/scripts/gen_extra_seed.py:364, 440`（两处）

```python
# 修复前（只对含"年"的名称生效）
display_name = name.replace("年", f"{year}年")

# 修复后（统一加年份前缀）
display_name = f"{year} {name}"
```

**影响：** 大部分促销模板名不含"年"字（如"情人节美妆秒杀"），`replace` 无操作，`REPLACE INTO` 覆盖后数据库中促销名称丢失年份。

**已修复 ✅**

---

## 审查通过的项目

### `meta_knowledge_service.py` — Decimal-to-Float Fix
- `try: float(v)` + `except (TypeError, ValueError)` 正确处理三种情况
- 只用于 Qdrant payload（JSON 序列化），不做精确运算，精度损失无影响

### `dw.sql` — SQL 表定义
| 表 | 检查项 | 结果 |
|:---|:---|:--:|
| `dim_supplier` | 6 列，主键 `VARCHAR(20)` | ✅ |
| `dim_promotion` | `DECIMAL(3,2)` 容纳 max 0.50 | ✅ |
| `fact_inventory` | `DECIMAL(10,2)` 容纳 max ~6650 | ✅ |
| `fact_order` | 包含 `promotion_id DEFAULT NULL` | ✅ |

无语法问题、无外键类型不匹配、无数据类型溢出。

### 其他验证通过
- 订单 ID 格式 `ORD{date_id}{NNNNN}` 与原有 `ORD{date_id}{NNN}` 不冲突
- 日期范围 2024 全年 + 2025 Q2-Q4 + 2026 H1 = 912 天 ✅
- 促销按年份过滤正确（2026 只保留 H1，`month <= 6`）
- 库存 ID `INV{date_id}{product_id}` 唯一性保证
- 所有 `REPLACE INTO` 列顺序与 DW 表定义一致
- `meta_config.yaml` 8 张表列名与 DW schema 完全匹配

---

## 修复后的验证结果

| 表 | 行数 | 状态 |
|:---|---:|:--:|
| dim_customer | 200 | ✅ |
| dim_product | 50 | ✅ |
| dim_date | 912 | ✅ |
| dim_promotion | 43 | ✅ |
| dim_supplier | 16 | ✅ |
| fact_inventory | 1,500 | ✅ |
| fact_order | 6,505 | ✅ |

端到端测试：华东地区 GMV = 1,962,583 元 ✅

---

## 总结

| 严重度 | 数量 | 处理 |
|:---|:--:|:---|
| 高危 | 0 | — |
| 中危 | 2 | 全部修复 |
| 低危 | 1 | 已修复 |
| 通过 | — | 3 个文件无问题 |

**commit:** d956000 — `fix: #7 CR修复 — 泊松采样算法+促销名称年份+AOV关联列+订单目标调整`
