/**
 * fieldLabels 字段中英映射测试
 *
 * 覆盖：已知列名翻译、未知字段原样返回、多系列复合键只翻度量部分。
 */
import { describe, expect, it } from "vitest";
import { columnLabel, COLUMN_LABELS } from "../fieldLabels";

describe("columnLabel", () => {
  it("已知列名翻译成中文", () => {
    expect(columnLabel("product_name")).toBe("商品名称");
    expect(columnLabel("order_amount")).toBe("销售额");
    expect(columnLabel("order_quantity")).toBe("销量");
  });

  it("未知字段原样返回", () => {
    expect(columnLabel("some_unknown_col")).toBe("some_unknown_col");
  });

  it("空字符串原样返回", () => {
    expect(columnLabel("")).toBe("");
  });

  it("多系列复合键只翻度量列部分", () => {
    expect(columnLabel("华东·order_amount")).toBe("华东·销售额");
  });

  it("复合键的度量部分未知时整体原样返回", () => {
    expect(columnLabel("华东·unknown_metric")).toBe("华东·unknown_metric");
  });

  it("COLUMN_LABELS 覆盖核心字段", () => {
    expect(COLUMN_LABELS).toHaveProperty("product_name");
    expect(COLUMN_LABELS).toHaveProperty("order_amount");
  });
});
