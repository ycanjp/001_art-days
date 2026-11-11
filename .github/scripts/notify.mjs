// Builds the daily summary from data.json and sends it as a web push.
import fs from "node:fs";
import { execSync } from "node:child_process";

const { VAPID_PUBLIC_KEY: pub, VAPID_PRIVATE_KEY: priv, PUSH_SUBSCRIPTION: subRaw, TEST, DRY_RUN } = process.env;

const cur = JSON.parse(fs.readFileSync("data.json", "utf8"));
let prev = { exhibitions: [] };
try {
  const shas = execSync("git log --format=%H -n 2 -- data.json", { encoding: "utf8" }).trim().split("\n");
  if (shas[1]) prev = JSON.parse(execSync(`git show ${shas[1]}:data.json`, { encoding: "utf8", maxBuffer: 1 << 26 }));
} catch (_) { /* first version: nothing to compare with */ }

const today = new Date(Date.now() + 9 * 3600e3).toISOString().slice(0, 10); // JST
const D = (s) => new Date(s + "T00:00:00Z");
const days = (a, b) => Math.round((D(b) - D(a)) / 864e5);
const md = (s) => `${+s.slice(5, 7)}/${+s.slice(8, 10)}`;
const ex = cur.exhibitions || [];
const prevIds = new Set((prev.exhibitions || []).map((x) => x.id));

const added = ex.filter((x) => !prevIds.has(x.id) && !(x.e && x.e < today));
const ending = ex.filter((x) => x.e && x.e >= today && days(today, x.e) <= 7 && (!x.s || x.s <= today))
  .sort((a, b) => a.e.localeCompare(b.e));
const events = ex.flatMap((x) => (x.events || []).filter((e) => e.d && e.d >= today && days(today, e.d) <= 3));

const parts = [];
if (added.length) parts.push(`新しく${added.length}件：${added.slice(0, 2).map((x) => x.t).join("、")}${added.length > 2 ? " ほか" : ""}`);
if (ending.length) parts.push(`今週で終わる${ending.length}件（${ending[0].t} ${md(ending[0].e)}まで${ending.length > 1 ? " ほか" : ""}）`);
if (events.length) parts.push(`3日以内のトーク・イベント${events.length}件`);
if (!parts.length) parts.push("今日は大きな変化はありません");

const title = `${TEST === "true" ? "（テスト）" : ""}アート暦 ${md(cur.updatedAt || today)} 更新`;
const payload = { title, body: parts.join(" ／ "), url: "./" };
console.log(JSON.stringify(payload));

if (DRY_RUN) process.exit(0);
if (!priv || !subRaw) {
  console.log("VAPID_PRIVATE_KEY or PUSH_SUBSCRIPTION is not set; skipping send.");
  process.exit(0);
}
const webpush = (await import("web-push")).default;
webpush.setVapidDetails("https://ycanjp.github.io/001_art-days/", pub, priv);
try {
  const r = await webpush.sendNotification(JSON.parse(subRaw), JSON.stringify(payload), { TTL: 12 * 3600 });
  console.log("sent", r.statusCode);
} catch (e) {
  console.error("send failed", e.statusCode, e.body || e.message);
  if (e.statusCode === 404 || e.statusCode === 410)
    console.error("The subscription has expired. Open the page from the home screen, tap the bell, and register PUSH_SUBSCRIPTION again.");
  process.exit(1);
}
