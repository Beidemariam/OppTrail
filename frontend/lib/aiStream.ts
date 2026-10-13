import { csrfToken } from "./api";

/**
 * Reading a streamed answer (milestone 6.4, `docs/FEATURES.md` §14).
 *
 * The other stream in this app — ADR 0003's live updates — is a GET read by
 * `EventSource`, carries invalidations and never content, and stays open as
 * long as a screen does. This one is the opposite on every count: it carries
 * the answer, is answered once, and needs a request body (the question),
 * which `EventSource` cannot send. So it is `fetch` plus a reader, and the
 * framing is SSE only because the two halves of the reply have to be told
 * apart: `delta` is text as it is written, `done` carries the citations,
 * which are computed from the finished answer and so cannot arrive earlier.
 *
 * Why streaming at all: D-168 measured this deployment's model at a ~29s
 * floor and 40.1s for a long deal. Forty seconds of spinner is
 * indistinguishable from a broken button, and the human's own report at the
 * Phase 4 gate was exactly that. Nothing about the answer changes.
 *
 * It does **not** go through `apiRequest`: that wrapper reads a JSON body and
 * throws on a non-2xx, which is the right shape for every other call in the
 * app and the wrong one for a response read in pieces. What it borrows is the
 * two things that make a request this app's own — the session cookie and the
 * CSRF header.
 */
export interface AiStreamHandlers {
  onDelta: (text: string) => void;
  onDone: (answer: string, referencedEntryNumbers: number[]) => void;
  onError: (message: string) => void;
}

export interface AiStreamRequest {
  question: string;
  since?: string;
  until?: string;
}

export async function streamAiAnswer(
  opportunityId: number,
  request: AiStreamRequest,
  handlers: AiStreamHandlers,
  signal?: AbortSignal,
): Promise<void> {
  let response: Response;
  try {
    response = await fetch(
      `/api/v2/opportunities/${opportunityId}/ai/ask/stream`,
      {
        method: "POST",
        credentials: "include",
        headers: {
          "Content-Type": "application/json",
          "X-CSRF-Token": csrfToken(),
        },
        body: JSON.stringify(request),
        signal,
      },
    );
  } catch {
    handlers.onError("AI service is unavailable");
    return;
  }

  // A refusal still arrives as an ordinary status with an ordinary envelope:
  // the permission check and the context read both happen before the
  // response starts, so there is no such thing here as a 200 that turns out
  // to be a 404.
  if (!response.ok || !response.body) {
    handlers.onError(await errorMessage(response));
    return;
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) {
        break;
      }
      buffer += decoder.decode(value, { stream: true });
      // A frame ends at a blank line. Anything after the last one is a
      // partial frame and stays in the buffer — a chunk boundary falls
      // wherever the network puts it, not where the message ends.
      const frames = buffer.split("\n\n");
      buffer = frames.pop() ?? "";
      for (const frame of frames) {
        dispatch(frame, handlers);
      }
    }
  } catch {
    // An aborted read is the reader navigating away, not a failure to
    // report: the caller that aborted already knows.
    if (!signal?.aborted) {
      handlers.onError("The answer stopped part way through");
    }
  }
}

/** One SSE frame, as the event it names. */
function dispatch(frame: string, handlers: AiStreamHandlers): void {
  let event = "";
  const data: string[] = [];
  for (const line of frame.split("\n")) {
    if (line.startsWith("event: ")) {
      event = line.slice(7);
    } else if (line.startsWith("data: ")) {
      // Rejoined with a newline, which is how a multi-line payload travels:
      // the server splits an answer's paragraphs across `data:` lines
      // because the spec gives it no other way to carry them.
      data.push(line.slice(6));
    }
  }
  const payload = data.join("\n");

  if (event === "delta") {
    handlers.onDelta(payload);
    return;
  }
  if (event === "error") {
    handlers.onError(payload || "AI service is unavailable");
    return;
  }
  if (event === "done") {
    try {
      const parsed = JSON.parse(payload) as {
        answer?: string;
        referenced_entry_numbers?: number[];
      };
      handlers.onDone(
        parsed.answer ?? "",
        parsed.referenced_entry_numbers ?? [],
      );
    } catch {
      handlers.onError("The answer could not be read");
    }
  }
}

async function errorMessage(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { error?: { message?: string } };
    return body.error?.message ?? "AI service is unavailable";
  } catch {
    return "AI service is unavailable";
  }
}
