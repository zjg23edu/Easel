import { definePluginEntry } from "openclaw/plugin-sdk/plugin-entry";
import { normalizeWebSearchParams } from "./search-query.js";

export default definePluginEntry({
  id: "easel-search-query",
  name: "Easel search query",
  description: "Trim leaked web_search queries and drop site: when a domain filter is already set.",
  register(api) {
    api.on("before_tool_call", async (event) => {
      if (event.toolName !== "web_search") return;
      const params = normalizeWebSearchParams(event.params);
      if (!params) return;
      api.logger?.info?.(`easel-search-query: query ${String(event.params?.query ?? "").length} -> ${params.query.length}`);
      return { params };
    });
  },
});
