import "./globals.css";

import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Prediction Market Arbitrage Scanner",
  description: "Read-only dashboard for estimated binary prediction-market arbitrage."
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
