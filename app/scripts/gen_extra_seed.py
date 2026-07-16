"""
扩充数仓测试数据生成器 v2

为贴近真实电商场景，在原有基础上补充：
- 客户扩至 200 人（含年龄/城市/注册渠道）
- 商品扩至 50 款（覆盖 10 品类，每品类 ~5 款）
- 日期扩至 2024 全年 + 2025 Q2-Q4 + 2026 H1（912 天）
- 新增供应商/营销活动/库存三张表
- 帕累托销量分布 + 节假日脉冲 + 地区品类偏好 + 促销关联
- ~5600 笔新订单（2024:2400 / 2025:2000 / 2026H1:1200），总计 ~6155 笔

产物写入 docker/mysql/seed_extra.sql，用 REPLACE INTO 保证幂等。
Docker 首次初始化时按字母序在 dw.sql 之后自动加载。

用法（无需数据库连接，纯生成文本）：
    python app/scripts/gen_extra_seed.py
"""

import math
import random
from datetime import date, timedelta
from pathlib import Path

random.seed(20250711)

OUTPUT_PATH = Path(__file__).resolve().parents[2] / "docker" / "mysql" / "seed_extra.sql"

# ═══════════════════════════════════════════════════════════════════
# 常量配置
# ═══════════════════════════════════════════════════════════════════

# --- 商品：单价 + 品类 + 品牌 + 供应商 ---
# (product_id, product_name, category, brand, supplier_id, unit_price, stock_quantity)
EXISTING_PRODUCTS = [
    ("P001", "iPhone 15 Pro", "手机数码", "苹果", "SUP01", 8999.0, 150),
    ("P002", "Galaxy S24 Ultra", "手机数码", "三星", "SUP02", 9499.0, 200),
    ("P003", "Mate 60 Pro", "手机数码", "华为", "SUP03", 6999.0, 120),
    ("P004", "戴森 V15 吸尘器", "家用电器", "戴森", "SUP04", 5499.0, 80),
    ("P005", "美的空调 KFR-35GW", "家用电器", "美的", "SUP04", 3200.0, 100),
    ("P006", "耐克 Air Max 270 运动鞋", "鞋靴", "耐克", "SUP05", 899.0, 300),
    ("P007", "阿迪达斯 Ultraboost 跑鞋", "鞋靴", "阿迪达斯", "SUP05", 1299.0, 250),
    ("P008", "优衣库 Heattech 保暖夹克", "服饰", "优衣库", "SUP06", 199.0, 400),
    ("P009", "李维斯 501 牛仔裤", "服饰", "李维斯", "SUP06", 599.0, 350),
    ("P010", "雀巢金牌速溶咖啡", "食品饮料", "雀巢", "SUP07", 25.0, 800),
    ("P011", "蒙牛纯牛奶 250ml*12", "食品饮料", "蒙牛", "SUP08", 5.0, 600),
    ("P012", "乐事原味薯片 150g", "休闲零食", "乐事", "SUP09", 5.0, 500),
    ("P013", "奥利奥巧克力夹心饼干", "休闲零食", "奥利奥", "SUP10", 3.5, 450),
    ("P014", "Kindle Paperwhite 电子书", "手机数码", "亚马逊", "SUP11", 1399.0, 180),
    ("P015", "Instant Pot 多功能电压力锅", "家用电器", "Instant Pot", "SUP12", 899.0, 90),
    # seed_extra 已有（含 supplier + stock）
    ("P016", "兰蔻小黑瓶精华 30ml", "美妆护肤", "兰蔻", "SUP13", 1080.0, 120),
    ("P017", "雅诗兰黛小棕瓶精华 50ml", "美妆护肤", "雅诗兰黛", "SUP13", 850.0, 100),
    ("P018", "完美日记丝绒哑光口红", "美妆护肤", "完美日记", "SUP13", 99.0, 300),
    ("P019", "花王妙而舒纸尿裤 L码", "母婴用品", "花王", "SUP14", 128.0, 250),
    ("P020", "爱他美卓萃奶粉 3段", "母婴用品", "爱他美", "SUP14", 305.0, 200),
    ("P021", "贝亲宽口径玻璃奶瓶", "母婴用品", "贝亲", "SUP14", 89.0, 280),
    ("P022", "迪卡侬 Quechua 快开帐篷", "运动户外", "迪卡侬", "SUP15", 199.0, 150),
    ("P023", "Keep 天然橡胶瑜伽垫", "运动户外", "Keep", "SUP15", 129.0, 200),
    ("P024", "始祖鸟 Beta 冲锋衣", "运动户外", "始祖鸟", "SUP15", 4500.0, 60),
    ("P025", "《三体》全集三册", "图书文具", "读客", "SUP16", 168.0, 350),
    ("P026", "晨光优品中性笔 12支装", "图书文具", "晨光", "SUP16", 24.0, 500),
    ("P027", "得力多功能订书机", "图书文具", "得力", "SUP16", 35.0, 400),
]

# 新增 23 款商品（P028-P050），补齐每品类 ~5 款
NEW_PRODUCTS = [
    ("P028", "小米 14 Pro", "手机数码", "小米", "SUP03", 4999.0, 130),
    ("P029", "OPPO Find X7 Ultra", "手机数码", "OPPO", "SUP03", 5999.0, 100),
    ("P030", "戴森 Airwrap 多功能美发器", "家用电器", "戴森", "SUP04", 3999.0, 70),
    ("P031", "九阳全自动破壁机", "家用电器", "九阳", "SUP04", 599.0, 150),
    ("P032", "新百伦 574 经典复古鞋", "鞋靴", "新百伦", "SUP05", 699.0, 200),
    ("P033", "匡威 Chuck Taylor 高帮帆布鞋", "鞋靴", "匡威", "SUP05", 399.0, 220),
    ("P034", "安踏 C37 软底跑鞋", "鞋靴", "安踏", "SUP05", 399.0, 250),
    ("P035", "ZARA 基础款白衬衫", "服饰", "ZARA", "SUP06", 259.0, 300),
    ("P036", "H&M 纯棉圆领T恤", "服饰", "H&M", "SUP06", 79.0, 500),
    ("P037", "波司登轻薄羽绒服", "服饰", "波司登", "SUP06", 899.0, 150),
    ("P038", "星巴克哥伦比亚咖啡豆 250g", "食品饮料", "星巴克", "SUP07", 128.0, 300),
    ("P039", "农夫山泉矿泉水 550ml*24", "食品饮料", "农夫山泉", "SUP07", 48.0, 1000),
    ("P040", "良品铺子坚果礼盒 1.5kg", "休闲零食", "良品铺子", "SUP09", 149.0, 200),
    ("P041", "三只松鼠每日坚果 750g", "休闲零食", "三只松鼠", "SUP09", 99.0, 250),
    ("P042", "SK-II 神仙水 230ml", "美妆护肤", "SK-II", "SUP13", 1370.0, 80),
    ("P043", "花西子空气蜜粉", "美妆护肤", "花西子", "SUP13", 169.0, 180),
    ("P044", "帮宝适超薄干爽纸尿裤 M码", "母婴用品", "帮宝适", "SUP14", 109.0, 200),
    ("P045", "合生元益生菌粉 48袋", "母婴用品", "合生元", "SUP14", 259.0, 150),
    ("P046", "始祖鸟 Gamma 软壳夹克", "运动户外", "始祖鸟", "SUP15", 3200.0, 50),
    ("P047", "小米手环 8 Pro", "运动户外", "小米", "SUP15", 399.0, 200),
    ("P048", "故宫日历 2025", "图书文具", "故宫出版社", "SUP16", 88.0, 300),
    ("P049", "万宝龙大班系列钢笔", "图书文具", "万宝龙", "SUP16", 3200.0, 60),
    ("P050", "LEGO 机械组 42143 法拉利", "图书文具", "乐高", "SUP16", 3499.0, 40),
]

ALL_PRODUCTS = EXISTING_PRODUCTS + NEW_PRODUCTS
ALL_PRODUCT_IDS = [p[0] for p in ALL_PRODUCTS]
UNIT_PRICE = {p[0]: p[5] for p in ALL_PRODUCTS}
PRODUCT_CATEGORY = {p[0]: p[2] for p in ALL_PRODUCTS}

# --- 帕累托销量权重（80% 销量来自前 10 款爆品）---
PRODUCT_WEIGHTS = {}
for pid in ALL_PRODUCT_IDS:
    p = [x for x in ALL_PRODUCTS if x[0] == pid][0]
    price = p[5]
    cat = p[2]
    if pid in ("P001", "P010", "P011", "P012", "P013", "P018"):
        PRODUCT_WEIGHTS[pid] = 12.0  # 爆品
    elif pid in ("P003", "P005", "P008", "P016", "P026"):
        PRODUCT_WEIGHTS[pid] = 6.0   # 热销
    elif pid in ("P006", "P009", "P017", "P021", "P023", "P027", "P034", "P036", "P039"):
        PRODUCT_WEIGHTS[pid] = 3.0   # 常销
    elif price >= 3000:
        PRODUCT_WEIGHTS[pid] = 1.0   # 高端低频
    elif price <= 50:
        PRODUCT_WEIGHTS[pid] = 4.0   # 低价高频
    else:
        PRODUCT_WEIGHTS[pid] = 2.0   # 中等

# --- 维度参数 ---
REGION_IDS = ["R001", "R002", "R003", "R004", "R005", "R006"]
MEMBER_LEVELS = ["青铜", "白银", "黄金", "铂金"]
MEMBER_WEIGHTS = [40, 30, 20, 10]
CHANNELS = ["微信", "抖音", "淘宝", "京东", "小红书"]
CHANNEL_WEIGHTS = [35, 25, 20, 12, 8]

# 城市池（按地区分组）
REGION_CITIES = {
    "R001": ["广州市", "深圳市", "东莞市", "佛山市", "珠海市", "惠州市"],
    "R002": ["杭州市", "宁波市", "温州市", "嘉兴市", "绍兴市", "金华市"],
    "R003": ["成都市", "绵阳市", "德阳市", "宜宾市", "南充市", "泸州市"],
    "R004": ["北京市", "天津市", "石家庄市", "太原市", "呼和浩特市"],
    "R005": ["上海市", "南京市", "苏州市", "无锡市", "常州市", "南通市"],
    "R006": ["武汉市", "长沙市", "郑州市", "合肥市", "南昌市", "宜昌市"],
}

# 地区品类偏好乘数
REGION_CATEGORY_BOOST = {
    "R001": {"美妆护肤": 2.0, "手机数码": 1.5},
    "R002": {"服饰": 1.8, "食品饮料": 1.5},
    "R003": {"休闲零食": 1.6, "图书文具": 1.4},
    "R004": {"运动户外": 1.8, "家用电器": 1.5},
    "R005": {"服饰": 2.0, "美妆护肤": 1.5, "手机数码": 1.4},
    "R006": {"母婴用品": 2.0, "食品饮料": 1.4},
}

# 仓库位置
WAREHOUSES = ["华南仓", "华东仓", "西南仓", "华北仓", "华中仓", "西北仓"]

# 姓名池
SURNAMES = [
    "李", "王", "张", "刘", "陈", "杨", "赵", "黄", "周", "吴",
    "徐", "孙", "胡", "朱", "高", "林", "何", "郭", "马", "罗",
    "梁", "宋", "郑", "谢", "韩", "唐", "冯", "于", "董", "萧",
    "程", "曹", "袁", "邓", "许", "傅", "沈", "曾", "彭", "吕",
    "苏", "卢", "蒋", "蔡", "贾", "丁", "魏", "薛", "叶", "阎",
]
MALE_GIVEN = [
    "伟", "强", "磊", "涛", "斌", "勇", "军", "杰", "峰", "浩",
    "建国", "志强", "建华", "文博", "宇轩", "浩然", "铭泽",
    "子涵", "泽宇", "鹏飞", "逸飞", "俊杰", "明哲", "瑞霖",
]
FEMALE_GIVEN = [
    "芳", "敏", "静", "丽", "婷", "雪", "玲", "燕", "娜", "慧",
    "秀英", "美玲", "雅琴", "诗涵", "欣怡", "雨桐", "梓涵",
    "一诺", "梓萱", "若曦", "思雨", "梦瑶", "语嫣", "瑾瑜",
]

# 原有 20 客户姓名（C001-C020），保持兼容
EXISTING_CUSTOMERS = {
    "C001": ("李伟", "男", "黄金", 32, "广州市", "微信"),
    "C002": ("王芳", "女", "白银", 28, "杭州市", "抖音"),
    "C003": ("张敏", "女", "黄金", 35, "成都市", "淘宝"),
    "C004": ("刘洋", "男", "青铜", 22, "北京市", "京东"),
    "C005": ("陈静", "女", "铂金", 40, "上海市", "微信"),
    "C006": ("赵磊", "男", "白银", 30, "杭州市", "小红书"),
    "C007": ("黄秀英", "女", "青铜", 55, "武汉市", "微信"),
    "C008": ("吴斌", "男", "黄金", 45, "北京市", "淘宝"),
    "C009": ("周燕", "女", "铂金", 38, "上海市", "微信"),
    "C010": ("徐浩", "男", "白银", 26, "杭州市", "抖音"),
    "C011": ("孙丽", "女", "黄金", 33, "广州市", "淘宝"),
    "C012": ("马强", "男", "青铜", 24, "成都市", "京东"),
    "C013": ("朱玲", "女", "白银", 29, "杭州市", "小红书"),
    "C014": ("胡杰", "男", "黄金", 42, "广州市", "微信"),
    "C015": ("高梅", "女", "铂金", 36, "上海市", "淘宝"),
    "C016": ("林峰", "男", "青铜", 21, "北京市", "抖音"),
    "C017": ("何娜", "女", "白银", 27, "武汉市", "京东"),
    "C018": ("郭涛", "男", "黄金", 48, "北京市", "微信"),
    "C019": ("邓慧", "女", "青铜", 50, "成都市", "淘宝"),
    "C020": ("曹瑞", "男", "铂金", 39, "上海市", "微信"),
}

# 促销配置：(promotion_id, name, type, discount_rate, min_amount, start, end)
PROMOTION_TEMPLATES = [
    ("PROM{YY}01", "年货节满300减50", "满减", 0.00, 300.00, "0115", "0205"),
    ("PROM{YY}02", "情人节美妆秒杀", "秒杀", 0.40, 0, "0214", "0214"),
    ("PROM{YY}03", "三八女神节美妆9折", "折扣", 0.10, 0, "0301", "0308"),
    ("PROM{YY}04", "春季焕新运动户外85折", "折扣", 0.15, 0, "0315", "0415"),
    ("PROM{YY}05", "吃货节零食满99减20", "满减", 0.00, 99.00, "0501", "0515"),
    ("PROM{YY}06", "五一假期消费券", "优惠券", 0.10, 0, "0501", "0505"),
    ("PROM{YY}07", "六一儿童节母婴满200减40", "满减", 0.00, 200.00, "0525", "0603"),
    ("PROM{YY}08", "618母婴品类满减", "满减", 0.00, 400.00, "0601", "0618"),
    ("PROM{YY}09", "618全场8折", "折扣", 0.20, 0, "0601", "0618"),
    ("PROM{YY}10", "清凉一夏饮料满50减10", "满减", 0.00, 50.00, "0701", "0731"),
    ("PROM{YY}11", "七夕情人节美妆秒杀", "秒杀", 0.40, 0, "0810", "0810"),
    ("PROM{YY}12", "开学季图书文具满200减30", "满减", 0.00, 200.00, "0825", "0915"),
    ("PROM{YY}13", "国庆黄金周消费券", "优惠券", 0.15, 100.00, "1001", "1007"),
    ("PROM{YY}14", "双11预售定金膨胀", "折扣", 0.30, 0, "1020", "1110"),
    ("PROM{YY}15", "双11狂欢秒杀", "秒杀", 0.50, 0, "1111", "1111"),
    ("PROM{YY}16", "双12满500减100", "满减", 0.00, 500.00, "1210", "1212"),
    ("PROM{YY}17", "年终大促家电满1000减150", "满减", 0.00, 1000.00, "1220", "1231"),
]

# 节假日销售脉冲：(start, end) → multiplier
SPIKE_DEFS = {
    2024: [
        ((20240115, 20240205), 2.0),   # 年货节
        ((20240214, 20240214), 1.5),   # 情人节
        ((20240301, 20240308), 1.3),   # 三八
        ((20240501, 20240505), 1.3),   # 五一
        ((20240601, 20240618), 2.5),   # 618
        ((20240810, 20240810), 1.3),   # 七夕
        ((20241001, 20241007), 1.4),   # 国庆
        ((20241020, 20241111), 3.0),   # 双11
        ((20241210, 20241212), 2.0),   # 双12
        ((20241220, 20241231), 1.5),   # 年终
    ],
    2025: [
        ((20250115, 20250205), 2.0),
        ((20250214, 20250214), 1.5),
        ((20250301, 20250308), 1.3),
        ((20250501, 20250505), 1.3),
        ((20250601, 20250618), 2.5),
        ((20250810, 20250810), 1.3),
        ((20251001, 20251007), 1.4),
        ((20251020, 20251111), 3.0),
        ((20251210, 20251212), 2.0),
        ((20251220, 20251231), 1.5),
    ],
    2026: [
        ((20260115, 20260205), 2.0),
        ((20260214, 20260214), 1.5),
        ((20260301, 20260308), 1.3),
        ((20260501, 20260505), 1.3),
        ((20260601, 20260618), 2.5),
    ],
}

# 订单量目标
ORDERS_PER_YEAR = {2024: 2400, 2025: 2000, 2026: 1200}

# 全局序号，保证 order_id 唯一
_global_seq = [0]


# ═══════════════════════════════════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════════════════════════════════

def next_order_id(date_id: int) -> str:
    _global_seq[0] += 1
    return f"ORD{date_id}{_global_seq[0]:05d}"


def is_leap(year: int) -> bool:
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)


def day_of_week(date_id: int) -> int:
    """返回 0=周一 ... 6=周日"""
    y, m, d = date_id // 10000, (date_id % 10000) // 100, date_id % 100
    dt = date(y, m, d)
    return dt.weekday()


def pick_quantity(unit_price: float) -> int:
    if unit_price >= 3000:
        return random.choices([1, 2], weights=[90, 10])[0]
    if unit_price >= 1000:
        return random.choices([1, 2], weights=[80, 20])[0]
    if unit_price >= 100:
        return random.choices([1, 2, 3], weights=[55, 30, 15])[0]
    return random.randint(5, 30)


# ═══════════════════════════════════════════════════════════════════
# 生成函数
# ═══════════════════════════════════════════════════════════════════

def gen_customer_rows() -> list[str]:
    """生成 200 客户（C001-C020 保留原有，C021-C200 随机生成）"""
    rows = []
    for i in range(1, 201):
        cid = f"C{i:03d}"
        if cid in EXISTING_CUSTOMERS:
            name, gender, level, age, city, channel = EXISTING_CUSTOMERS[cid]
        else:
            gender = random.choice(["男", "女"])
            surname = random.choice(SURNAMES)
            given = random.choice(MALE_GIVEN if gender == "男" else FEMALE_GIVEN)
            name = surname + given
            age = int(random.gauss(34, 12))
            age = max(18, min(65, age))
            region = random.choice(REGION_IDS)
            city = random.choice(REGION_CITIES[region])
            channel = random.choices(CHANNELS, weights=CHANNEL_WEIGHTS)[0]
            # 会员等级：年龄大倾向高等级
            if age >= 45:
                level = random.choices(MEMBER_LEVELS, weights=[20, 25, 30, 25])[0]
            elif age >= 30:
                level = random.choices(MEMBER_LEVELS, weights=[35, 30, 25, 10])[0]
            else:
                level = random.choices(MEMBER_LEVELS, weights=[50, 30, 15, 5])[0]
        rows.append(
            f"('{cid}', '{name}', '{gender}', '{level}', {age}, '{city}', '{channel}')"
        )
    return rows


def gen_product_rows() -> list[str]:
    """生成全部 50 商品 REPLACE INTO 行"""
    rows = []
    for pid, name, cat, brand, sid, price, stock in ALL_PRODUCTS:
        rows.append(
            f"('{pid}', '{name}', '{cat}', '{brand}', '{sid}', {stock})"
        )
    return rows


def gen_dim_date_rows() -> list[str]:
    """生成 2024 Q1-Q4 + 2025 Q2-Q4 + 2026 Q1-Q2 日期行"""
    rows = []
    quarters = {
        "Q1": [(1, 31), (2, 28), (3, 31)],
        "Q2": [(4, 30), (5, 31), (6, 30)],
        "Q3": [(7, 31), (8, 31), (9, 30)],
        "Q4": [(10, 31), (11, 30), (12, 31)],
    }

    for year in [2024, 2025, 2026]:
        qs = list(quarters.keys()) if year in (2024, 2026) else ["Q2", "Q3", "Q4"]
        for q in qs:
            for month, days in quarters[q]:
                feb_days = 29 if is_leap(year) else 28
                actual = feb_days if month == 2 else days
                # 2026 只到 Q2
                if year == 2026 and month > 6:
                    continue
                for day in range(1, actual + 1):
                    date_id = year * 10000 + month * 100 + day
                    rows.append(f"({date_id}, {year}, '{q}', {month}, {day})")
    return rows


def gen_promotion_rows() -> list[str]:
    """生成 2024/2025/2026 活动（dw.sql 已有 INSERT，这里用 REPLACE 做幂等）"""
    rows = []
    for tmpl in PROMOTION_TEMPLATES:
        pid_tmpl, name, ptype, rate, min_amt, start_md, end_md = tmpl
        for yy in [24, 25, 26]:
            year = 2000 + yy
            if year == 2026:
                # 2026 H1 只到 618，跳过下半年活动
                if int(start_md[:2]) > 6:
                    continue
            pid = pid_tmpl.replace("{YY}", f"{yy}")
            start_id = int(f"{year}{start_md}")
            end_id = int(f"{year}{end_md}")
            display_name = f"{year} {name}"
            rows.append(
                f"('{pid}', '{display_name}', '{ptype}', {rate:.2f}, "
                f"{min_amt:.2f}, {start_id}, {end_id})"
            )
    return rows


def gen_supplier_rows() -> list[str]:
    """生成 16 供应商 REPLACE INTO 行（dw.sql 已有 INSERT）"""
    suppliers = [
        ("SUP01", "苹果中国供应链有限公司", "陈明", "深圳市", 5, 10),
        ("SUP02", "三星电子中国采购中心", "金秀贤", "苏州市", 5, 8),
        ("SUP03", "华为终端供应链管理公司", "任正凡", "东莞市", 5, 12),
        ("SUP04", "高端家电供应集团", "方洪波", "佛山市", 4, 15),
        ("SUP05", "运动品牌供应联盟", "张伟强", "上海市", 5, 15),
        ("SUP06", "快时尚服饰供应链", "刘文辉", "广州市", 3, 5),
        ("SUP07", "雀巢中国供应链公司", "王德明", "北京市", 4, 18),
        ("SUP08", "蒙牛乳业供应链公司", "卢敏放", "呼和浩特市", 4, 10),
        ("SUP09", "百事食品中国供应链", "陈志华", "上海市", 4, 12),
        ("SUP10", "亿滋中国供应链公司", "范思哲", "北京市", 4, 15),
        ("SUP11", "亚马逊中国供应链", "张艾瑞", "深圳市", 4, 8),
        ("SUP12", "Instant Pot供应链公司", "李建国", "杭州市", 3, 6),
        ("SUP13", "欧莱雅中国供应链", "周雅琴", "上海市", 5, 20),
        ("SUP14", "母婴用品供应联盟", "林晓芳", "杭州市", 4, 7),
        ("SUP15", "运动户外供应链", "马建国", "北京市", 4, 9),
        ("SUP16", "图书文具供应集团", "孙文杰", "上海市", 3, 6),
    ]
    return [
        f"('{sid}', '{name}', '{contact}', '{city}', {rating}, {years})"
        for sid, name, contact, city, rating, years in suppliers
    ]


def gen_inventory_rows() -> list[str]:
    """生成月度库存快照（每月1号 × 50商品）"""
    rows = []
    for year in [2024, 2025, 2026]:
        end_month = 13 if year < 2026 else 7  # 2026 只到 6 月
        for month in range(1, end_month):
            date_id = year * 10000 + month * 100 + 1
            for pid, name, cat, brand, sid, price, stock in ALL_PRODUCTS:
                unit_cost = round(price * random.uniform(0.40, 0.70), 2)
                qty = int(random.gauss(stock, stock * 0.3))
                qty = max(10, min(stock * 2, qty))
                warehouse = random.choice(WAREHOUSES)
                inv_id = f"INV{date_id}{pid}"
                rows.append(
                    f"('{inv_id}', '{pid}', '{sid}', {date_id}, "
                    f"{qty}, {unit_cost}, '{warehouse}')"
                )
    return rows


def gen_fact_order_rows() -> list[str]:
    """核心：按年生成订单，融入帕累托/脉冲/偏好/促销逻辑"""
    rows = []
    # 收集所有 date_id
    all_date_ids = []
    for row in gen_dim_date_rows():
        date_id = int(row.split(",")[0].strip("()"))
        all_date_ids.append(date_id)

    date_set = set(all_date_ids)

    # 构建促销索引 {date_id: [promotions]}
    promo_by_date: dict[int, list[tuple]] = {}
    for tmpl in PROMOTION_TEMPLATES:
        pid_tmpl, name, ptype, rate, min_amt, start_md, end_md = tmpl
        for yy in [24, 25, 26]:
            year = 2000 + yy
            if year == 2026 and int(start_md[:2]) > 6:
                continue
            pid = pid_tmpl.replace("{YY}", f"{yy}")
            start_id = int(f"{year}{start_md}")
            end_id = int(f"{year}{end_md}")
            display_name = f"{year} {name}"
            for d in date_set:
                if start_id <= d <= end_id and str(d)[:4] == str(year):
                    promo_by_date.setdefault(d, []).append(
                        (pid, display_name, ptype, rate, min_amt)
                    )

    # 构建客户 ID 列表（C001-C200）
    all_customers = [f"C{i:03d}" for i in range(1, 201)]

    for year, target_orders in ORDERS_PER_YEAR.items():
        year_dates = sorted(d for d in all_date_ids if str(d)[:4] == str(year))
        if not year_dates:
            continue

        # 计算每天的基准订单数（按脉冲调整）
        daily_base = target_orders / len(year_dates)
        spikes = SPIKE_DEFS.get(year, [])
        day_multipliers = {}
        for d in year_dates:
            mult = 1.0
            # 节假日脉冲
            for (sp_start, sp_end), sp_mult in spikes:
                if sp_start <= d <= sp_end:
                    mult = max(mult, sp_mult)
            # 周末脉冲
            dow = day_of_week(d)
            if dow >= 5:  # 周六日
                mult = max(mult, 1.3)
            day_multipliers[d] = mult

        # 按天分配订单数
        total_weight = sum(day_multipliers.values())
        for d in year_dates:
            expected = target_orders * (day_multipliers[d] / total_weight)
            # 泊松采样 (Knuth's algorithm)
            if expected > 0:
                L = math.exp(-expected)
                k = 0
                p = 1.0
                while p > L:
                    k += 1
                    p *= random.random()
                n = max(1, min(k, 20))  # 每天 1-20 单
            else:
                n = 1

            for _ in range(n):
                # 选商品（帕累托）
                pid = random.choices(
                    list(PRODUCT_WEIGHTS.keys()),
                    weights=list(PRODUCT_WEIGHTS.values()),
                )[0]
                # 选地区（有品类偏好）
                cat = PRODUCT_CATEGORY[pid]
                region_weights = []
                for rid in REGION_IDS:
                    w = 1.0
                    if rid in REGION_CATEGORY_BOOST and cat in REGION_CATEGORY_BOOST[rid]:
                        w *= REGION_CATEGORY_BOOST[rid][cat]
                    region_weights.append(w)
                region_id = random.choices(REGION_IDS, weights=region_weights)[0]
                # 选客户
                customer_id = random.choice(all_customers)
                # 计算数量和金额
                price = UNIT_PRICE[pid]
                quantity = pick_quantity(price)
                amount = round(price * quantity, 2)
                # 促销关联
                promo_id = "NULL"
                promos_today = promo_by_date.get(d, [])
                if promos_today:
                    # 大促日 60-70%，日常 35%
                    is_mega = any(p[1] for p in promos_today if "双11" in p[1] or "618" in p[1])
                    link_rate = 0.65 if is_mega else 0.35
                    if random.random() < link_rate:
                        promo = random.choice(promos_today)
                        promo_id = f"'{promo[0]}'"
                # 组装
                rows.append(
                    f"('{next_order_id(d)}', '{customer_id}', '{pid}', "
                    f"{d}, '{region_id}', {promo_id}, {quantity}, {amount})"
                )
    return rows


# ═══════════════════════════════════════════════════════════════════
# 组装 SQL
# ═══════════════════════════════════════════════════════════════════

def build_sql() -> str:
    parts: list[str] = []
    h = "-- 由 app/scripts/gen_extra_seed.py v2 自动生成，请勿手改"
    parts.append(h)
    parts.append("-- 扩充：200客户 + 50商品 + 912天 + 供应商/活动/库存 + ~5600订单（泊松采样）")
    parts.append("SET NAMES utf8mb4;")
    parts.append("USE dw;")
    parts.append("")

    # 客户
    parts.append("REPLACE INTO dim_customer (customer_id, customer_name, gender, member_level, age, city, register_channel)")
    parts.append("VALUES\n       " + ",\n       ".join(gen_customer_rows()) + ";")
    parts.append("")

    # 商品
    parts.append("REPLACE INTO dim_product (product_id, product_name, category, brand, supplier_id, stock_quantity)")
    parts.append("VALUES\n       " + ",\n       ".join(gen_product_rows()) + ";")
    parts.append("")

    # 日期
    parts.append("REPLACE INTO dim_date (date_id, year, quarter, month, day)")
    parts.append("VALUES\n       " + ",\n       ".join(gen_dim_date_rows()) + ";")
    parts.append("")

    # 供应商
    parts.append("REPLACE INTO dim_supplier (supplier_id, supplier_name, contact_person, supplier_city, rating, cooperation_years)")
    parts.append("VALUES\n       " + ",\n       ".join(gen_supplier_rows()) + ";")
    parts.append("")

    # 活动
    parts.append("REPLACE INTO dim_promotion (promotion_id, promotion_name, promotion_type, discount_rate, min_amount, start_date_id, end_date_id)")
    parts.append("VALUES\n       " + ",\n       ".join(gen_promotion_rows()) + ";")
    parts.append("")

    # 库存
    parts.append("REPLACE INTO fact_inventory (inventory_id, product_id, supplier_id, date_id, stock_quantity, unit_cost, warehouse_location)")
    parts.append("VALUES\n       " + ",\n       ".join(gen_inventory_rows()) + ";")
    parts.append("")

    # 订单（最大段）
    order_rows = gen_fact_order_rows()
    parts.append("REPLACE INTO fact_order (order_id, customer_id, product_id, date_id, region_id, promotion_id, order_quantity, order_amount)")
    parts.append("VALUES\n       " + ",\n       ".join(order_rows) + ";")
    parts.append("")

    return "\n".join(parts)


def main():
    sql = build_sql()
    OUTPUT_PATH.write_text(sql, encoding="utf-8")
    print(f"已生成 {OUTPUT_PATH}")
    print(f"  客户: 200 人")
    print(f"  商品: {len(ALL_PRODUCTS)} 款（{len(NEW_PRODUCTS)} 新增）")
    print(f"  供应商: 16 家")
    print(f"  活动: 17 × 3年（2026仅H1）= ~42 个")
    total_target = sum(ORDERS_PER_YEAR.values())
    print(f"  目标订单: ~{total_target} 笔（2024:{ORDERS_PER_YEAR[2024]} 2025:{ORDERS_PER_YEAR[2025]} 2026H1:{ORDERS_PER_YEAR[2026]}），实际受泊松采样波动")


if __name__ == "__main__":
    main()
