import type { Metadata } from "next";
import "./globals.css";
import { Providers } from "./providers";

export const metadata: Metadata = {
  title: "Reviveo - AI Revenue Recovery for Razorpay Merchants",
  description:
    "Reviveo detects failed and at-risk Razorpay payments, diagnoses the root cause, and recovers revenue automatically — within guardrails you control, with a full audit trail.",
  openGraph: {
    title: "Reviveo - AI Revenue Recovery for Razorpay Merchants",
    description:
      "Detect failed payments, decide the right recovery action, and win back revenue — automatically and safely, built on Razorpay.",
    images: ["/hero-bg_image.png"],
    type: "website",
  },
  twitter: {
    card: "summary_large_image",
    title: "Reviveo - AI Revenue Recovery for Razorpay Merchants",
    description: "AI-powered revenue recovery for payments at risk, built on Razorpay.",
    images: ["/hero-bg_image.png"],
  },
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className="h-full antialiased">
      <body className="min-h-full flex flex-col">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
