const servers = [
  { name: "exa", url: process.env.SELFIT_EXA_MCP_URL || "https://mcp.exa.ai/mcp" },
  { name: "parallel-search", url: process.env.SELFIT_PARALLEL_MCP_URL || "https://search.parallel.ai/mcp" },
];

const timeoutMs = Number(process.env.SELFIT_SEARCH_MCP_PROBE_TIMEOUT_MS || "15000");

async function rpc(url, payload, sessionId = "") {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  const headers = {
    Accept: "application/json, text/event-stream",
    "Content-Type": "application/json",
  };
  if (sessionId) headers["mcp-session-id"] = sessionId;
  try {
    const response = await fetch(url, {
      method: "POST",
      headers,
      body: JSON.stringify(payload),
      signal: controller.signal,
    });
    const body = await response.text();
    if (!response.ok) throw new Error(`HTTP ${response.status}: ${body.slice(0, 240)}`);
    const dataLine = body
      .split(/\r?\n/)
      .find((line) => line.startsWith("data:"));
    const data = JSON.parse(dataLine ? dataLine.slice(5).trim() : body);
    return { data, sessionId: response.headers.get("mcp-session-id") || sessionId };
  } finally {
    clearTimeout(timer);
  }
}

async function probe(server) {
  const initialized = await rpc(server.url, {
    jsonrpc: "2.0",
    id: 1,
    method: "initialize",
    params: {
      protocolVersion: "2025-03-26",
      capabilities: {},
      clientInfo: { name: "selfit-search-doctor", version: "1.0.0" },
    },
  });
  const listed = await rpc(
    server.url,
    { jsonrpc: "2.0", id: 2, method: "tools/list", params: {} },
    initialized.sessionId,
  );
  const tools = listed.data?.result?.tools || [];
  if (!tools.length) throw new Error("MCP server returned no tools");
  return tools.map((tool) => tool.name);
}

let failed = false;
for (const server of servers) {
  try {
    const tools = await probe(server);
    console.log(`OK ${server.name}: ${tools.join(", ")}`);
  } catch (error) {
    failed = true;
    console.error(`FAILED ${server.name}: ${error?.message || error}`);
  }
}

process.exit(failed ? 1 : 0);
