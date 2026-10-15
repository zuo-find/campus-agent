"""批量预热校徽：把全国高校的校徽提前抓好存进后端缓存。

为什么要预热：用户同步官网时现抓要等几秒，而且碰到网络慢/官网改版就可能抓不到。
提前抓好之后，用户选完学校点同步就直接命中缓存，校徽立刻出来。

只存后端，不进小程序包——小程序主包上限 2MB，全量校徽有上百 MB，塞不下；
而且批量打包分发别人的校徽也有版权问题。这里只是"替用户提前抓一次
他自己学校官网上的校徽"，抓完缓存复用。

用法（在 backend 目录下）：
    python scripts/warm_logos.py                # 抓 100 所试试水
    python scripts/warm_logos.py --limit 500    # 抓 500 所
    python scripts/warm_logos.py --all          # 抓全部 583 所
    python scripts/warm_logos.py --retry        # 只重试之前失败的

参数：
    --limit N   最多抓多少所（默认 100）
    --all       抓全部有官网的学校
    --delay S   每所之间停几秒（默认 1.5，别把人家学校网站打疼了）
    --retry     只跑上次没成功的
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from urllib.parse import urlparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx                                      # noqa: E402
from app import school_sync as S                  # noqa: E402

FAILED_PATH = os.path.join(S._BASE, "data", "school_logo_failed.json")


def warm_one(name: str, url: str) -> tuple[bool, str]:
    """抓一所学校的校徽，返回 (是否成功, 说明)。"""
    try:
        with httpx.Client(timeout=20, follow_redirects=True, trust_env=False,
                          headers={"User-Agent": S.UA}) as cli:
            r = cli.get(url)
            r.raise_for_status()
            html = r.text
    except Exception as e:
        return False, "抓页面失败：" + str(e)[:60]

    src = S.find_logo(html, url)
    if not src:
        return False, "页面里没找到校徽"
    try:
        # 用域名当 slug，同一站点的不同栏目共用一张图
        host_slug = "h" + urlparse(url).netloc.lower().replace(".", "_").replace(":", "_")
        path, is_light = S.save_logo(src, host_slug)
    except Exception as e:
        return False, "下载校徽失败：" + str(e)[:60]
    if not path:
        return False, "校徽格式小程序显示不了（可能是纯矢量 SVG）"

    S.put_logo_cache(urlparse(url).netloc.lower(), path, is_light, name)
    return True, path + ("（浅色，前端会垫深底）" if is_light else "")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=100)
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--delay", type=float, default=1.5)
    ap.add_argument("--retry", action="store_true")
    args = ap.parse_args()

    items = json.load(open(os.path.join(S._BASE, "app", "data", "universities.json"),
                           encoding="utf-8"))["items"]
    targets = [x for x in items if x.get("u")]
    if args.retry:
        try:
            want = set(json.load(open(FAILED_PATH, encoding="utf-8")))
            targets = [x for x in targets if x["n"] in want]
        except Exception:
            print("没有失败记录，退出")
            return 0
    if not args.all:
        targets = targets[:args.limit]

    cache = S._logo_cache()
    todo = [x for x in targets if urlparse(x["u"]).netloc.lower() not in cache]
    print("有官网的学校 %d 所，已缓存 %d 所，本次要抓 %d 所（每所间隔 %.1fs）"
          % (len([x for x in items if x.get("u")]), len(cache), len(todo), args.delay))
    if not todo:
        print("都抓过了，无事可做")
        return 0

    ok, failed = 0, []
    for i, x in enumerate(todo, 1):
        good, msg = warm_one(x["n"], x["u"])
        if good:
            ok += 1
            print("[%d/%d] OK   %-16s %s" % (i, len(todo), x["n"], msg))
        else:
            failed.append(x["n"])
            print("[%d/%d] FAIL %-16s %s" % (i, len(todo), x["n"], msg))
        if i < len(todo):
            time.sleep(args.delay)

    json.dump(failed, open(FAILED_PATH, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\n完成：成功 %d，失败 %d（失败的记在 %s，可用 --retry 重来）"
          % (ok, len(failed), os.path.basename(FAILED_PATH)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
