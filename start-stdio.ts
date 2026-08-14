// Entry point for stdio mode (MCP Inspector)
import { server, tokenServer, TOKEN_PORT } from "./server.js";

const log = (...args: any[]) => console.error("[mcp]", ...args);

async function main() {
  tokenServer.listen(TOKEN_PORT, () => log(`Token receiver on :${TOKEN_PORT}`));
  await server.start({ transportType: "stdio" });
}

main();
