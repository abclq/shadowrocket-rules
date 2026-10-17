# Shadowrocket 线上分流规则（自建补丁版）

> 修好「黑名单模式漏新域名」+「QUIC/UDP 不走代理」两个坑，补齐 Hark / Meta Muse 等未收录域名。
> 所有规则集引用已换成 **国内可直连的 jsdelivr 镜像**，手机不挂代理也能拉到。

## 为什么会有这个仓库

用 `sr_top500_banlist_ad.conf` 这类**黑名单**配置时，有两个问题：

1. **兜底是 `FINAL,direct`** —— 只要域名没被 GFWList / blackmatrix7 收录，就**直连**。
   `hark.com`（Hark AI 助手）在 87,541 行规则里 **0 命中** → 直连 → 被 Cloudflare **403** → App 报「登录失败。请重试。」
2. **`[General]` 段缺少 `block-quic`** —— Shadowrocket 的 TUN 接口**只处理 TCP**。
   Hark / Muse / Facebook 这些原生 App 优先走 **HTTP/3（QUIC over UDP 443）**，UDP 没被代理 → 请求漏出去 → 卡登录。
   而 Safari 里的谷歌授权走 TCP → 成功。这就是「网页能成、原生 App 全挂」的原因。

## 规则文件

| 文件 | 说明 | 建议 |
|---|---|---|
| `sr-lazy.conf` | **懒人配置**：`GEOIP,CN,DIRECT` + `FINAL,PROXY`（国内直连、其它全走代理）+ `block-quic = all-proxy` | ⭐ **推荐，新域名自动走代理，一劳永逸** |
| `sr-banlist-patched.conf` | 原黑名单配置 + 5 条 General 补丁 + hark 规则（**87,771 条规则 / 3.35 MB**） | ⚠️ **不建议**。体积是懒人配置的 140 倍，小火箭在 iOS 上受 NetworkExtension 内存上限约束，规则数超 6 万条会在载入阶段 OOM，表现就是「订阅不下来」；而且它的兜底 `FINAL,direct` 正是 Hark 登录失败的根因 |
| `sr-custom.list` | 补充规则集（Hark / Meta Muse / 常见 AI / 广告拦截） | **不是订阅**，是给配置引用的规则集。`sr-lazy.conf` 里已经引用它了，不用单独下载 |

## 订阅地址（国内可直连）

**只有一个订阅**（24 KB，秒下）：

```
https://gcore.jsdelivr.net/gh/abclq/shadowrocket-rules@main/sr-lazy.conf
```

> ⚠️ 另外两个文件**不是订阅**，别往小火箭的「配置」页里加：
>
> - **`sr-banlist-patched.conf`** —— 3.35 MB / 87,771 条规则。链接本身能下（实测 6/6 成功，5~14 秒），但小火箭在 iOS 上受 NetworkExtension 内存硬限约束，规则数超过 6 万条会在**载入阶段 OOM 被系统杀掉**，用户看到的就是「订阅不下来」。**请改用 `sr-lazy.conf`。**
> - **`sr-custom.list`** —— 规则集，只供配置文件用 `RULE-SET` 引用，**本身不是配置**。`sr-lazy.conf` 已经引用了它，规则已经在生效，不需要单独下载。

备用镜像（jsdelivr 前缀实测：`gcore` 最快，`testingcf` 次之，`fastly` / `cdn` 国内已不可达）：

```
https://gcore.jsdelivr.net/gh/abclq/shadowrocket-rules@main/sr-lazy.conf
https://testingcf.jsdelivr.net/gh/abclq/shadowrocket-rules@main/sr-lazy.conf
```

GitHub 原生（国内多数网络拉不动，仅作备份）：

```
https://raw.githubusercontent.com/abclq/shadowrocket-rules/main/sr-lazy.conf
```

## 自动更新（跑在 GitHub Actions，不占本机）

`.github/workflows/update.yml` 每天 **08:40（北京时间）** 自动执行：

1. 拉上游最新 `sr_top500_banlist_ad.conf` + `lazy.conf`
2. 跑 `scripts/build.py` 重新打补丁
3. 有变化才提交（amend + force push 覆盖上一条，历史不增长，3MB 的大文件不会一天天堆积）

上游 `johnshall` 每天 08:00 更新，我们 08:40 跟进。
手动触发：仓库 → **Actions** → 「每日更新规则」 → **Run workflow**。

> ⚠️ **实际执行时间会比 08:40 晚几个小时** —— 上面的 `40 0 * * *` 是**调度时间**，不是**执行时间**。
> GitHub 对公开仓库的定时任务是**排队执行**的，官方明确不保证准点。
> 实测：2026-10-14 实际 `05:19Z`、10-15 实际 `05:06Z`（= 北京 13:19 / 13:06），比 08:40 晚 4~5 小时。
> 想让规则立刻生效就**手动触发**（见下），别干等定时。规则内容不受影响，只是当天生效时间会顺延。

> 上游格式若变动导致锚点找不到，`build.py` 会直接报错退出，**不会**覆盖仓库里已有的好文件。
> 本机完全不需要参与，关机也照样更新。

## 在 Shadowrocket 里怎么用

1. 首页 → **配置** → 右上角 `+`
2. **URL** 填上面 `sr-lazy.conf` 的地址 → 下载
3. 点一下让它打勾（启用）
4. **断开 VPN 重连一次**（必须，否则新配置不生效）

## 验证

- Safari 打开 `https://hark.com` → 出正常页面（不是 Cloudflare 403）= 成了
- 然后回去登 Hark / Muse

## 已知取舍

- `sr-lazy.conf` 是「国外走代理、国内直连」模型，**所有国外域名都会走代理**（这正是原生 App 需要的行为）。
- 如果某些国内 App 走代理变慢，往 `[Rule]` 段加 `DOMAIN-SUFFIX,xxx.com,DIRECT` 即可。
- `sr-banlist-patched.conf` 保留了黑名单模型（`FINAL,direct`），**以后新出的 App 仍会被漏掉** —— 这正是 Hark 当初打不开的原因；而且 87,771 条规则在 iOS 上根本载入不了。**已弃用，不要再订阅它。**
- 以后遇到打不开的 App，往 `sr-custom.list` 加域名即可 —— `sr-lazy.conf` 会自动引用到。
