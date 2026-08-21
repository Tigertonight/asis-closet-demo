import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const required = [
  "agents/selfit-stylist/agent.md",
  "tools/selfit-tools.openapi.json",
  "config/openclaw.example.json",
  "config/search-mcp.example.json",
  "config/xiaohongshu-mcp.example.json",
  "skills/multi-source-search/SKILL.md",
  "openclaw.lock.json",
  "xiaohongshu-mcp.lock.json",
];

let ok = true;
for (const relative of required) {
  const file = path.join(root, relative);
  if (fs.existsSync(file)) {
    console.log(`OK ${relative}`);
  } else {
    ok = false;
    console.error(`MISSING ${relative}`);
  }
}

process.exit(ok ? 0 : 1);
