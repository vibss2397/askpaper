/* SSE stream parsing for the ask endpoint.
 *
 * Ported from raycast-extensions/paper-agent/src/ask.tsx (migration plan §5.3):
 * events are separated by \n\n, \r\n is normalized to \n, multiple `data:`
 * lines within one event are joined with \n.
 *
 * Kept free of DOM dependencies so it can be unit-tested with `bun test`.
 */
(function (global) {
  "use strict";

  function sseFeed(buffer, chunk) {
    buffer += chunk.replace(/\r\n/g, "\n");
    const parts = buffer.split("\n\n");
    const rest = parts.pop() || "";
    const events = [];
    for (const part of parts) {
      const dataLines = [];
      for (const line of part.split("\n")) {
        if (line.startsWith("data: ")) dataLines.push(line.slice(6));
      }
      if (dataLines.length > 0) events.push(dataLines.join("\n"));
    }
    return { events: events, buffer: rest };
  }

  /* Classify one joined `data:` payload into a structured event.
   * errorPending is true after an `[ERROR]` sentinel — the server then sends
   * the error detail as a JSON object (server.py error path), which would
   * otherwise be indistinguishable from a raw answer token. */
  function classifyEvent(data, errorPending) {
    if (data === "[DONE]") return { type: "done" };
    if (data === "[ERROR]") return { type: "error_sentinel" };
    if (data.charAt(0) === "{") {
      try {
        const obj = JSON.parse(data);
        if (typeof obj.status === "string") return { type: "status", obj: obj };
        if (typeof obj.session_path === "string") return { type: "session_path", path: obj.session_path };
        if (errorPending && obj && typeof obj.error === "string") return { type: "error_detail", message: obj.error };
      } catch (e) {
        /* not valid JSON — treat as a raw token */
      }
    }
    return { type: "token", text: data };
  }

  const SSE = { sseFeed: sseFeed, classifyEvent: classifyEvent };
  global.SSE = SSE;
  if (typeof module !== "undefined" && module.exports) module.exports = SSE;
})(typeof window !== "undefined" ? window : globalThis);
