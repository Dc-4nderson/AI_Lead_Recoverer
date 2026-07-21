// Placeholder landing / onboarding entry (§1). The full onboarding wizard
// (account → verify → connect number → business info → calendar → AI tone →
// notifications → test → activate) builds out from here — each step is a route
// that calls the typed API client.
const ONBOARDING_STEPS = [
  "Create an account",
  "Verify email",
  "Connect or provision a business phone number",
  "Enter business information",
  "Connect calendar",
  "Customize AI tone and instructions",
  "Configure notification preferences",
  "Test the workflow",
  "Activate the system",
];

export default function Home() {
  return (
    <main style={{ maxWidth: 760, margin: "0 auto", padding: "64px 24px" }}>
      <h1 style={{ fontSize: 40, marginBottom: 8 }}>AI Lead Recovery</h1>
      <p style={{ color: "#9fb0c9", fontSize: 18, marginTop: 0 }}>
        Never lose a missed-call lead again. Onboard in minutes — no developer
        required.
      </p>

      <h2 style={{ marginTop: 48, fontSize: 22 }}>Guided onboarding</h2>
      <ol style={{ lineHeight: 1.9, color: "#cdd8ea" }}>
        {ONBOARDING_STEPS.map((step) => (
          <li key={step}>{step}</li>
        ))}
      </ol>

      <p style={{ marginTop: 40, color: "#6f7f99", fontSize: 14 }}>
        This is the MVP scaffold. The dashboard consumes the FastAPI backend via
        a typed client backed by the shared types package.
      </p>
    </main>
  );
}
