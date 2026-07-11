<div align='center'>
  <h1>🧚 DataSprite 问数精灵</h1>
  <h4>NL2SQL 智能数据分析系统</h4>
  <p><em>自然语言提问 → 自动生成 SQL → 流式返回结果</em></p>
</div>

<div align='center'>

![Python](https://img.shields.io/badge/Python-3.12+-3776AB.svg?logo=python&logoColor=white)
![LangGraph](https://img.shields.io/badge/LangGraph-Workflow-1C3C3C.svg)
![FastAPI](https://img.shields.io/badge/FastAPI-Backend-009688.svg?logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/React-19-61DAFB.svg?logo=react&logoColor=black)
![MySQL](https://img.shields.io/badge/MySQL-8.0-4479A1.svg?logo=mysql&logoColor=white)
![Qdrant](https://img.shields.io/badge/Qdrant-Vector_DB-DC244C.svg)
![Elasticsearch](https://img.shields.io/badge/ES-8.x-FEC514.svg?logo=elasticsearch&logoColor=black)

</div>

---

## 📖 项目简介

DataSprite 是一个基于 NL2SQL 的智能问数系统。用户用自然语言提问（如"华北地区上季度 GMV 是多少"），系统自动完成**关键词抽取 → 多路召回 → 上下文组装 → SQL 生成与校验 → 流式返回结果**的全链路处理。

> 💡 基于 [shopkeeper-agent](https://github.com/didilili/shopkeeper-agent) 学习并二次开发

---

## 🏗️ 架构总览

```
用户提问："华北地区上季度GMV"
        │
        ▼
┌─────────────────────────────────────┐
│           LangGraph 工作流            │
│                                      │
│  extract_keywords（关键词抽取）        │
│       │                              │
│       ├── recall_column（Qdrant）     │
│       ├── recall_metric（Qdrant）     │
│       └── recall_value （ES）         │
│       │                              │
│       ▼                              │
│  merge_retrieved_info（合并补全）      │
│       │                              │
│       ├── filter_table（LLM筛选）      │
│       └── filter_metric（LLM筛选）     │
│       │                              │
│       ▼                              │
│  add_extra_context  →  generate_sql  │
│       │                              │
│       ▼                              │
│  validate_sql  →  correct_sql        │
│       │                              │
│       ▼                              │
│  run_sql  →  SSE 流式返回前端         │
└─────────────────────────────────────┘
```

---

## 🛠️ 技术栈

| 类别 | 技术 |
|:---|:---|
| 🧠 大模型 | qwen3.7-max（通义千问） |
| 🔢 Embedding | BGE-large-zh-v1.5（1024维） |
| 🔍 向量检索 | Qdrant（HNSW 索引） |
| 📄 全文检索 | Elasticsearch（IK 中文分词） |
| 🗄️ 数据库 | MySQL 8.0（星型模型：1事实表 + 4维度表） |
| 🔗 工作流 | LangGraph（12节点编排） |
| 🌐 后端 | FastAPI + SSE 流式推送 |
| 🎨 前端 | React 19 + TypeScript + Tailwind CSS |
| 🐳 部署 | Docker Compose |

---

## 🚀 快速启动

### 环境要求

- Python 3.12+
- Docker Desktop
- Node.js 20+ / pnpm

### 1. 启动基础设施

```bash
cd docker
docker compose up -d
# 启动 MySQL + Qdrant + Elasticsearch
```

### 2. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env，填入 LLM_API_KEY
```

### 3. 构建元数据知识库

```bash
pip install -r requirements.txt
python app/scripts/build_meta_knowledge.py
```

### 4. 启动后端

```bash
uvicorn main:app --reload --port 8000
# 访问 http://localhost:8000/docs 查看 API 文档
```

### 5. 启动前端

```bash
cd frontend
pnpm install && pnpm dev
# 访问 http://localhost:5173
```

---

## 📁 项目结构

```
datasprite/
├── app/
│   ├── agent/          # LangGraph 工作流（12个节点 + 图编排）
│   ├── api/            # FastAPI 路由 + 依赖注入
│   ├── clients/        # MySQL/Qdrant/ES 客户端
│   ├── entities/       # 领域实体
│   ├── models/         # 数据模型
│   ├── repositories/   # 数据仓储层
│   ├── services/       # 业务服务层
│   └── scripts/        # 工具脚本
├── conf/               # 配置文件
├── docker/             # Docker Compose + SQL 初始化
├── frontend/           # React 前端
├── prompts/            # LLM 提示词模板
└── main.py             # 应用入口
```

---

## 📝 后续规划

- [ ] SQL 修正循环（correct → re-validate）
- [ ] 多轮对话上下文
- [ ] 可视化图表（折线图/柱状图/饼图）
- [ ] 结果导出 CSV/Excel
- [ ] 查询历史与收藏
- [ ] 前端 UI 重设计

---

## 📄 License

MIT © 2026
