import type { ReactNode } from "react";

export const metadata = {
  title: "AI Lead Recovery",
  description: "Recover missed-call leads automatically.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body
        style={{
          fontFamily: "system-ui, sans-serif",
          margin: 0,
          background: "#0b1020",
          color: "#e7ecf5",
        }}
      >
        {children}
      </body>
    </html>
  );
}
