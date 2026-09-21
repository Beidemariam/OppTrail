import "@testing-library/jest-dom/vitest";

// Deterministic time zone (brief §6.5). A non-UTC zone is deliberate: the
// local/UTC conversions in lib/time.ts are exactly where an off-by-an-offset
// bug hides, and a UTC-only run would never see it.
process.env.TZ = "America/New_York";

// jsdom never lays anything out, so every element reports 0 for
// offsetHeight/offsetWidth. @tanstack/react-virtual (StageBoard's
// VirtualList, milestone 2.3) reads that as "the viewport is zero pixels",
// and correctly renders nothing into it -- which would otherwise make every
// opportunity card disappear from every test that touches the board. A
// plausible stub is the documented way to exercise a virtualizer under
// jsdom; a real browser measures the actual laid-out element instead.
Object.defineProperty(window.HTMLElement.prototype, "offsetHeight", {
  configurable: true,
  value: 600,
});
Object.defineProperty(window.HTMLElement.prototype, "offsetWidth", {
  configurable: true,
  value: 600,
});

// jsdom lays nothing out and so implements no scrolling either;
// `OpportunityPanel` scrolls itself into view when an opportunity is opened
// (milestone 2.7). The stub records nothing — what it does in a real browser
// is asserted by the E2E suite, which has a viewport to scroll.
window.HTMLElement.prototype.scrollIntoView = () => {};

// jsdom implements no media queries, and `ThemeProvider` (milestone 2.5) asks
// it for `prefers-color-scheme` on mount. The stub answers "light" and accepts
// listeners; `lib/theme.test.ts` covers the resolution both ways without a
// browser, and the E2E suite runs the real query under Playwright's
// `emulateMedia`.
Object.defineProperty(window, "matchMedia", {
  configurable: true,
  writable: true,
  value: (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addEventListener: () => {},
    removeEventListener: () => {},
    addListener: () => {},
    removeListener: () => {},
    dispatchEvent: () => false,
  }),
});
