# 表情包管家 Sticker Manager

> 纯本地运行的微信表情包管理工具：自动定位表情文件、格式识别、视觉去重、标签筛选、一键批量导出。

**不联网、不注入微信、只读你的磁盘、绝不写微信目录。**

## 它解决什么问题

- 微信没有任何表情管理功能：攒了几百上千个表情，不能搜索、不能批量导出
- 同一个表情在不同群里反复保存，越攒越多
- 换电脑 / 重装微信时表情包直接丢失
- 想把珍藏的表情拿到 Telegram / QQ 用，没法批量弄出来

## 功能（v0.1）

| 功能 | 说明 |
|---|---|
| 自动定位 | 自动探测微信 3.x / 4.x 表情目录（含用户自选数据盘），失败可手动指定任意文件夹 |
| 格式识别 | 微信表情无扩展名，按文件头（magic bytes）识别 gif/png/jpg/webp/bmp/mp4 |
| 精确去重 | MD5 全量哈希，完全相同的文件秒级聚类 |
| 视觉去重 | 自研 pHash（纯 numpy DCT，无 scipy 依赖）聚类，同图不同压缩/尺寸也算重复 |
| 网格浏览 | 缩略图瀑布流 + 格式/标签筛选 + 搜索 + 勾选批量导出（正确扩展名） |
| 命令行 | `detect` / `scan` / `report` / `export` / `serve` 全功能 CLI |

规划中的功能见 [路线图](#路线图)。

## 合规边界（四不原则）

1. **不注入、不附加**微信进程
2. **不走微信私有协议、不联网**（Web 界面仅绑定 127.0.0.1）
3. 只**读取**用户自己磁盘上的文件，**绝不写微信目录**（导出目的地命中微信目录会被硬性拒绝）
4. 导出目的地由用户指定；工具不提供任何"删除微信文件"的功能

全部代码可审计。索引数据库（`~/.sticker-manager/stickers.db`）只存元数据和哈希。

## 安装

要求 Python 3.11+。

```bash
git clone https://github.com/wangwujie253/sticker-manager.git
cd sticker-manager
pip install -e ".[dev]"        # 安装后得到 sticker-manager 命令

# 可选：构建 Web 界面（不构建也能用 CLI）
cd web && npm install && npm run build && cd ..
```

## 使用

### Web 界面（推荐）

```bash
sticker-manager serve
# 打开 http://127.0.0.1:8765
```

界面里点「扫描（增量）」→ 「重复组」页看聚类结果 → 勾选导出。

### 命令行

```bash
sticker-manager detect                              # 探测微信表情目录
sticker-manager scan                                # 扫描入库（增量，可 --path 手动指定）
sticker-manager report                              # 去重报告（精确/近似分组 + keeper 标记）
sticker-manager export --dest D:\my-stickers --keepers   # 导出每组最优版本
sticker-manager scan --path 任意文件夹 --max-files 100    # 把任何文件夹当表情库扫描（受限抽样）
```

> 本质上这是个"文件夹表情去重器"——不绑死微信路径，Telegram 导出目录、QQ 表情文件夹一样能用。

## 重要：新版微信表情已加密（实测）

2026-10 真机实测（微信 3.x + 4.x 并存）：

- **微信 4.x** 表情存于 `xwechat_files\wxid_*\business\emoticon\`（Persist/Temp/Thumb 哈希分桶），文件内容**已加密**
- **微信 3.x（新版）** `FileStorage\CustomEmotion` 的文件带 `V1MMWX` 私有封装头，**同样已加密**（老版本 3.x 是明文 GIF/PNG）
- 均非单字节 XOR；文件名也不是内容 MD5

因此：加密文件会被如实识别为 `unknown`（不阻塞流程，MD5 精确去重仍可用）；**如果你的微信版本存的是明文格式（较老版本），全部功能开箱即用**。解密格式研究欢迎社区贡献（issues / PR）。

## 架构

```
sticker-manager/
├── app/
│   ├── scanner.py    # 目录探测（规则表 + 微信配置挖掘）+ magic bytes 嗅探
│   ├── phash.py      # pHash 感知哈希（纯 numpy DCT-II）
│   ├── indexer.py    # SQLite 索引：元数据、md5、pHash，增量更新
│   ├── deduper.py    # 精确去重 → 并查集 pHash 聚类 → keeper 标记
│   ├── exporter.py   # 批量导出（含微信目录/源目录安全护栏）
│   └── server.py     # FastAPI 本地 API（仅 127.0.0.1）
├── web/              # Vue3 + Vite 前端
├── rules/paths.json  # 微信目录探测规则表（社区可更新）
└── tests/            # 35 个单元/集成测试（全部合成数据）
```

## 开发

```bash
pip install -e ".[dev]"
pytest                        # 运行测试
cd web && npm run dev         # 前端开发模式（代理到 8765）
```

## 路线图

- [ ] v0.2：点图打标签、备份模式（unknown 加密文件按 .dat 原样导出）、一键导出全部
- [ ] v0.3：本地 CLIP（ONNX）自动中文打标签，完全离线
- [ ] v1.0：watchdog 目录监听增量入库、i18n、PyInstaller 单文件打包
- [ ] 社区：V1MMWX / 4.x 加密格式研究

## License

MIT
