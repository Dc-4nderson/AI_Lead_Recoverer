import Link from "next/link";

export default function DevToolsPage() {
  return (
    <main style={{ maxWidth: 760, margin: "0 auto", padding: "64px 24px" }}>
      <h1 style={{ fontSize: 32, marginBottom: 8 }}>Developer Tools</h1>
      <p style={{ color: "#9fb0c9", marginTop: 0 }}>
        Internal tools for exercising the production backend without Twilio or real customers.
      </p>
      <ul style={{ lineHeight: 2 }}>
        <li>
          <Link href="/dev-tools/simulator" style={{ color: "#5a8fd6" }}>
            Workflow Simulator
          </Link>
        </li>
      </ul>
    </main>
  );
}
