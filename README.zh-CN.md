# 个人财务管理器

[English](README.md)

一个全栈个人财务应用，支持导入银行/信用卡账单，使用AI自动分类交易，并追踪支出和净资产。

**技术栈**: FastAPI + Next.js + SQLAlchemy + Claude AI

## 功能特性

### 账单导入
- **多格式支持**: CSV 和 PDF
- **支持银行**: Chase、Fidelity、Amex、Capital One、Wells Fargo、Ally、IBKR、Vanguard 401(k)
- **智能检测**: 自动识别CSV列格式
- **AI分类**: Claude AI自动分类交易
- **去重**: 基于哈希的重复导入防护

### 净资产追踪
- **银行余额**: 追踪活期/储蓄账户余额
- **券商账户**: 导入投资账单
- **401(k)支持**: Vanguard账单解析
- **多币种**: 支持多种货币

### 分析仪表盘
- **月度统计**: 支出、收入和净额
- **分类明细**: 可视化支出分布
- **日期筛选**: 自定义时间段分析
- **柱状图切换**: 趋势可视化
- **交易分组**: 相似交易合并显示

### 交易管理
- **智能筛选**: 按账户、类型、分类、日期
- **备注**: 为交易添加备注
- **待审队列**: 标记需要关注的项目
- **批量操作**: 管理多笔交易

## 业务逻辑

| 类型 | is_spend | is_income |
|------|----------|-----------|
| 消费 EXPENSE | true | false |
| 收入 INCOME | false | true |
| 还款 PAYMENT | false | false |
| 转账 TRANSFER | false | false |
| 退款 REFUND | false | false |
| 费用/利息 FEE_INTEREST | true | false |

**总支出** = SUM(交易 WHERE is_spend=true)

## 快速开始

### 环境要求
- Python 3.9+
- Node.js 18+
- [Anthropic API Key](https://console.anthropic.com/)

### 后端
```bash
cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # 添加 ANTHROPIC_API_KEY
alembic upgrade head
uvicorn app.main:app --reload
```
后端地址: http://localhost:8000

### 前端
```bash
cd frontend
npm install
npm run dev
```
前端地址: http://localhost:3001

## API文档

完整API文档: http://localhost:8000/docs

## 支持的账单格式

| 银行 | 格式 | 状态 |
|------|------|------|
| Chase 信用卡 | PDF | 已支持 |
| Chase 活期/储蓄 | PDF | 已支持 |
| Fidelity Visa | PDF | 已支持 |
| Fidelity 券商 | PDF | 已支持 |
| American Express | PDF | 已支持 |
| Capital One | PDF | 已支持 |
| Wells Fargo | PDF | 已支持 |
| Ally Bank | PDF | 已支持 |
| 盈透证券 IBKR | PDF | 已支持 |
| Vanguard 401(k) | PDF | 已支持 |
| 任意银行 | CSV | 已支持 |

## 隐私与安全
- 仅向AI发送日期/描述/金额（无个人信息）
- 默认使用本地SQLite数据库
- 处理完成后删除上传文件

## 许可证
MIT
