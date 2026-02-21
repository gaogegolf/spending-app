# 个人财务管理器

[![English](https://img.shields.io/badge/lang-English-blue)](README.md)

一个全栈个人财务应用，支持导入银行/信用卡账单，使用AI自动分类交易，并追踪支出和净资产。

**技术栈**: FastAPI + Next.js + SQLAlchemy + Claude AI

## 功能特性

### 账单导入
- **多格式支持**: CSV 和 PDF
- **支持银行**: Chase、Fidelity、Amex、Capital One、Wells Fargo、Ally、Wealthfront、IBKR、Vanguard 401(k)、Equatex/EquatePlus、Schwab
- **未知格式处理**: 使用Claude Vision AI提取未支持的PDF格式
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

### 账户管理
- **账户类型**: 信用卡、活期、储蓄、券商、IRA、401(k)、股票计划、现金、数字钱包
- **账户详情页**: 查看每个账户的导入历史、快照和统计
- **删除导入**: 删除已导入的账单及相关交易

### 交易管理
- **手动录入**: 为现金/数字钱包账户手动添加交易
- **智能筛选**: 按账户、类型、分类、日期
- **备注**: 为交易添加备注
- **待审队列**: 标记需要关注的项目
- **批量操作**: 管理多笔交易

### 商户分类
- **自定义映射**: 保存商户到分类的映射
- **自动应用**: 自动分类未来交易
- **批量管理**: 查看和编辑所有商户映射

### 规则引擎
- **文本匹配**: 按描述关键词分类
- **正则支持**: 高级模式匹配
- **金额范围**: 基于交易金额的规则
- **优先级**: 控制规则执行顺序

### 报表与导出
- **同比分析**: 跨年度支出对比
- **月度对比**: 同月不同年对比
- **支出速度**: 追踪月内支出节奏
- **CSV导出**: 下载交易数据

### 认证与账户
- **用户注册**: 带密码强度指示
- **会话管理**: 查看和撤销登录会话
- **个人设置**: 更新邮箱和用户名
- **修改密码**: 实时强度验证
- **删除账户**: 永久删除账户及所有数据

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
python3 -m venv venv && source venv/bin/activate
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

### 故障排除

**虚拟环境无法工作（bad interpreter 错误）**

如果克隆的仓库中 venv 是在其他机器上创建的，会看到类似错误：
```
bad interpreter: /old/path/to/python: no such file or directory
```
解决方法 - 重新创建虚拟环境：
```bash
cd backend
rm -rf venv
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

**npm install 出现 E401/认证错误**

如果 npm install 出现密码或认证错误，尝试指定公共仓库：
```bash
npm install --registry https://registry.npmjs.org/
```

**使用绝对路径运行服务**

如果不想激活虚拟环境，可以使用绝对路径运行：
```bash
# 后端（从项目根目录）
./backend/venv/bin/uvicorn app.main:app --reload --app-dir ./backend

# 前端（从 frontend 目录）
./node_modules/.bin/next dev -p 3001
```

**缺少 email-validator 或 bcrypt 错误**

如果看到关于缺少 `email-validator` 或 bcrypt 版本问题的错误：
```bash
pip install email-validator 'bcrypt<4.1'
```

**默认登录凭据**

运行数据库迁移后，会创建一个默认用户：
- 邮箱: `default@example.com`
- 密码: `changeme123`

首次登录后建议修改密码或创建新账户。

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
| Wealthfront | PDF | 已支持 |
| Equatex/EquatePlus | PDF | 已支持 |
| Schwab | PDF | 已支持 |
| 任意银行 | CSV | 已支持 |
| 未知银行 | PDF | AI回退* |

*未知PDF格式在模式匹配失败时使用Claude Vision提取。设置 `ENABLE_LLM_PDF_EXTRACTION=false` 可禁用。

## 隐私与安全
- 仅向AI发送日期/描述/金额（无个人信息）
- 默认使用本地SQLite数据库
- 处理完成后删除上传文件
- 完整数据备份和恢复功能

## 许可证
MIT
