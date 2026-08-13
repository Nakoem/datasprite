/**
 * 查询结果字段名 → 中文标签映射
 *
 * 数据库列名（如 product_name）直接展示给用户不友好，
 * 渲染表格表头 / 图表标题时统一翻译成中文。
 * 映射来源：后端 conf/meta_config.yaml 中表的列定义与 alias。
 * 未知字段原样返回。
 */

export const COLUMN_LABELS: Record<string, string> = {
  // dim_product 商品
  product_name: "商品名称",
  category: "品类",
  brand: "品牌",
  stock_quantity: "库存量",

  // dim_region 地区
  province: "省份",
  region_name: "大区",
  country: "国家",

  // dim_customer 客户
  customer_name: "客户名称",
  gender: "性别",
  member_level: "会员等级",
  age: "年龄",
  city: "城市",
  register_channel: "注册渠道",

  // dim_date 时间
  year: "年份",
  quarter: "季度",
  month: "月份",
  day: "日",

  // fact_order 订单
  order_amount: "销售额",
  order_quantity: "销量",

  // dim_promotion 活动
  promotion_name: "活动名称",
  promotion_type: "活动类型",
  discount_rate: "折扣率",
  min_amount: "最低金额",

  // dim_supplier 供应商
  supplier_name: "供应商名称",
  contact_person: "联系人",
  supplier_city: "供应商城市",
  rating: "评级",
  cooperation_years: "合作年限",

  // fact_inventory 库存
  unit_cost: "单位成本",
  warehouse_location: "仓库位置",

  // 指标
  GMV: "成交总额",
  AOV: "平均订单金额",
  promotion_GMV: "活动GMV",
  promotion_order_count: "活动订单数",
  discount_amount: "折扣金额",
  inventory_value: "库存货值",
  stock_turnover_rate: "库存周转率",
  repurchase_rate: "复购率",
};

/** 字段名 → 中文标签，未知字段原样返回 */
export function columnLabel(name: string): string {
  // 多系列复合键：`系列值·度量列`（如 "华东·order_amount"）→ 只翻度量列部分
  const idx = name.indexOf("·");
  if (idx !== -1) {
    const head = name.slice(0, idx);
    const tail = name.slice(idx + 1);
    return `${head}·${COLUMN_LABELS[tail] ?? tail}`;
  }
  return COLUMN_LABELS[name] ?? name;
}
