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

// jsdom implements no ResizeObserver, and `useStickyChrome` (the record
// band publishing how far the sticky chrome reaches, for `scroll-padding-top`
// and WCAG 2.2's 2.4.11) constructs one on mount. A no-op is the honest stub
// rather than a thin one: jsdom never lays anything out, so an observer here
// would have no resize to report and the height it published would be the
// 600px fixture above rather than a measurement. What the hook computes is
// unit-tested without a DOM through `lib/nav.ts`'s `stuckBottom`, and the
// value the browser actually ends up using is asserted at eleven widths by
// `e2e/30-focus-and-keyboard.spec.ts`.
class NoopResizeObserver implements ResizeObserver {
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
}
window.ResizeObserver = NoopResizeObserver;

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

// The same absence, for ProseMirror (the rich composer, milestone 3.1): it
// asks where the caret is on screen — to keep it in view after a change, and
// to turn a mouse position into a document position — and jsdom answers
// neither question. `Text` and `Range` in particular implement no geometry at
// all, and ProseMirror measures both — a caret between two characters is a
// collapsed range. These stubs make those reads answer zero rather than throw;
// where the caret actually goes is asserted in `e2e/18-rich-text.spec.ts`,
// which has a real layout.
const emptyRect = {
  bottom: 0,
  height: 0,
  left: 0,
  right: 0,
  top: 0,
  width: 0,
};
document.elementFromPoint = () => null;
for (const geometryless of [window.Text.prototype, window.Range.prototype]) {
  Object.assign(geometryless, {
    getBoundingClientRect: () => emptyRect,
    getClientRects: () => [],
  });
}
