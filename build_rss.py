"""
gooood.cn RSS feed 生成器 (GitHub Pages 部署版)

策略:
  1. 抓首页 HTML, 从 __INITIAL_STATE__.home.posts 拿到 18 条带完整字段的文章
  2. 抓 sitemap.xml, 按 lastmod 倒序取前 ~110 个 URL (留余量避免去重后不足)
  3. 抠掉首页已经有的, 剩余条目逐个抓详情页, 从 og:title / og:description / og:image 提取
  4. 拼成标准 RSS 2.0 XML

输出: ./gooood.xml

环境要求: Python 3.10+ (仅标准库)
"""

import html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path

OUTPUT = Path(__file__).parent / "gooood.xml"
TARGET_COUNT = 100

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Referer": "https://www.gooood.cn/",
}

FEED_URL = "https://{USER}.github.io/{REPO}/gooood.xml"
SITE_URL = "https://www.gooood.cn/"

# ---------------------------------------------------------------------------
# 1. 抓取工具
# ---------------------------------------------------------------------------

def fetch(url: str, *, timeout: int = 30, retries: int = 3) -> str:
    last_err = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                raw = r.read()
                charset = r.headers.get_content_charset() or "utf-8"
                return raw.decode(charset, errors="replace")
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
            last_err = e
            print(f"  [重试 {i+1}/{retries}] {url}  err={type(e).__name__}: {e}", file=sys.stderr)
            time.sleep(2 + i * 2)
    raise RuntimeError(f"fetch failed: {url}  last_err={last_err}")


# ---------------------------------------------------------------------------
# 2. 首页
# ---------------------------------------------------------------------------

def parse_home(html_text: str) -> list[dict]:
    m = re.search(r"window\.__INITIAL_STATE__\s*=\s*(\{.+?\});?\s*</script>",
                  html_text, re.DOTALL)
    if not m:
        raise RuntimeError("__INITIAL_STATE__ not found in homepage")
    state = json.loads(m.group(1))
    posts = state["home"]["posts"]
    out = []
    for p in posts:
        slug = p["slug"]
        date_gmt = p["date_gmt"]
        excerpt = strip_html(p["excerpt"]["rendered"])
        title = p["title"]["fulltitle"] or p["title"]["rendered"]
        cover = p["featured_image"]["source_url"] if p.get("featured_image") else ""
        out.append({
            "id": p["id"],
            "slug": slug,
            "url": f"{SITE_URL}{slug}.htm",
            "title": title,
            "description": excerpt,
            "cover": cover,
            "date_gmt": date_gmt,
        })
    return out


# ---------------------------------------------------------------------------
# 3. sitemap
# ---------------------------------------------------------------------------

def parse_sitemap(sitemap_xml: str) -> list[dict]:
    ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    root = ET.fromstring(sitemap_xml)
    out = []
    for url in root.findall("sm:url", ns):
        loc = url.findtext("sm:loc", "", ns)
        lastmod = url.findtext("sm:lastmod", "", ns)
        if loc and "gooood.cn/" in loc and not loc.endswith("/"):
            slug = loc.rsplit("/", 1)[-1].rsplit(".htm", 1)[0]
            out.append({"loc": loc, "lastmod": lastmod, "slug": slug})
    return out


# ---------------------------------------------------------------------------
# 4. 详情页
# ---------------------------------------------------------------------------

def parse_detail(html_text: str) -> dict:
    def meta(prop: str) -> str:
        m = re.search(
            rf'<meta\s+(?:property|name)\s*=\s*[\"\']{re.escape(prop)}[\"\']\s+'
            r'content\s*=\s*[\"\']([^\"\']*)[\"\']',
            html_text, re.IGNORECASE)
        return m.group(1) if m else ""

    title = meta("og:title") or meta("twitter:title")
    desc = meta("og:description") or meta("twitter:description")
    image = meta("og:image") or meta("twitter:image")
    pub = meta("article:published_time")
    if not pub:
        m = re.search(r'<div\s+class="post-data\s+pull-right"[^>]*>\s*(\d{4}-\d{2}-\d{2})\s*</div>',
                      html_text)
        if m:
            pub = m.group(1)
    return {
        "title": html.unescape(title).strip(),
        "description": html.unescape(desc).strip(),
        "image": image.strip(),
        "pub": pub.strip(),
    }


# ---------------------------------------------------------------------------
# 5. 工具
# ---------------------------------------------------------------------------

def strip_html(s: str) -> str:
    if not s:
        return ""
    s = re.sub(r"<[^>]+>", "", s)
    s = html.unescape(s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def iso_to_rfc822(iso: str) -> str:
    if not iso:
        return ""
    try:
        if "T" in iso:
            dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
        elif re.match(r"\d{4}-\d{2}-\d{2}$", iso):
            dt = datetime.strptime(iso, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        else:
            return ""
        return format_datetime(dt, usegmt=True)
    except (ValueError, TypeError) as e:
        print(f"  [iso 解析失败] {iso!r}  {e}", file=sys.stderr)
        return ""


# ---------------------------------------------------------------------------
# 6. 主流程
# ---------------------------------------------------------------------------

def main():
    cache_dir = Path(__file__).parent / ".cache"
    cache_dir.mkdir(exist_ok=True)
    home_cache = cache_dir / "_home.html"

    # 1) 抓首页
    print("[1/4] 抓取首页...")
    if home_cache.exists() and (time.time() - home_cache.stat().st_mtime) < 3600:
        home_html = home_cache.read_text(encoding="utf-8", errors="replace")
        print(f"  使用缓存: {home_cache}")
    else:
        home_html = fetch(SITE_URL)
        home_cache.write_text(home_html, encoding="utf-8")
    home_posts = parse_home(home_html)
    print(f"  首页拿到 {len(home_posts)} 条")
    home_slugs = {p["slug"] for p in home_posts}

    # 2) 抓 sitemap
    print("[2/4] 抓取 sitemap.xml...")
    sitemap_xml = fetch(f"{SITE_URL}sitemap.xml", timeout=60)
    sitemap_entries = parse_sitemap(sitemap_xml)
    print(f"  sitemap 解析到 {len(sitemap_entries)} 条 URL")

    sitemap_entries.sort(key=lambda x: x["lastmod"], reverse=True)
    candidates = [e for e in sitemap_entries if e["slug"] not in home_slugs]
    need = max(TARGET_COUNT - len(home_posts), 0)
    to_fetch = candidates[: need + 20]
    print(f"[3/4] 需补 {need} 条, 准备抓取 {len(to_fetch)} 个详情页 (含余量)")

    extra_posts = []
    fail_count = 0
    for i, e in enumerate(to_fetch):
        if len(extra_posts) >= need:
            break
        try:
            print(f"  [{i+1}/{len(to_fetch)}] {e['loc']}")
            detail_html = fetch(e["loc"], timeout=20)
            d = parse_detail(detail_html)
            if not d["title"]:
                print(f"    [空标题, 跳过]")
                fail_count += 1
                continue
            pub = d["pub"] or e["lastmod"]
            extra_posts.append({
                "slug": e["slug"],
                "url": e["loc"],
                "title": d["title"],
                "description": d["description"],
                "cover": d["image"],
                "date_gmt": pub,
                "id": None,
            })
            time.sleep(0.8)
        except Exception as ex:
            print(f"    [失败] {ex}")
            fail_count += 1

    print(f"  详情页成功: {len(extra_posts)}, 失败: {fail_count}")

    all_posts = home_posts + extra_posts
    all_posts.sort(key=lambda x: x["date_gmt"], reverse=True)
    all_posts = all_posts[:TARGET_COUNT]
    print(f"[4/4] 最终 {len(all_posts)} 条, 开始生成 RSS XML")

    build_rss(all_posts)
    print(f"\n✅ 已生成: {OUTPUT}  ({OUTPUT.stat().st_size} bytes, {len(all_posts)} items)")
    return len(all_posts), fail_count


def build_rss(all_posts: list[dict]):
    build_time = format_datetime(datetime.now(timezone.utc), usegmt=True)
    ATOM = "http://www.w3.org/2005/Atom"
    ET.register_namespace("atom", ATOM)
    ET.register_namespace("content", "http://purl.org/rss/1.0/modules/content/")
    ET.register_namespace("dc", "http://purl.org/dc/elements/1.1/")

    rss = ET.Element("rss", version="2.0")
    channel = ET.SubElement(rss, "channel")
    ET.SubElement(channel, "title").text = "谷德设计网 gooood.cn 最新文章"
    ET.SubElement(channel, "link").text = SITE_URL
    ET.SubElement(channel, "description").text = (
        "谷德设计网是中国具有影响力和广泛关注度的建筑、景观、室内与设计门户平台。"
        "本 feed 自动抓取最近 100 篇文章的标题、摘要与封面。"
    )
    ET.SubElement(channel, "language").text = "zh-CN"
    ET.SubElement(channel, "lastBuildDate").text = build_time
    ET.SubElement(channel, "generator").text = "gooood-rss GitHub Action"

    # self-link
    sl = ET.SubElement(channel, f"{{{ATOM}}}link")
    sl.set("href", os.environ.get("FEED_URL", "https://example.com/gooood.xml"))
    sl.set("rel", "self")
    sl.set("type", "application/rss+xml")

    for p in all_posts:
        item = ET.SubElement(channel, "item")
        ET.SubElement(item, "title").text = p["title"]
        ET.SubElement(item, "link").text = p["url"]
        guid = f"gooood-{p.get('id') or p['slug']}"
        g = ET.SubElement(item, "guid", isPermaLink="false")
        g.text = guid

        rfc = iso_to_rfc822(p["date_gmt"])
        if rfc:
            ET.SubElement(item, "pubDate").text = rfc

        desc_parts = []
        if p["cover"]:
            desc_parts.append(
                f'<p><img src="{html.escape(p["cover"])}" alt="{html.escape(p["title"])}" /></p>')
        if p["description"]:
            desc_parts.append(f"<p>{html.escape(p['description'])}</p>")
        if desc_parts:
            ET.SubElement(item, "description").text = "\n".join(desc_parts)

        if p["cover"]:
            enc = ET.SubElement(item, "enclosure")
            enc.set("url", p["cover"])
            enc.set("type", "image/jpeg")

    ET.indent(rss, space="  ")
    tree = ET.ElementTree(rss)
    tree.write(OUTPUT, encoding="utf-8", xml_declaration=True)


if __name__ == "__main__":
    try:
        n, f = main()
        sys.exit(0 if n >= 50 else 1)
    except Exception as e:
        print(f"\n❌ 失败: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(2)
