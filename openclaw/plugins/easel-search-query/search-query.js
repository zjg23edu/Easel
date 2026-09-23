const MAX_QUERY = 400;
const LEAK = /to=functions\.|to=multi_tool_use\.|\(commentary\)/;
const SITE = /(?:^|\s)site:(?:"[^"]+"|\S+)/gi;

function domainFilterActive(value) {
  if (Array.isArray(value)) return value.some((item) => String(item ?? "").trim());
  if (typeof value === "string") return value.trim().length > 0;
  return false;
}

function cleanQuery(query) {
  const lines = query.replace(/\r\n/g, "\n").split("\n");
  const nonempty = lines.map((line) => line.trim()).filter(Boolean);
  const leaked = LEAK.test(query) || lines.length - nonempty.length > 5;
  const body = leaked ? (nonempty[0] || "") : nonempty.join(" ");
  return body.replace(/\s+/g, " ").trim();
}

/** Return rewritten params, or null when the call can be sent unchanged. */
export function normalizeWebSearchParams(params) {
  if (!params || typeof params.query !== "string") return null;
  let query = cleanQuery(params.query);
  const filter = params.domain_filter ?? params.domainFilter;
  if (domainFilterActive(filter)) {
    const stripped = query.replace(SITE, " ").replace(/\s+/g, " ").trim();
    if (stripped) query = stripped;
  }
  if (query.length > MAX_QUERY) query = query.slice(0, MAX_QUERY).trim();
  if (!query || query === params.query) return null;
  return { ...params, query };
}
