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
const friendlyStylistErrorMessage = "暂时灵感耗尽，正在努力充能～";

function logBridge(event, details = {}) {
  console.error(JSON.stringify({ event, ts: new Date().toISOString(), ...details }));
}

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
        message: friendlyStylistErrorMessage,
        technical_message: "AI 穿搭师暂时不可用，请检查模型配置。",
      },
      assistant_message: friendlyStylistErrorMessage,
      evidence: { exit_code: code, stderr: String(stderr || "").slice(-2000) },
    };
  }
  return {
    status: "failed",
    error: {
      code: "agent_runtime_unavailable",
      message: friendlyStylistErrorMessage,
      technical_message: "OpenClaw 穿搭师运行时暂时不可用。",
    },
    assistant_message: friendlyStylistErrorMessage,
    evidence: { exit_code: code, stderr: String(stderr || "").slice(-2000) },
  };
}

function buildAgentMessage(payload, message) {
  const context = payload && typeof payload.context === "object" && payload.context !== null ? payload.context : {};
  const closetOnly = Boolean(context.closet_only);
  const trimGroupObject = (groups, groupLimit = 8, itemLimit = 3) => {
    if (!groups || typeof groups !== "object") return {};
    return Object.fromEntries(
      Object.entries(groups)
        .slice(0, groupLimit)
        .map(([key, value]) => [key, Array.isArray(value) ? value.slice(0, itemLimit) : value]),
    );
  };
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
        closet_items: Array.isArray(context.closet_items)
          ? context.closet_items.slice(0, closetOnly ? 14 : 24).map((item) => ({
              item_id: item.item_id || "",
              category: item.category || "",
              subcategory: item.subcategory || "",
              slot: item.slot || "",
              label: item.label || "",
              colors: Array.isArray(item.colors) ? item.colors.slice(0, 4) : [],
              material: Array.isArray(item.material) ? item.material.slice(0, 3) : [],
              fit: item.fit || "",
              pattern: item.pattern || "",
              style_tags: Array.isArray(item.style_tags) ? item.style_tags.slice(0, 6) : [],
              type_tags: Array.isArray(item.type_tags) ? item.type_tags.slice(0, 8) : [],
              favorite: Boolean(item.favorite),
              quality_status: item.quality_status || "",
            }))
          : [],
        closet_item_groups: trimGroupObject(context.closet_item_groups, closetOnly ? 5 : 6, 2),
        closet_outfits: Array.isArray(context.closet_outfits)
          ? context.closet_outfits.slice(0, closetOnly ? 5 : 8).map((outfit) => ({
              outfit_id: outfit.outfit_id || "",
              title: outfit.title || "",
              scene_tags: Array.isArray(outfit.scene_tags) ? outfit.scene_tags.slice(0, 6) : [],
              favorite_count: outfit.favorite_count ?? 0,
              item_ids: Array.isArray(outfit.item_ids) ? outfit.item_ids.slice(0, 8) : [],
              items: Array.isArray(outfit.items) ? outfit.items.slice(0, 6) : [],
            }))
          : [],
        closet_outfit_groups: trimGroupObject(context.closet_outfit_groups, closetOnly ? 4 : 6, 2),
        xiaohongshu_preferred: Boolean(context.xiaohongshu_preferred),
        closet_only: Boolean(context.closet_only),
        xhs_query: context.xhs_query || "",
        xhs_notes: Array.isArray(context.xhs_notes)
          ? context.xhs_notes.slice(0, 6).map((note) => ({
              note_id: note.note_id || "",
              title: note.title || "",
              author_name: note.author_name || "",
              liked_count: note.liked_count || "",
              collected_count: note.collected_count || "",
              detail_summary: String(note.detail_summary || "").slice(0, 240),
              detail_text: String(note.detail_text || note.desc || "").slice(0, 900),
              source_label: note.source_label || "小红书推荐",
            }))
          : [],
        conversation: Array.isArray(context.conversation) ? context.conversation.slice(-8) : [],
      },
      null,
      2,
    ),
    "",
    "Use closet_outfits by scene_tags first when they match the latest User message. Use closet_items by category/slot/subcategory/style_tags/type_tags to compose alternatives across top, bottom/skirt/dress, shoes, bag, and accessory.",
    "When closet_only is true, keep the answer concise and base it on wardrobe evidence only. Do not ask for or wait for Xiaohongshu evidence. Return at most one preferred outfit and one backup, with no more than 5 short bullets in assistant_message.",
    "If no suitable closet_outfits or closet_items match, do not fail and do not invent item_id/outfit_id values. Summarize Xiaohongshu/style evidence and give actionable styling advice with empty recommended_items/recommended_outfits if needed.",
    "Default target audience is women's styling unless the latest User message explicitly asks for male, men's, menswear, or non-female styling. Treat male/menswear Xiaohongshu notes as irrelevant by default.",
    "Use xhs_notes.detail_summary/detail_text as Xiaohongshu note body evidence when present. Ignore any note whose title or body conflicts with the latest User message scene or target gender.",
    "Keep assistant_message user-facing: do not mention internal field names such as xhs_notes, closet_items, closet_item_groups, tool_steps, context, schema, JSON, API, or raw item/outfit IDs.",
    "Return only JSON compatible with asis_stylist_recommendation_v1. Include evidence_sources and quality_checks. Do not invent Xiaohongshu evidence.",
  ];
  return lines.join("\n");
}

async function runOpenClawAgent(payload) {
  const message = String(payload.message || "").trim();
  const requestId = `${Date.now().toString(36)}-${Math.random().toString(16).slice(2, 8)}`;
  const startedAt = Date.now();
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
  const agentMessage = buildAgentMessage(payload, message);
  await writeFile(messagePath, agentMessage, "utf8");
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
  const timeoutMs = Number(process.env.STYLIST_OPENCLAW_TIMEOUT_MS || "240000");
  logBridge("openclaw_start", {
    request_id: requestId,
    session_id: payload.session_id || "default",
    session_key: payload.session_key || "",
    message_chars: message.length,
    prompt_chars: agentMessage.length,
    timeout_ms: timeoutMs,
  });
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
      logBridge("openclaw_timeout", {
        request_id: requestId,
        session_id: payload.session_id || "default",
        elapsed_ms: Date.now() - startedAt,
      });
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
    logBridge("openclaw_failed", {
      request_id: requestId,
      session_id: payload.session_id || "default",
      code: result.code,
      elapsed_ms: Date.now() - startedAt,
      stdout_chars: String(result.stdout || "").length,
      stderr_tail: String(result.stderr || "").slice(-500),
    });
    return { statusCode: 503, data: classifyRuntimeError(result.stderr, result.stdout, result.code) };
  }
  try {
    const parsed = JSON.parse(result.stdout);
    logBridge("openclaw_done", {
      request_id: requestId,
      session_id: payload.session_id || "default",
      elapsed_ms: Date.now() - startedAt,
      stdout_chars: String(result.stdout || "").length,
      status: parsed?.status || "unknown",
    });
    return { statusCode: 200, data: parsed };
  } catch {
    logBridge("openclaw_parse_fallback", {
      request_id: requestId,
      session_id: payload.session_id || "default",
      elapsed_ms: Date.now() - startedAt,
      stdout_chars: String(result.stdout || "").length,
      stderr_tail: String(result.stderr || "").slice(-500),
    });
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
