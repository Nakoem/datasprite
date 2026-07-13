/**
 * Tailwind CSS 主题配置
 * 定义前端项目的字体、颜色和阴影扩展
 */
import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: [
          '"Inter"',
          '"LXGW WenKai Screen"',
          '"Noto Sans SC"',
          '"PingFang SC"',
          '"Microsoft YaHei"',
          "sans-serif",
        ],
        serif: [
          '"Fraunces"',
          '"LXGW WenKai Screen"',
          '"Noto Serif SC"',
          "Georgia",
          "serif",
        ],
        mono: ['"JetBrains Mono"', '"SFMono-Regular"', "Consolas", "monospace"],
      },
      colors: {
        parchment: "#FAF8F4",
        ink: "#14110E",
        soot: "#332F29",
        moss: "#5E7855",
        brass: "#D9806B",
        tomato: "#C55444",
        mist: "#BDCBB5",
      },
      boxShadow: {
        line: "0 1px 0 rgba(20, 17, 14, 0.08)",
        panel: "0 24px 70px rgba(51, 47, 41, 0.16)",
      },
    },
  },
  plugins: [],
} satisfies Config;
