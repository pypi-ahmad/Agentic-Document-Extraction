import { afterEach, describe, expect, it, vi } from "vitest";

import { parseDocument } from "./api";

afterEach(() => vi.unstubAllGlobals());

describe("stateless parsing", () => {
  it("posts the document directly to the parse endpoint", async () => {
    const payload = { markdown: "text", metadata: {}, structure: {} };
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(payload), { headers: { "Content-Type": "application/json" } }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await parseDocument(new File(["document"], "sample.pdf"), "paperplane-ade-latest");

    expect(fetchMock).toHaveBeenCalledOnce();
    expect(fetchMock.mock.calls[0][0]).toBe("/api/v2/parse");
    expect(fetchMock.mock.calls[0][1]).toMatchObject({ method: "POST", cache: "no-store" });
  });
});
