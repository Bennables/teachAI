import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "TeachOnce",
  description: "Teach an agent with one video"
};

export default function RootLayout({
  children
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
