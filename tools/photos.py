#!/usr/bin/env python3
"""会場の外観写真（Wikimedia Commons）を管理する。毎朝の更新で使う。

  python3 tools/photos.py missing [プレビュー保存先]   写真のない新しい会場と候補を出す
  python3 tools/photos.py add "<会場名(data.jsonのv)>" "<Commonsのファイル名>"
  python3 tools/photos.py none "<会場名>"            見つからなかった/合わなかったと記録（90日は再検索しない）
"""
import json, re, os, sys, time, html, hashlib, subprocess, tempfile, datetime, urllib.request, urllib.parse
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PJ, DJ = os.path.join(ROOT, "photos.json"), os.path.join(ROOT, "data.json")
UA = {"User-Agent": "art-calendar-prototype/0.1"}
FREE = re.compile(r"^(CC0|CC BY(-SA)? [0-9.]+|Public domain|PD.*)", re.I)
RECHECK_DAYS = 90

def get(url, **p):
    q = url + "?" + urllib.parse.urlencode({**p, "format": "json"})
    for i in range(5):
        try: return json.load(urllib.request.urlopen(urllib.request.Request(q, headers=UA), timeout=30))
        except Exception: time.sleep(10 * (i + 1))
    return {}

def fetch(url, out):
    for i in range(5):
        try:
            open(out, "wb").write(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30).read()); return
        except Exception: time.sleep(10 * (i + 1))
    raise SystemExit("download failed: " + url)

def load():
    p = json.load(open(PJ, encoding="utf-8")); p.setdefault("none", {}); return p

def save(p):
    names = {}
    for v, e in p["venues"].items(): names.setdefault(e["page"], []).append(re.sub(r"（.*?）", "", v))
    for v, e in p["venues"].items(): e["name"] = "・".join(dict.fromkeys(names[e["page"]]))
    json.dump(p, open(PJ, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

def p18(qid):
    c = get("https://www.wikidata.org/w/api.php", action="wbgetclaims", entity=qid, property="P18")
    cl = c.get("claims", {}).get("P18", [])
    return cl[0]["mainsnak"]["datavalue"]["value"] if cl else None

def info(f):
    r = get("https://commons.wikimedia.org/w/api.php", action="query", titles="File:" + f, prop="imageinfo", iiprop="url|extmetadata", iiurlwidth=720)
    ii = next(iter(r.get("query", {}).get("pages", {"x": {}}).values())).get("imageinfo", [{}])[0]
    m = ii.get("extmetadata", {}); s = lambda k: html.unescape(re.sub(r"<[^>]+>", "", m.get(k, {}).get("value") or "")).strip()
    return {"thumb": ii.get("thumburl"), "page": ii.get("descriptionurl"), "by": s("Artist"), "lic": s("LicenseShortName")}

def clean_by(b):
    b = b.replace("\n", " ")
    if "derivative" in b and ":" in b: b = b.split(":", 1)[1].split("derivative")[0]
    b = re.sub(r"^photo:\s*", "", b); b = re.split(r"\s*\(talk\)| Taken with| from [A-Z]", b)[0]
    return b.strip()[:60] or "Wikimedia Commons"

def missing(prev_dir):
    p = load(); d = json.load(open(DJ, encoding="utf-8")); today = datetime.date.today()
    todo = []
    for v in dict.fromkeys(e["v"] for e in d["exhibitions"]):
        if v in p["venues"]: continue
        n = p["none"].get(v)
        if n and (today - datetime.date.fromisoformat(n)).days < RECHECK_DAYS: continue
        todo.append(v)
    if not todo: print("写真が必要な新しい会場はありません"); return
    os.makedirs(prev_dir, exist_ok=True)
    for v in todo:
        key = re.sub(r"（.*?）", "", v).strip()
        cands = []
        for h in get("https://www.wikidata.org/w/api.php", action="wbsearchentities", search=key, language="ja", limit=3).get("search", []):
            cands.append((h["id"], h.get("label"), h.get("description")))
        s = get("https://ja.wikipedia.org/w/api.php", action="query", list="search", srsearch=key, srlimit=1).get("query", {}).get("search", [])
        if s:
            pp = get("https://ja.wikipedia.org/w/api.php", action="query", prop="pageprops", titles=s[0]["title"], ppprop="wikibase_item")
            q = next(iter(pp.get("query", {}).get("pages", {"x": {}}).values())).get("pageprops", {}).get("wikibase_item")
            if q and q not in [c[0] for c in cands]: cands.append((q, s[0]["title"], "ja.wikipedia 検索1位"))
        print(f"\n■ {v}")
        if not cands: print("  候補なし → none に記録してよい")
        for q, label, desc in cands:
            f = p18(q); time.sleep(1)
            if not f: print(f"  {q} {label} / {desc} / 画像なし"); continue
            i = info(f); prev = ""
            if i["thumb"] and FREE.match(i["lic"] or ""):
                prev = os.path.join(prev_dir, hashlib.md5(f.encode()).hexdigest()[:10] + ".jpg"); fetch(i["thumb"], prev)
            print(f"  {q} {label} / {desc}\n    file: {f}\n    license: {i['lic']}  preview: {prev or '（自由ライセンスでないため不可）'}")
            time.sleep(1)

def add(v, f):
    i = info(f)
    if not i["thumb"]: raise SystemExit("Commonsにそのファイルがありません: " + f)
    if not FREE.match(i["lic"] or ""): raise SystemExit("自由ライセンスではないので使えません: " + i["lic"])
    h = hashlib.md5(f.encode()).hexdigest()[:10]; os.makedirs(os.path.join(ROOT, "img/v"), exist_ok=True)
    with tempfile.TemporaryDirectory() as t:
        src = os.path.join(t, "src.jpg"); fetch(i["thumb"], src)
        for size, out, flag in ((640, f"img/v/{h}.jpg", "--resampleWidth"), (168, f"img/v/{h}-s.jpg", "-Z")):
            mid = os.path.join(t, "mid.jpg")
            subprocess.run(["sips", "-s", "format", "jpeg", flag, str(size), src, "--out", mid], capture_output=True, check=True)
            subprocess.run(["sips", "-s", "formatOptions", "60", mid, "--out", os.path.join(ROOT, out)], capture_output=True, check=True)
    p = load(); p["none"].pop(v, None)
    p["venues"][v] = {"m": f"img/v/{h}.jpg", "s": f"img/v/{h}-s.jpg", "by": clean_by(i["by"]), "lic": i["lic"], "page": i["page"]}
    save(p); print(f"追加: {v} ← {f}（{i['lic']} / {clean_by(i['by'])}）  files: img/v/{h}.jpg img/v/{h}-s.jpg")

def none(v):
    p = load(); p["none"][v] = datetime.date.today().isoformat(); save(p); print("記録: " + v)

if __name__ == "__main__":
    a = sys.argv[1:]
    if a[:1] == ["missing"]: missing(a[1] if len(a) > 1 else os.path.join(tempfile.gettempdir(), "artdays-photo-preview"))
    elif a[:1] == ["add"] and len(a) == 3: add(a[1], a[2])
    elif a[:1] == ["none"] and len(a) == 2: none(a[1])
    else: print(__doc__)
