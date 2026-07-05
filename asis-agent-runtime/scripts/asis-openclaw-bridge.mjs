#!/usr/bin/env node
import { createServer } from "node:http";
import { spawn } from "node:child_process";
import { mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const runtimeRoot = resolve(__dirname, "..");
const openclawCli = process.env.OPENCLAW_CLI || resolve(runtimeRoot, "vendor/openclaw/openclaw.mjs");
const nodeBin = process.env.NODE_BIN || process.execPath;
const port = Number(process.env.ASIS_OPENCLAW_BRIDGE_PORT || process.env.PORT || 18789);
const host = process.env.ASIS_OPENCLAW_BRIDGE_HOST || "127.0.0.1";
const memoryPath = process.env.ASIS_OPENCLAW_MEMORY_PATH || resolve(runtimeRoot, "data/asis-memory.json");
const openclawHome = process.env.OPENCLAW_HOME || resolve(runtimeRoot, ".openclaw-home");
const openclawStateDir = process.env.OPENCLAW_STATE_DIR || resolve(runtimeRoot, ".openclaw");
const openclawConfigPath = process.env.OPENCLAW_CONFIG_PATH || resolve(runtimeRoot, "config/openclaw.local.json");

process.on("uncaughtException", (error) => {
  console.error("asis bridge uncaught exception:", error);
});

process.on("unhandledRejection", (reason) => {
  console.error("asis bridge unhandled rejection:", reason);
});

process.on("SIGTERM", () => {
  console.error("asis bridge received SIGTERM");
});

function jsonResponse(res, statusCode, payload) {
  const body = JSON.stringify(payload);
  res.writeHead(statusCode, {
    "content-type": "application/json; charset=utf-8",
    "content-length": Buffer.byteLength(body),
  });
  res.end(body);
}

async function readJson(req) {
  const chunks = [];
  for await (const chunk of req) chunks.push(chunk);
  if (!chunks.length) return {};
  return JSON.parse(Buffer.concat(chunks).toString("utf8"));
}

async function readMemoryStore() {
  try {
    return JSON.parse(await readFile(memoryPath, "utf8"));
  } catch {
    return { version: 1, users: {} };
  }
}

async function writeMemoryStore(store) {
  await mkdir(dirname(memoryPath), { recursive: true });
  await writeFile(memoryPath, JSON.stringify(store, null, 2), "utf8");
}

function normalizeMemoryPatch(payload) {
  const updates = [];
  const raw = Array.isArray(payload?.memory) ? payload.memory : Array.isArray(payload?.items) ? payload.items : [];
  for (const item of raw) {
    if (!item || typeof item !== "object") continue;
    const id = String(item.id || item.key || `memory_${Date.now()}_${updates.length}`);
    updates.push({
      id,
      type: String(item.type || "preference"),
      content: String(item.content || item.value || ""),
      source: String(item.source || "user_edit"),
      updated_at: new Date().toISOString(),
    });
  }
  if (payload?.content || payload?.value) {
    updates.push({
      id: String(payload.id || payload.key || `memory_${Date.now()}`),
      type: String(payload.type || "preference"),
      content: String(payload.content || payload.value),
      source: String(payload.source || "user_edit"),
      updated_at: new Date().toISOString(),
    });
  }
  return updates;
}

async function handleMemory(req, res, url) {
  const userId = decodeURIComponent(url.pathname.replace(/^\/api\/asis\/memory\/?/, "") || url.searchParams.get("user_id") || "local-user");
  const store = await readMemoryStore();
  store.users ||= {};
  const userMemory = Array.isArray(store.users[userId]) ? store.users[userId] : [];
  if (req.method === "GET") {
    return jsonResponse(res, 200, { status: "ok", user_id: userId, memory: userMemory });
  }
  if (req.method === "PATCH") {
    const payload = await readJson(req);
    const updates = normalizeMemoryPatch(payload);
    const byId = new Map(userMemory.map((item) => [item.id, item]));
    for (const item of updates) byId.set(item.id, { ...(byId.get(item.id) || {}), ...item });
    store.users[userId] = Array.from(byId.values()).filter((item) => item.content);
    await writeMemoryStore(store);
    return jsonResponse(res, 200, { status: "ok", user_id: userId, memory: store.users[userId] });
  }
  if (req.method === "DELETE") {
    delete store.users[userId];
    await writeMemoryStore(store);
    return jsonResponse(res, 200, { status: "ok", user_id: userId, memory: [] });
  }
  return jsonResponse(res, 405, { status: "failed", error: { code: "method_not_allowed", message: "Unsupported memory method." } });
}

function classifyRuntimeError(stderr, stdout, code) {
  const text = `${stderr || ""}\n${stdout || ""}`.toLowerCase();
  if (
    text.includes("api key") ||
    text.includes("apikey") ||
    text.includes("unauthorized") ||
    text.includes("invalid key") ||
    text.includes("quota") ||
    text.includes("credit") ||
    text.includes("billing") ||
    text.includes("model not found") ||
    text.includes("provider")
  ) {
    return {
      status: "failed",
      error: {
        code: "ai_unavailable",
        message: "AI 穿搭师暂时不可用，请检查模型配置。",
      },
      assistant_message: "AI 穿搭师暂时不可用，请检查模型配置。",
      evidence: { exit_code: code, stderr: String(stderr || "").slice(-2000) },
    };
  }
  return {
    status: "failed",
    error: {
      code: "agent_runtime_unavailable",
      message: "OpenClaw 穿搭师运行时暂时不可用。",
    },
    assistant_message: "OpenClaw 穿搭师运行时暂时不可用。",
    evidence: { exit_code: code, stderr: String(stderr || "").slice(-2000) },
  };
}

function buildAgentMessage(payload, message) {
  const context = payload && typeof payload.context === "object" && payload.context !== null ? payload.context : {};
  const lines = [
    "User message:",
    message,
    "",
    "asis bridge context:",
    JSON.stringify(
      {
        session_id: payload.session_id || "default",
        user_id: payload.user_id || "local-user",
        source: context.source || "",
        item_count: context.item_count ?? null,
        outfit_count: context.outfit_count ?? null,
        xiaohongshu_preferred: Boolean(context.xiaohongshu_preferred),
        xhs_query: context.xhs_query || "",
        xhs_notes: Array.isArray(context.xhs_notes)
          ? context.xhs_notes.slice(0, 6).map((note) => ({
              note_id: note.note_id || "",
              title: note.title || "",
              author_name: note.author_name || "",
              liked_count: note.liked_count || "",
              collected_count: note.collected_count || "",
              source_label: note.source_label || "小红书推荐",
            }))
          : [],
        conversation: Array.isArray(context.conversation) ? context.conversation.slice(-8) : [],
      },
      null,
      2,
    ),
    "",
    "Return only JSON compatible with asis_stylist_recommendation_v1. Include evidence_sources and quality_checks. Do not invent Xiaohongshu evidence.",
  ];
  return lines.join("\n");
}

async function runOpenClawAgent(payload) {
  const message = String(payload.message || "").trim();
  if (!message) {
    return {
      statusCode: 400,
      data: {
        status: "failed",
        error: { code: "invalid_request", message: "请先告诉 AI 穿搭师你的场景或问题。" },
        assistant_message: "请先告诉 AI 穿搭师你的场景或问题。",
      },
    };
  }
  const tempDir = await mkdtemp(join(tmpdir(), "asis-openclaw-"));
  const messagePath = join(tempDir, "message.txt");
  await writeFile(messagePath, buildAgentMessage(payload, message), "utf8");
  const args = [
    openclawCli,
    "agent",
    "--local",
    "--json",
    "--agent",
    String(payload.agent_id || process.env.STYLIST_OPENCLAW_AGENT_ID || "asis-stylist"),
    "--session-key",
    String(payload.session_key || `asis:${payload.user_id || "local-user"}:${payload.session_id || "default"}`),
    "--message-file",
    messagePath,
  ];
  if (process.env.STYLIST_OPENCLAW_MODEL) {
    args.push("--model", process.env.STYLIST_OPENCLAW_MODEL);
  }
  const timeoutMs = Number(process.env.STYLIST_OPENCLAW_TIMEOUT_MS || "600000");
  const result = await new Promise((resolvePromise) => {
    const child = spawn(nodeBin, args, {
      cwd: runtimeRoot,
      env: {
        ...process.env,
        OPENCLAW_HOME: openclawHome,
        OPENCLAW_STATE_DIR: openclawStateDir,
        OPENCLAW_CONFIG_PATH: openclawConfigPath,
        ASIS_TOOL_BASE_URL: payload.tool_base_url || process.env.ASIS_TOOL_BASE_URL || "http://127.0.0.1:8002",
      },
      stdio: ["ignore", "pipe", "pipe"],
    });
    const timer = setTimeout(() => {
      child.kill("SIGTERM");
    }, timeoutMs);
    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (chunk) => {
      stdout += chunk.toString();
    });
    child.stderr.on("data", (chunk) => {
      stderr += chunk.toString();
    });
    child.on("error", (error) => {
      clearTimeout(timer);
      resolvePromise({ code: -1, stdout, stderr: `${stderr}\n${error?.message || "Failed to start OpenClaw agent."}` });
    });
    child.on("close", (code) => {
      clearTimeout(timer);
      resolvePromise({ code, stdout, stderr });
    });
  });
  await rm(tempDir, { recursive: true, force: true });
  if (result.code !== 0) {
    return { statusCode: 503, data: classifyRuntimeError(result.stderr, result.stdout, result.code) };
  }
  try {
    const parsed = JSON.parse(result.stdout);
    return { statusCode: 200, data: parsed };
  } catch {
    return {
      statusCode: 200,
      data: {
        status: "ok",
        mode: "openclaw",
        assistant_message: result.stdout.trim(),
      },
    };
  }
}

const server = createServer(async (req, res) => {
  try {
    const url = new URL(req.url || "/", `http://${host}:${port}`);
    if (req.method === "GET" && url.pathname === "/health") {
      return jsonResponse(res, 200, {
        status: "ok",
        runtime: "asis-openclaw-bridge",
        openclaw_cli: openclawCli,
        openclaw_home: openclawHome,
        openclaw_state_dir: openclawStateDir,
        openclaw_config_path: openclawConfigPath,
      });
    }
    if (req.method === "POST" && url.pathname === "/api/asis/chat") {
      const payload = await readJson(req);
      const result = await runOpenClawAgent(payload);
      return jsonResponse(res, result.statusCode, result.data);
    }
    if (url.pathname.startsWith("/api/asis/memory")) {
      return handleMemory(req, res, url);
    }
    return jsonResponse(res, 404, { status: "failed", error: { code: "not_found", message: "Unknown route." } });
  } catch (error) {
    return jsonResponse(res, 500, {
      status: "failed",
      error: { code: "bridge_failed", message: error?.message || "Bridge failed." },
    });
  }
});

server.listen(port, host, () => {
  console.log(`asis OpenClaw bridge listening on http://${host}:${port}`);
});
