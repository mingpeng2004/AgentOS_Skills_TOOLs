#!/usr/bin/env node
/**
 * AI 专用浏览器 · CDP 操作台（与 bin/ai_browser.py 配套）。
 *
 *   node ai_browser.js open  <url> [--wait ms] [--text]      打开（可选打印正文）
 *   node ai_browser.js shot  <out.png> [--url <url>] [--full] 截图（默认视口，--full 整页）
 *   node ai_browser.js pdf   <out.pdf> [--url <url>]         打印为 PDF（A4）
 *   node ai_browser.js text  [--url <url>]                   打印正文文本
 *   node ai_browser.js status                                CDP 状态
 *
 * 约束（见 protocols/DESKTOP-NONINTERFERENCE.md）：
 *   · 只连 9418 端口的**专用**浏览器，绝不碰用户的浏览器；
 *   · 专用浏览器必须已离屏启动（ai_browser.py start）；
 *   · 需要等待渲染时优先轮询正文长度，别盲等。
 */
const fs = require('fs');
const http = require('http');
const path = require('path');

const PORT = 9418;

function httpJson(p, method = 'GET') {
  return new Promise((resolve, reject) => {
    const req = http.request({ host: '127.0.0.1', port: PORT, path: p, method }, (res) => {
      let d = '';
      res.on('data', (c) => { d += c; });
      res.on('end', () => {
        try { resolve(JSON.parse(d)); } catch (e) { reject(new Error('非 JSON: ' + d.slice(0, 120))); }
      });
    });
    req.on('error', reject);
    req.end();
  });
}

function connectWs(url) {
  return new Promise((resolve, reject) => {
    const ws = new WebSocket(url);
    let id = 0;
    const pending = new Map();
    ws.onopen = () => resolve({
      send: (method, params = {}) => new Promise((res, rej) => {
        const mid = ++id;
        pending.set(mid, { res, rej });
        ws.send(JSON.stringify({ id: mid, method, params }));
        setTimeout(() => { if (pending.has(mid)) { pending.delete(mid); rej(new Error('CDP 超时: ' + method)); } }, 120000);
      }),
      close: () => ws.close(),
    });
    ws.onerror = (e) => reject(new Error('WebSocket 连接失败'));
    ws.onmessage = (ev) => {
      let msg;
      try { msg = JSON.parse(ev.data); } catch { return; }
      if (msg.id && pending.has(msg.id)) {
        const { res, rej } = pending.get(msg.id);
        pending.delete(msg.id);
        if (msg.error) rej(new Error(msg.error.message)); else res(msg.result);
      }
    };
  });
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function attach() {
  const list = await httpJson('/json/list');
  const t = list.find((x) => x.type === 'page') || (await httpJson('/json/new?about:blank', 'PUT'));
  const c = await connectWs(t.webSocketDebuggerUrl);
  await c.send('Page.enable');
  await c.send('Runtime.enable');
  await c.send('Emulation.setDeviceMetricsOverride', { width: 1400, height: 1200, deviceScaleFactor: 1, mobile: false });
  return c;
}

async function evalJs(c, expr) {
  const r = await c.send('Runtime.evaluate', { expression: expr, returnByValue: true, awaitPromise: true });
  if (r.exceptionDetails) throw new Error(r.exceptionDetails.text || '脚本异常');
  return r.result && r.result.value;
}

async function waitRender(c, ms) {
  const end = Date.now() + (ms || 8000);
  while (Date.now() < end) {
    await sleep(1200);
    const st = await evalJs(c, `(() => {
      const t = document.body ? document.body.innerText : '';
      return {len: t.length, title: document.title};
    })()`).catch(() => null);
    if (st && st.len > 500) return st;
  }
  return null;
}

(async () => {
  const [cmd, out, ...rest] = process.argv.slice(2);
  const flag = (n, d) => {
    const i = rest.indexOf(n);
    return i >= 0 ? rest[i + 1] : d;
  };
  const c = await attach();
  // open 的第一个位置参数就是 URL；其余子命令用 --url
  let url = flag('--url', null);
  if (!url && cmd === 'open' && out && /^https?:\/\//.test(out)) url = out;

  if (cmd === 'status') {
    console.log(JSON.stringify(await httpJson('/json/version'), null, 1));
    process.exit(0);
  }
  if (url) {
    await c.send('Page.navigate', { url });
    await sleep(2500);
    await waitRender(c, 12000);
  }
  if (cmd === 'terms') {
    // OBP 首次进入的条款门：GWT 只认真实鼠标事件 ⇒ 用 Input 域派发真实点击
    const pts = await evalJs(c, `(() => {
      const cb = document.querySelector('input[type=checkbox]');
      const els = Array.from(document.querySelectorAll('span.v-button-caption, div.v-button, button, a'));
      const b = els.find(e => /^anonymous user$/i.test((e.innerText || '').trim()));
      const rect = (el) => { if (!el) return null; const r = el.getBoundingClientRect();
        return { x: r.left + r.width / 2, y: r.top + r.height / 2 }; };
      return { cb: rect(cb), btn: rect(b) };
    })()`);
    const click = async (p) => {
      if (!p) return;
      for (const type of ['mousePressed', 'mouseReleased']) {
        await c.send('Input.dispatchMouseEvent', {
          type, x: p.x, y: p.y, button: 'left', clickCount: 1,
          buttons: type === 'mousePressed' ? 1 : 0,
        });
        await sleep(250);
      }
    };
    if (pts && pts.cb) await click(pts.cb);
    await sleep(700);
    const pts2 = await evalJs(c, `(() => {
      const els = Array.from(document.querySelectorAll('span.v-button-caption, div.v-button, button, a'));
      const b = els.find(e => /^anonymous user$/i.test((e.innerText || '').trim()));
      if (!b) return null; const r = b.getBoundingClientRect();
      return { x: r.left + r.width / 2, y: r.top + r.height / 2 };
    })()`);
    if (pts2) await click(pts2);
    await sleep(3000);
    console.log('terms clicked');
    process.exit(0);
  }
  if (cmd === 'probe') {
    // 列出当前页里**真正可滚动**的元素（找预览面板用）
    const r = await evalJs(c, `(() => {
      const out = [];
      document.querySelectorAll('*').forEach(el => {
        if (el.scrollHeight > el.clientHeight + 30 && el.clientHeight > 120) {
          const s = getComputedStyle(el);
          out.push({ tag: el.tagName, cls: String(el.className || '').slice(0, 40),
            ch: el.clientHeight, sh: el.scrollHeight, oy: s.overflowY,
            txt: (el.innerText || '').replace(/\\n+/g, ' ').slice(0, 40) });
        }
      });
      return { n: out.length, list: out.slice(0, 10), ih: window.innerHeight,
               bsh: document.body.scrollHeight, title: document.title };
    })()`);
    console.log(JSON.stringify(r, null, 1));
    process.exit(0);
  }
  if (cmd === 'cookie') {
    // 注入 clearance（Cloudflare 放行标记）到专用浏览器的持久 profile
    // 用法: node ai_browser.js cookie <cookies.json> [--only name1,name2]
    const file = out;
    const data = JSON.parse(fs.readFileSync(file, 'utf8'));
    const list = Array.isArray(data) ? data : (data.cookies || []);
    const only = flag('--only', null);
    const keep = only ? only.split(',') : null;
    let ok = 0;
    for (const ck of list) {
      if (keep && !keep.includes(ck.name)) continue;
      const r = await c.send('Network.setCookie', {
        name: ck.name, value: ck.value, domain: ck.domain, path: ck.path || '/',
        secure: !!ck.secure, httpOnly: !!ck.httpOnly,
      });
      if (r && r.success) ok++; else console.log('  fail', ck.name, JSON.stringify(r));
    }
    console.log(`cookies set: ${ok}/${list.length}`);
    process.exit(0);
  }
  if (cmd === 'wait') {
    // 等 Cloudflare 挑战自动通过（或页面渲染完）：轮询标题与正文长度
    const ms = parseInt(flag('--ms', '60000'), 10);
    const end = Date.now() + ms;
    let last = '';
    while (Date.now() < end) {
      await sleep(3000);
      const t = await evalJs(c, 'document.title').catch(() => '');
      const len = await evalJs(c, "String((document.body?document.body.innerText:'')).length").catch(() => 0);
      const sig = `${t} ${len}`;
      if (sig !== last) { console.log(`${Math.round(ms - (end - Date.now()))}ms left | title="${String(t).slice(0, 50)}" len=${len}`); last = sig; }
      if (t && !/请稍候|just a moment|安全验证|attention required|checking your browser/i.test(t) && len > 400) {
        console.log('READY');
        process.exit(0);
      }
    }
    console.log('TIMEOUT');
    process.exit(2);
  }
  if (cmd === 'open' || cmd === 'text') {
    const t = await evalJs(c, "(document.body?document.body.innerText:'')");
    console.log(t);
    process.exit(0);
  }
  if (cmd === 'shot') {
    const p = { format: 'png' };
    if (rest.includes('--full')) p.captureBeyondViewport = true;
    const r = await c.send('Page.captureScreenshot', p);
    fs.mkdirSync(path.dirname(out), { recursive: true });
    fs.writeFileSync(out, Buffer.from(r.data, 'base64'));
    console.log(out, fs.statSync(out).size, 'bytes');
    process.exit(0);
  }
  if (cmd === 'pdf') {
    const r = await c.send('Page.printToPDF', {
      printBackground: true, paperWidth: 8.27, paperHeight: 11.69,
      marginTop: 0.3, marginBottom: 0.3, marginLeft: 0.3, marginRight: 0.3,
    });
    fs.mkdirSync(path.dirname(out), { recursive: true });
    fs.writeFileSync(out, Buffer.from(r.data, 'base64'));
    console.log(out, fs.statSync(out).size, 'bytes');
    process.exit(0);
  }
  console.log('用法见文件头注释');
  process.exit(2);
})().catch((e) => { console.error('ERR', e.message); process.exit(1); });
