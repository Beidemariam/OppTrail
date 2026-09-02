export default function Home() {
  return (
    <main
      style={{
        alignItems: "center",
        display: "flex",
        minHeight: "100vh",
        padding: "48px 24px",
      }}
    >
      <section style={{ margin: "0 auto", maxWidth: 760, width: "100%" }}>
        <p
          style={{
            color: "#0F9D8C",
            fontSize: 14,
            fontWeight: 700,
            letterSpacing: 0,
            margin: "0 0 12px",
            textTransform: "uppercase",
          }}
        >
          OppTrail
        </p>
        <h1
          style={{
            color: "#0B2540",
            fontSize: 44,
            lineHeight: 1.1,
            margin: "0 0 16px",
          }}
        >
          Sales opportunity timelines, ready for Phase 1.
        </h1>
        <p
          style={{
            color: "#6B7280",
            fontSize: 18,
            lineHeight: 1.6,
            margin: 0,
          }}
        >
          The Phase 0 scaffold is serving this static NextJS page through
          FastAPI.
        </p>
      </section>
    </main>
  );
}
