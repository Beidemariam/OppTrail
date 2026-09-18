import { AppRoot } from "../AppRoot";

/**
 * The whole application is one statically exported shell (ADR 0005).
 *
 * `next.config.ts` sets `output: "export"`, so Next emits files, not routes.
 * This optional catch-all emits only the root, which becomes `out/index.html`;
 * FastAPI serves that same file for any path it does not recognise
 * (`backend/app/main.py`'s `serve_frontend`), so a deep link such as `/search`
 * loads the shell and the client router in `AppRoot` takes it from there.
 *
 * Routing therefore lives in React Router, not in this directory. Adding a
 * second Next route here would emit a second HTML file and split the SPA.
 */
export function generateStaticParams() {
  return [{ slug: [] as string[] }];
}

export default function Page() {
  return <AppRoot />;
}
