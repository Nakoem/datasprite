/**
 * 数据导出工具
 *
 * 将查询结果导出为 CSV 或 Excel 文件并触发浏览器下载。
 * 导出的数据是 normalizeRows() 处理后的原始行数据，
 * 即 SQL 查询结果，不是图表 pivot 后的多系列格式。
 */

import * as XLSX from "xlsx";

type Row = Record<string, unknown>;

/** 生成下载文件名，含时间戳 */
function makeFilename(ext: "csv" | "xlsx") {
  const now = new Date();
  const pad = (n: number) => String(n).padStart(2, "0");
  const ts = `${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}_${pad(now.getHours())}${pad(now.getMinutes())}${pad(now.getSeconds())}`;
  return `datasprite_${ts}.${ext}`;
}

/** 收集所有列名（遍历所有行，因为不同行可能有不同 key） */
function collectColumns(rows: Row[]): string[] {
  const seen = new Set<string>();
  for (const row of rows) {
    for (const key of Object.keys(row)) {
      seen.add(key);
    }
  }
  return [...seen];
}

/** 单元格值转字符串，处理 null / undefined / 对象 */
function cellStr(value: unknown): string {
  if (value === null || value === undefined) return "";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

/** CSV 转义：含逗号、引号或换行的字段用双引号包裹 */
function csvEscape(value: string): string {
  if (value.includes(",") || value.includes('"') || value.includes("\n") || value.includes("\r")) {
    return `"${value.replace(/"/g, '""')}"`;
  }
  return value;
}

/** 触发浏览器文件下载 */
function download(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

// ── 公开 API ──

/**
 * 导出为 CSV 文件（UTF-8 BOM + 逗号分隔，Excel 友好）
 */
export function exportCSV(rows: Row[]) {
  const columns = collectColumns(rows);
  const BOM = "﻿";
  const header = columns.map(csvEscape).join(",");
  const body = rows
    .map((row) => columns.map((col) => csvEscape(cellStr(row[col]))).join(","))
    .join("\n");
  const blob = new Blob([BOM + header + "\n" + body], {
    type: "text/csv;charset=utf-8",
  });
  download(blob, makeFilename("csv"));
}

/**
 * 导出为 Excel (.xlsx) 文件
 */
export function exportExcel(rows: Row[]) {
  const columns = collectColumns(rows);
  const sheetData = rows.map((row) =>
    Object.fromEntries(columns.map((col) => [col, row[col] ?? ""])),
  );
  const ws = XLSX.utils.json_to_sheet(sheetData, { header: columns });
  const wb = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(wb, ws, "查询结果");
  XLSX.writeFile(wb, makeFilename("xlsx"));
}
