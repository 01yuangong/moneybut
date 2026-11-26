副业雷达 · 每天 3 分钟精选全网搞钱动作：https://afdian.com/a/sidehustleradar

# 副业雷达 SideHustle Radar — 全自动情报简报生产线

一条命令，把全网公开的「副业 / 独立开发 / 自动化赚钱」信息变成：
**一个可付费订阅的每日简报网站 + 一份可复制到公众号/小红书的文案 + 一个收录需求的流量入口。**

- 代码量：约 1,400 行 Python，**零第三方依赖**（全标准库），1 核 1G 服务器内存占用 < 60MB
- 成本：**0 元**就能上线（Cloudflare Pages + GitHub Actions 免费额度）；要自己服务器也就 30–50 元
- 合法性：只抓**公开 RSS / 公开 API**，只做**摘要 + 原文跳转**，不转载全文、不破解、不登录、不刷量

---

## 1. 为什么选它（而不是"搬运爆款视频"）

| 项目 | 需要出镜/剪辑 | 平台封号风险 | 边际成本 | 变现路径 | 自动化程度 |
|---|---|---|---|---|---|
| 搬运短视频矩阵 | 要 | **极高**（搬运侵权） | 低 | 带货/流量分成 | 中，但要人盯 |
| 撸免费 API 套利 | 不要 | 高（违反 ToS） | 低 | 差价 | 高，但随时被掐 |
| 资源站卖盗版资料 | 不要 | **违法**（著作权） | 低 | 单卖 | 高，但会出事 |
| **本方案：公开信息聚合 + 付费简报** | 不要 | 低（合规引用） | ~0 | 订阅 + 广告位 + 联盟 | **全自动** |

老板不动手，那就必须选一个 **"内容由别人的公开信息提供、价值由筛选和排序提供"** 的活儿——
因为筛选算法可以写成代码，而剪辑和出镜不行。

---

## 2. 运行逻辑（一条流水线，5 步）

```
                 ┌──────────────────────────────────────────┐
 每 24h 定时触发  │  main.py run                             │
                 └──────────────────────────────────────────┘
   ① 采集 sources.py   Hacker News / Reddit(r/SideProject,r/indiehackers)
                       / GitHub 新星 / 少数派 RSS / V2EX RSS
                       ——只读公开接口，单源失败不影响整体
                                  ↓
   ② 打分 score.py     score = 源权重 × log(1+热度) × 时间半衰期衰减 × (1+关键词加成)
                       关键词命中「AI / 自动化 / 独立开发 / MRR / 出海…」加权
                       命中「招聘 / 求职」直接判 0 分过滤
                                  ↓
   ③ 去重              三重去重：URL 规范化哈希 → 标题 Jaccard 相似度 > 0.72 → SQLite 历史库
                       （同一条新闻在 HN 和 Reddit 都出现，只会留一条）
                                  ↓
   ④ 分层渲染 render.py 免费 4 条（引流）+ 付费 14 条（变现）+ 付费墙 + 广告位
                       同时产出：HTML 站 / RSS / JSON API / 公众号 Markdown 稿
                                  ↓
   ⑤ 发布 publish.py   site/index.html、往期存档、feed.xml、sitemap.xml、
                       /paid/issue-XXXX-<hash>.html（不可猜路径，手动发给付费用户）、
                       /go/a0.html（广告位跳转，静态托管也能记点击）
                                  ↓
   ⑥ 服务 serve.py     /go/*   302 跳广告位 + 记点击
                       /api/subscribe  收邮箱，发订阅 token
                       /p/<token>      付费用户专属入口（自动跳到最新完整版）
                       /api/stats      后台数据（要 ADMIN_TOKEN）
```

**钱从哪来（三层，互相不冲突）：**

1. **订阅**：免费 4 条，完整版 14 条，￥9.9/月。收款用爱发电/面包多，**不用自己接支付**（省掉支付资质这个坎）。
2. **广告位**：站长/服务器/AI API 的联盟链接，每周轮换，点击进 SQLite，直接看哪条转化。
3. **流量复用**：`site/digest/issue-XXXX.md` 是排版好的中文稿，直接贴公众号、小红书、即刻、V2EX——
   一个内容源，四个渠道，零额外成本。免费工具页拿 SEO 长尾流量，再导向订阅。

---

## 3. 命令清单

```bash
cd moneybot

# 跑一期（联网，真实数据）
python3 main.py run --base-url https://your-domain.com

# 离线跑（不联网，用内置样本，测试/演示用）
python3 main.py run --offline

# 看后台数据：条目 / 期数 / 订阅 / 付费 / 点击 / 收入
python3 main.py stats

# 加一个付费订阅者，拿到专属链接
python3 main.py subscribe boss@example.com --paid --base-url https://your-domain.com

# 记一笔收入（对账用）
python3 main.py revenue 9.9 --kind subscription --note "第3个订阅"

# 起服务（开发机预览）
python3 serve.py --port 8080 --root site

# 全套测试（27 个用例，含付费墙泄露检测）
python3 -m unittest discover -s tests -v
```

产出目录：
```
site/index.html                     最新一期首页
site/issues/issue-0001.html         往期存档（SEO 长尾）
site/paid/issue-0001-xxxx.html      付费完整版（路径带 hash，猜不到）
site/feed.xml  /  api/latest.json   给 RSS 阅读器 / 二次分发用
site/digest/issue-0001.md           公众号/小红书文案
site/go/a0.html                     广告位（带点击统计）
```

---

## 4. 部署方案 A：0 元（**推荐，3 天内能上线**）

静态站 + 定时任务都用免费额度，50 块工具费**一分不花在服务器上**。

1. 建 GitHub 仓库，把 `moneybot/` 推上去。
2. Cloudflare 注册账号 → Pages → 建项目 `sidehustle-radar` → 记下 `Account ID`
   → My Profile → API Tokens → 建一个 `Cloudflare Pages:Edit` 的 token。
3. 仓库 Settings → Secrets 加 `CLOUDFLARE_API_TOKEN`、`CLOUDFLARE_ACCOUNT_ID`、`PAID_SECRET`（随便 32 位随机串）；
   Variables 加 `BASE_URL`（先用 `https://sidehustle-radar.pages.dev`）。
4. 已经写好 `.github/workflows/daily.yml`：每天北京时间 07:30 自动跑 `main.py run` 并 `pages deploy`。
   Actions 免费额度 2000 分钟/月，这个任务一次约 40 秒，够跑 100 年。
5. 想要自己的域名：Namecheap/阿里云买 `.top`/`.xyz` 首年 **6–12 元**，CNAME 到 Pages 即可，**不用备案**（境外节点）。

> 缺点：`/go/`、`/api/subscribe`、`/p/<token>` 这三个动态接口在纯静态托管上不可用。
> 应对：广告位用生成的 `go/a0.html` 静态跳转页（一样能记点击，走 JS 打点）；
> 订阅收邮箱用**金数据/腾讯问卷**免费表单；付费用户手动跑 `python3 main.py subscribe ... --paid` 发链接。
> 日更内容不依赖这些接口，所以**先上线跑流量，动态功能后补**。

---

## 5. 部署方案 B：50 元自有服务器（有公网 IP，动态功能全开）

### 买什么

| 选项 | 价格（活动价，随时变） | 说明 |
|---|---|---|
| 阿里云/腾讯云 轻量应用服务器 1核1G/2核2G（新用户） | **约 38–60 元/年** | 最贴合预算；618/双11 更低 |
| 学生机（腾讯云/阿里云校园） | 约 9.9 元/月 | 需学生认证 |
| 雨云 / CloudCone 等海外 VPS | $7–12/年 ≈ 50–85 元 | 免备案，但延迟高、可能被墙 |
| Oracle Cloud 永久免费 ARM | 0 元 | 要信用卡验证，1 核 1G 规模够用 |

**关键合规提醒**：国内服务器绑**域名**必须 ICP 备案（免费，但审核 7–20 天，3 天内下不来）。
所以：
- **3 天内要见效** → 用方案 A（免费托管 + 境外域名），或先用 `http://公网IP:8080` 直接访问；
- 备案同步提交，等下来了再把域名切过去。

### 怎么装（3 条命令）

```bash
# 1. 传代码（本地执行）
scp -r moneybot root@你的IP:/root/

# 2. 一键部署（服务器上执行，会自动装 nginx、建用户、装 systemd 定时器）
ssh root@你的IP
bash /root/moneybot/deploy/deploy.sh your-domain.com   # 没域名就传空

# 3. 验收
curl -s http://你的IP/ | head -5
systemctl list-timers | grep moneybot
```

它会做这些事：装 python3+nginx → 建 `moneybot` 用户 → 拷代码到 `/opt/moneybot` →
生成随机 `ADMIN_TOKEN` / `PAID_SECRET` → 装 `moneybot.timer`（每天 07:30 跑一期）→
装 `moneybot-web.service`（常驻 8080）→ 配 Nginx 反代 + gzip + 静态缓存 → 首跑一期验证。

开 HTTPS（免费证书，2 分钟）：
```bash
apt install -y certbot python3-certbot-nginx
certbot --nginx -d your-domain.com
```

Docker 党：
```bash
cd moneybot/deploy
docker build -t moneybot -f Dockerfile ..
docker run -d --name moneybot -p 8080:8080 -v $PWD/../data:/app/data moneybot
```

---

## 6. 100 元预算怎么花（建议表）

| 项目 | 金额 | 备注 |
|---|---|---|
| 服务器（1核1G 年付活动价） | 38–50 元 | 或 0 元用 Cloudflare Pages + Oracle 免费机 |
| 域名 `.top`/`.xyz` 首年 | 6–12 元 | 免备案用境外节点；国内节点等备案 |
| 备用：AI API（可选，改写摘要） | 0–20 元 | `config.json` 里 `llm.enabled=true` 才花钱，默认关 |
| 备用：小红书/公众号推广 | 0–30 元 | 不建议先投，先用免费渠道测内容 |
| **合计** | **≈ 50–100 元** | 大部分情况 50 元以内搞定 |

**别花的钱**：代运营、买粉、买"矩阵号"、买"自动剪辑软件"——这些是这行的主要亏损来源。

---

## 7. 上线后 72 小时执行清单（老板只需 3 次操作，每次 10 分钟）

| 时间 | 动作 | 耗时 |
|---|---|---|
| D1 上午 | 方案 A 跑通：推 GitHub → 配 3 个 Secrets → 手动触发一次 workflow，确认 `pages.dev` 能打开 | 30 min |
| D1 下午 | 注册爱发电（或面包多）→ 把商品链接填进 `config.json` 的 `monetize.buy_url` → 重跑一次 | 15 min |
| D1 晚 | 把 `site/digest/issue-0001.md` 贴到：即刻、V2EX「分享创造」、小红书（3 图 + 文案）、公众号 | 30 min |
| D2 | 同上，发第 2 期。观察哪个渠道有阅读→点进站；`python3 main.py stats` 看点击 | 15 min |
| D2 晚 | 找 5 个精准社群（独立开发者群、副业群），发"免费领 7 天完整版"（手动 `subscribe --paid`） | 30 min |
| D3 | 有 10 个免费订阅就开卖 ￥9.9；把广告位换成**真能收佣金的**（服务器/AI API 联盟） | 15 min |

3 天现实结果：**大概率是 0–200 元**，而不是几千。
这个项目的正确预期是"第 2–6 周滚到每天几个订阅"，靠的是日更和 SEO 复利。
任何承诺"3 天 100% 回本"的自动化方案，基本都在做违规或诈骗的事——别碰。

---

## 8. 合规红线（写在代码里的，不是嘴上说说）

- ✅ 只读 `robots.txt` 允许的 RSS / 官方公开 API；请求带 UA、限速、单源失败不重试轰炸
- ✅ 商用内容只做**摘要 + 原文链接跳转**，`rel="nofollow noopener"`，页脚注明"版权归原作者"
- ❌ 不全文转载、不洗稿、不镜像别人的付费内容
- ❌ 不抓需要登录/付费/验证码的页面，不伪造 UA 绕过风控
- ❌ 不做刷量、群控、自动私信（平台判定为骚扰，轻则封号重则违法）
- ⚠️ 收入要申报；广告位必须标"广告"（页面已强制标注）
- ⚠️ 别把 Reddit/HN 的评论区原文整段翻译发布，摘要 + 链接才是安全区

---

## 9. 目录结构

```
moneybot/
├── main.py                  CLI：run / stats / subscribe / revenue
├── serve.py                 生产服务器：静态 + /go + /api/subscribe + /p/<token>
├── config.json              源、权重、关键词、价格、广告位（改这里就够了，不用改代码）
├── core/
│   ├── config.py            配置与路径
│   ├── sources.py           HN / Reddit / GitHub / RSS 抓取（标准库）
│   ├── score.py             打分、三重去重、抽取式摘要、可选 LLM 改写
│   ├── render.py            HTML / RSS / JSON / Markdown 渲染 + 付费墙
│   ├── publish.py           静态站发布、付费路径 hash、保留期清理
│   └── store.py             SQLite：条目/期号/订阅/点击/账本
├── data/fixtures/           离线样本（无网络也能跑通全链路）
├── tests/test_pipeline.py   27 个测试（含付费墙泄露、路径穿越、鉴权）
├── deploy/                  systemd + Nginx + Dockerfile + 一键部署脚本
└── .github/workflows/       0 元方案：每天自动生成并发布
```
