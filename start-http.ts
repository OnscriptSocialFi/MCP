// Entry point for HTTP mode (direct run, no inspector)
import { server, tokenServer, TOKEN_PORT } from "./server.js";

const MCP_PORT = parseInt(process.env.MCP_SERVER_PORT || "3000");
const log = (...args: any[]) => console.log("[mcp]", ...args);

async function main() {
  tokenServer.listen(TOKEN_PORT, () => log(`Token receiver on :${TOKEN_PORT}`));
  await server.start({ transportType: "httpStream", httpStream: { host: "0.0.0.0", port: MCP_PORT } });
  log(`MCP server on :${MCP_PORT}`);
}

main();
