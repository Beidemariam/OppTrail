# 0005. Client-side SPA with TanStack Query; keep the static export

Status: Accepted (v2)

## Context

`frontend/app/page.tsx` is a single 1,829-line `"use client"` component with 28
`useState` hooks, no router, and a hand-rolled `apiRequest` wrapper. There is no
cache, no deduplication, no optimistic update, and the mutation pattern is "await
the write, then refetch everything." Views switch on component state, so there are
no URLs.

`next.config.ts` sets `output: "export"`, so **no Next.js server feature is in use**
— no SSR, no server components, no API routes, no image optimization. Next is
currently a bundler.

This is the review's blocker B1 and the main obstacle to every Phase 2 feature.

## Options

1. **Next.js server components + a Node server.** Real data fetching on the server,
   streaming, less client JS. Requires running Node alongside Python in the
   container, or splitting into two deploy units.
2. **Keep the static export; add a client router and TanStack Query.** Next stays a
   bundler. FastAPI keeps serving the bundle and the API from one origin.
3. **Replace Next with Vite + React Router.** Honest about what the app is, smaller
   toolchain, but a migration that buys no user-visible capability.

## Decision

**Option 2.** Option 1 puts two runtimes in one container to serve 20 users and
breaks the single-origin, single-process deployment that ADR 0011 keeps — a large
operational cost for a benefit (server rendering) that nobody at this scale will
perceive. Option 3 is a week of work whose only product is a different build tool.

Implementation:

- Collapse the route tree to a single optional catch-all (`app/[[...slug]]/page.tsx`)
  with `generateStaticParams` emitting only the root. **This already works** because
  `main.py:56-64` serves `index.html` for any unmatched path, so deep links like
  `/opportunities/12/board` load the shell and the client router takes over.
- **React Router** for client-side routing. URL becomes the source of truth for
  selected opportunity, active view, and filters — which is what makes saved views,
  deep links and the back button possible.
- **TanStack Query** for all server state: caching, deduplication, invalidation on
  SSE events (ADR 0003), and optimistic mutations.
- Decompose `page.tsx` into routed views and feature components. State that is local
  to a comment box must live in the comment box.

## Consequences

- Two new frontend dependencies, both boring and dominant in their niche.
- Next.js is retained but explicitly demoted to a build tool. Documented so nobody
  later assumes SSR is available. Revisit only if server rendering is ever wanted.
- The decomposition is invisible to users, which conflicts with the roadmap rule
  that every phase ship something demoable. Resolved by folding it into the first
  view-adding phase — see `ROADMAP.md`.
