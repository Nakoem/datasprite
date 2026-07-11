"""
扩充数仓测试数据生成器

为可视化图表准备更丰富的业务数据：在原有 2025 Q1 基础上，补充
- 4 个新品类（美妆护肤 / 母婴用品 / 运动户外 / 图书文具）共 12 个新商品
- 2025 Q2/Q3/Q4 的日期维度
- Q2~Q4 约 340 张订单，带轻微季节性（Q4 购物季走高）

产物写入 docker/mysql/seed_extra.sql，用 REPLACE INTO 保证可重复执行、幂等。
该文件同时会被 Docker 首次初始化时按字母序在 dw.sql 之后自动加载。

用法（无需数据库连接，纯生成文本）：
    python app/scripts/gen_extra_seed.py
"""

import random
from pathlib import Path

# 固定随机种子，保证每次生成的订单完全一致，便于版本管理和复现
random.seed(20250711)

# 输出文件：放进 docker 初始化目录，未来全新构建也会自动带上这批数据
OUTPUT_PATH = Path(__file__).resolve().parents[2] / "docker" / "mysql" / "seed_extra.sql"

# ---- 新增商品：4 个新品类 × 3 款，id 从 P016 起接续原有 P001~P015 ----
# 每项：(product_id, product_name, category, brand, unit_price)
NEW_PRODUCTS = [
    ("P016", "兰蔻小黑瓶精华 30ml", "美妆护肤", "兰蔻", 1080.0),
    ("P017", "雅诗兰黛小棕瓶精华 50ml", "美妆护肤", "雅诗兰黛", 850.0),
    ("P018", "完美日记丝绒哑光口红", "美妆护肤", "完美日记", 99.0),
    ("P019", "花王妙而舒纸尿裤 L码", "母婴用品", "花王", 128.0),
    ("P020", "爱他美卓萃奶粉 3段", "母婴用品", "爱他美", 305.0),
    ("P021", "贝亲宽口径玻璃奶瓶", "母婴用品", "贝亲", 89.0),
    ("P022", "迪卡侬 Quechua 快开帐篷", "运动户外", "迪卡侬", 199.0),
    ("P023", "Keep 天然橡胶瑜伽垫", "运动户外", "Keep", 129.0),
    ("P024", "始祖鸟 Beta 冲锋衣", "运动户外", "始祖鸟", 4500.0),
    ("P025", "《三体》全集三册", "图书文具", "读客", 168.0),
    ("P026", "晨光优品中性笔 12支装", "图书文具", "晨光", 24.0),
    ("P027", "得力多功能订书机", "图书文具", "得力", 35.0),
]

# ---- 原有商品单价（从 dw.sql 现有数据推导），用于新订单计算金额 ----
EXISTING_UNIT_PRICE = {
    "P001": 8999.0, "P002": 9499.0, "P003": 6999.0, "P004": 5499.0,
    "P005": 3200.0, "P006": 899.0, "P007": 1299.0, "P008": 199.0,
    "P009": 599.0, "P010": 25.0, "P011": 5.0, "P012": 5.0,
    "P013": 3.5, "P014": 1399.0, "P015": 899.0,
}

# 全部商品单价表（原有 + 新增），生成订单时按 product_id 取价
UNIT_PRICE = dict(EXISTING_UNIT_PRICE)
for pid, _name, _cat, _brand, price in NEW_PRODUCTS:
    UNIT_PRICE[pid] = price

ALL_PRODUCT_IDS = list(UNIT_PRICE.keys())

# ---- 维度取值：客户 20 人、大区 6 个，沿用原有数据 ----
CUSTOMER_IDS = [f"C{i:03d}" for i in range(1, 21)]
REGION_IDS = ["R001", "R002", "R003", "R004", "R005", "R006"]

# ---- 季度日期定义：Q2~Q4 各月天数 ----
QUARTER_MONTHS = {
    "Q2": [(4, 30), (5, 31), (6, 30)],
    "Q3": [(7, 31), (8, 31), (9, 30)],
    "Q4": [(10, 31), (11, 30), (12, 31)],
}

# 每季度订单量，Q4 明显走高模拟双11/双12购物季，形成上升趋势
QUARTER_ORDER_COUNT = {"Q2": 95, "Q3": 105, "Q4": 140}


def pick_quantity(unit_price: float) -> int:
    """按单价分档决定购买数量：越便宜越可能大批量购买，越贵越接近单件"""
    if unit_price >= 1000:
        return random.choices([1, 2], weights=[85, 15])[0]
    if unit_price >= 100:
        return random.choices([1, 2, 3], weights=[60, 30, 10])[0]
    # 低客单价快消品，数量跨度大，制造销量维度上的差异
    return random.randint(5, 30)


def gen_dim_date_rows() -> list[str]:
    """生成 Q2~Q4 每一天的日期维度行"""
    rows = []
    for quarter, months in QUARTER_MONTHS.items():
        for month, days in months:
            for day in range(1, days + 1):
                date_id = 2025 * 10000 + month * 100 + day
                rows.append(f"({date_id}, 2025, '{quarter}', {month}, {day})")
    return rows


def gen_fact_order_rows() -> list[str]:
    """按季度生成订单事实行，日期在该季度内随机分布"""
    rows = []
    for quarter, months in QUARTER_MONTHS.items():
        # 先枚举该季度所有合法 date_id，供订单随机落日期
        quarter_date_ids = [
            2025 * 10000 + month * 100 + day
            for month, days in months
            for day in range(1, days + 1)
        ]
        for seq in range(1, QUARTER_ORDER_COUNT[quarter] + 1):
            date_id = random.choice(quarter_date_ids)
            product_id = random.choice(ALL_PRODUCT_IDS)
            customer_id = random.choice(CUSTOMER_IDS)
            region_id = random.choice(REGION_IDS)
            quantity = pick_quantity(UNIT_PRICE[product_id])
            amount = round(UNIT_PRICE[product_id] * quantity, 2)
            # 订单号：ORD + 日期 + 季度内序号，保证全局唯一且可读
            order_id = f"ORD{date_id}{seq:03d}"
            rows.append(
                f"('{order_id}', '{customer_id}', '{product_id}', "
                f"{date_id}, '{region_id}', {quantity}, {amount})"
            )
    return rows


def build_sql() -> str:
    """拼装完整的 seed_extra.sql 文本"""
    parts: list[str] = []
    parts.append("-- 由 app/scripts/gen_extra_seed.py 自动生成，请勿手改")
    parts.append("-- 扩充数据：4 新品类商品 + Q2~Q4 日期与订单")
    parts.append("SET NAMES utf8mb4;")
    parts.append("USE dw;")
    parts.append("")

    # 新增商品：REPLACE 保证重复执行不会主键冲突
    product_values = ",\n       ".join(
        f"('{pid}', '{name}', '{cat}', '{brand}')"
        for pid, name, cat, brand, _price in NEW_PRODUCTS
    )
    parts.append(
        "REPLACE INTO dim_product (product_id, product_name, category, brand)\n"
        f"VALUES {product_values};"
    )
    parts.append("")

    # 新增日期维度
    date_values = ",\n       ".join(gen_dim_date_rows())
    parts.append(
        "REPLACE INTO dim_date (date_id, year, quarter, month, day)\n"
        f"VALUES {date_values};"
    )
    parts.append("")

    # 新增订单事实
    order_values = ",\n       ".join(gen_fact_order_rows())
    parts.append(
        "REPLACE INTO fact_order "
        "(order_id, customer_id, product_id, date_id, region_id, order_quantity, order_amount)\n"
        f"VALUES {order_values};"
    )
    parts.append("")
    return "\n".join(parts)


def main():
    sql = build_sql()
    OUTPUT_PATH.write_text(sql, encoding="utf-8")
    order_total = sum(QUARTER_ORDER_COUNT.values())
    print(f"已生成 {OUTPUT_PATH}")
    print(f"  新增商品 {len(NEW_PRODUCTS)} 个（4 品类）")
    print(f"  新增订单 {order_total} 条（Q2={QUARTER_ORDER_COUNT['Q2']} "
          f"Q3={QUARTER_ORDER_COUNT['Q3']} Q4={QUARTER_ORDER_COUNT['Q4']}）")


if __name__ == "__main__":
    main()
