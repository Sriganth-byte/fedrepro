const fs = require("fs");
const WebSocket = require("../frontend/node_modules/ws");

const [, , token, output, route = "/dashboard"] = process.argv;
if (!token || !output) throw new Error("Usage: node capture_chrome_page.js <token> <output> [route]");

const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

async function run() {
  const targets = await fetch("http://127.0.0.1:9222/json").then((response) => response.json());
  const target = targets.find((item) => item.type === "page");
  if (!target) throw new Error("No Chrome page target found");
  const ws = new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((resolve, reject) => {
    ws.once("open", resolve);
    ws.once("error", reject);
  });

  let sequence = 0;
  const pending = new Map();
  ws.on("message", (payload) => {
    const message = JSON.parse(payload);
    if (message.id && pending.has(message.id)) {
      const { resolve, reject } = pending.get(message.id);
      pending.delete(message.id);
      if (message.error) reject(new Error(message.error.message));
      else resolve(message.result);
    }
  });
  const send = (method, params = {}) => new Promise((resolve, reject) => {
    const id = ++sequence;
    pending.set(id, { resolve, reject });
    ws.send(JSON.stringify({ id, method, params }));
  });

  await send("Page.enable");
  await send("Runtime.enable");
  await send("Emulation.setDeviceMetricsOverride", {
    width: 1440,
    height: 1000,
    deviceScaleFactor: 1,
    mobile: false
  });
  await send("Runtime.evaluate", {
    expression: `localStorage.setItem("fedrepro_token", ${JSON.stringify(token)})`
  });
  await send("Page.navigate", { url: `http://127.0.0.1:3000${route}` });
  await wait(3500);
  const result = await send("Page.captureScreenshot", { format: "png", captureBeyondViewport: false });
  fs.writeFileSync(output, Buffer.from(result.data, "base64"));
  ws.close();
}

run().catch((error) => {
  console.error(error);
  process.exit(1);
});
