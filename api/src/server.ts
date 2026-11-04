import http from "node:http";

import { createApp } from "./app.js";
import { loadConfig } from "./config.js";
import { createDb } from "./db.js";
import { createRagClient } from "./ragClient.js";
import { failStuckFiles } from "./store/files.js";

const config = loadConfig();
const db = createDb(config.databaseUrl);
const rag = createRagClient(config.ragServiceUrl, config.ragServiceSecret);

const server = http.createServer(createApp({ config, db, rag }));
// Only the website's own server talks to this API, so listen on this computer only.
server.listen(config.port, "127.0.0.1", () => console.log(`API listening on http://127.0.0.1:${config.port}`));

// Files left "processing" because the indexing service stopped are marked failed, so the user can try again.
async function reap() {
  try {
    const count = await failStuckFiles(db);
    if (count > 0) console.log(`Marked ${count} interrupted file(s) as failed.`);
  } catch (error) {
    console.error("Could not check for interrupted files:", error);
  }
}
void reap();
setInterval(reap, 5 * 60_000).unref();

function shutdown() {
  server.close(() => void db.end().finally(() => process.exit(0)));
}
process.on("SIGINT", shutdown);
process.on("SIGTERM", shutdown);
