import assert from "node:assert/strict";
import test from "node:test";
import { normalizeWebSearchParams } from "./search-query.js";

test("a leaked tool call and blank lines keep the first search line", () => {
  const query = [
    "Anthropic Claude Opus new model September 22 2026 release announcement",
    "",
    "Need maybe web search. to=functions.web_search (commentary)",
    ...Array(20).fill(""),
    "2 json {",
  ].join("\n");
  const params = normalizeWebSearchParams({
    query,
    domain_filter: ["anthropic.com"],
    count: 5,
  });
  assert.equal(params.query, "Anthropic Claude Opus new model September 22 2026 release announcement");
  assert.equal(params.count, 5);
  assert.deepEqual(params.domain_filter, ["anthropic.com"]);
});

test("site path is removed when a domain filter is already set", () => {
  const params = normalizeWebSearchParams({
    query: "site:anthropic.com/news Claude Opus September 22 2026 Anthropic announcement",
    domain_filter: ["anthropic.com"],
  });
  assert.equal(params.query, "Claude Opus September 22 2026 Anthropic announcement");
});

test("site operator stays when no domain filter is set", () => {
  const query = "site:xiaohongshu.com 竞品昵称";
  assert.equal(normalizeWebSearchParams({ query, domain_filter: [] }), null);
});

test("a normal short query is unchanged", () => {
  assert.equal(normalizeWebSearchParams({ query: "Claude Opus 5.5", count: 5 }), null);
});
