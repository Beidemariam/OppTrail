import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "OppTrail",
  description: "Timeline note-taking for sales opportunities",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
