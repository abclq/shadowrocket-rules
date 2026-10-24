#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Shadowrocket 规则构建脚本（在 GitHub Actions 里跑，不依赖本机）

流程：
  1. 从上游 johnshall.github.io 拉最新的 sr_top500_banlist_ad.conf 和 lazy.conf
  2. 打补丁：
     - [General] 段补上 QUIC/UDP 相关设置（上游缺失 → 原生 App 走 HTTP/3 时漏代理）
     - 补上上游规则库未收录的域名（hark 等）
     - 引用自建的 sr-custom.list
     - 把规则集引用里的 raw.githubusercontent.com 换成国内可直连的 jsdelivr 镜像
  3. 写回仓库

每次都是从上游**原始文件**重新生成，所以脚本可反复执行、结果幂等。
上游格式若变动导致锚点找不到，脚本会直接报错退出，**不会**覆盖仓库里已有的好文件。
"""

import re
import sys
import urllib.request
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent

UPSTREAM = "https://johnshall.github.io/Shadowrocket-ADBlock-Rules-Forever"
BANLIST_URL = f"{UPSTREAM}/sr_top500_banlist_ad.conf"
LAZY_URL = f"{UPSTREAM}/lazy.conf"

# 自建补充规则集（走 jsdelivr，国内可直连）
CUSTOM_LIST_URL = (
    "https://gcore.jsdelivr.net/gh/abclq/shadowrocket-rules@main/sr-custom.list"
)

GENERAL_PATCH = """# ===== 补丁：QUIC/UDP 处理（上游配置缺失，导致 Hark/Muse/Facebook 等原生 App 登录失败）=====
# Shadowrocket 的 TUN 接口只处理 TCP；HTTP/3(QUIC) 走 UDP/443 会被漏掉 → 阻断它，强制 App 回退 TCP
block-quic = all-proxy
# 节点不支持 UDP 转发时的行为
udp-policy-not-supported-behaviour = REJECT
# 劫持 App 硬编码的 8.8.8.8 / 8.8.4.4 DNS，防止被污染
hijack-dns = 8.8.8.8:53,8.8.4.4:53
# 域名解析到私有 IP 时仍按域名规则走
private-ip-answer = true
# 直连域名解析失败时回退走代理
dns-direct-fallback-proxy = true
"""

CUSTOM_RULES = """# ===== 自建补充规则集（Hark / Meta Muse / 其它上游未收录的新 App）=====
RULE-SET,{custom},PROXY
DOMAIN-SUFFIX,hark.com,PROXY
DOMAIN-SUFFIX,harklabs.com,PROXY

""".format(custom=CUSTOM_LIST_URL)

# 通用规则：锚点 -> 注入内容
DNS_ANCHOR = "dns-server = https://dns.alidns.com/dns-query, https://doh.pub/dns-query"


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (rules-builder)"})
    with urllib.request.urlopen(req, timeout=90) as resp:
        return resp.read().decode("utf-8", "ignore")


def mirror_raw_github(text: str) -> str:
    """把 raw.githubusercontent.com 的引用换成国内可直连的 jsdelivr 镜像。

    raw.githubusercontent.com/OWNER/REPO/BRANCH/PATH
      -> gcore.jsdelivr.net/gh/OWNER/REPO@BRANCH/PATH
    """
    def repl(m):
        owner, repo, branch, rest = m.group(1), m.group(2), m.group(3), m.group(4)
        return f"https://gcore.jsdelivr.net/gh/{owner}/{repo}@{branch}/{rest}"

    return re.sub(
        r"https://raw\.githubusercontent\.com/([^/]+)/([^/]+)/([^/]+)/(\S+)",
        repl,
        text,
    )


def patch_banlist(src: str) -> str:
    # 1) [General] 补 QUIC/UDP 设置（插在 dns-server 那一行之后）
    if DNS_ANCHOR not in src:
        raise SystemExit("[FATAL] 上游 banlist 里找不到 dns-server 锚点，格式可能变了，放弃更新")
    if "block-quic" not in src:
        src = src.replace(DNS_ANCHOR, DNS_ANCHOR + "\n" + GENERAL_PATCH, 1)

    # 2) 补规则（插在 FINAL 兜底之前）
    if "FINAL,direct" not in src:
        raise SystemExit("[FATAL] 上游 banlist 里找不到 FINAL,direct 锚点，放弃更新")
    # 注意：不能用 `"hark.com" in src` 判断 —— 上游有 vidscriptshark.com / surfshark.com
    # 这类包含 "hark.com" 子串的域名，会误判成「已存在」而跳过注入。
    # 用自建规则集的 URL 作为唯一哨兵。
    if "sr-custom.list" not in src:
        idx = src.rindex("FINAL,direct")
        src = src[:idx] + CUSTOM_RULES + src[idx:]

    # 3) 规则集引用换国内镜像
    return mirror_raw_github(src)


def patch_lazy(src: str) -> str:
    # 规则集引用换国内镜像
    src = mirror_raw_github(src)

    # 补规则：插在真正的 GEOIP,CN,DIRECT 规则行之前（跳过注释里出现的那次）
    lines = src.splitlines()
    pos = None
    for i, line in enumerate(lines):
        if line.strip() == "GEOIP,CN,DIRECT" and not line.lstrip().startswith("#"):
            pos = i
            break
    if pos is None:
        raise SystemExit("[FATAL] 上游 lazy.conf 里找不到 GEOIP,CN,DIRECT 规则行，放弃更新")

    if not any("sr-custom.list" in l for l in lines):
        inject = [
            "# ===== 自建补充规则集（Hark / Meta Muse / 其它上游未收录的新 App）=====",
            f"RULE-SET,{CUSTOM_LIST_URL},PROXY",
            "DOMAIN-SUFFIX,hark.com,PROXY",
            "DOMAIN-SUFFIX,harklabs.com,PROXY",
            "",
        ]
        lines = lines[:pos] + inject + lines[pos:]

    return "\n".join(lines) + "\n"


def write_if_changed(path: pathlib.Path, content: str) -> bool:
    old = path.read_text(encoding="utf-8") if path.exists() else None
    if old == content:
        print(f"  = 无变化 {path.name}")
        return False
    path.write_text(content, encoding="utf-8")
    print(f"  + 已更新 {path.name}  ({len(content)} 字节)")
    return True


def main() -> int:
    print("拉取上游配置…")
    banlist_raw = fetch(BANLIST_URL)
    lazy_raw = fetch(LAZY_URL)
    print(f"  banlist {len(banlist_raw)} 字节 / lazy {len(lazy_raw)} 字节")

    # 先全部构建成功，再落盘 —— 任何一步失败都不会破坏仓库里已有的文件
    banlist_new = patch_banlist(banlist_raw)
    lazy_new = patch_lazy(lazy_raw)

    changed = False
    changed |= write_if_changed(ROOT / "sr-banlist-patched.conf", banlist_new)
    changed |= write_if_changed(ROOT / "sr-lazy.conf", lazy_new)

    print("有变化" if changed else "全部为最新，无需提交")
    return 0


if __name__ == "__main__":
    sys.exit(main())
