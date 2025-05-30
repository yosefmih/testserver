import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Audio Processor",
  description: "Upload audio files for processing",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>
        {children}
      </body>
    </html>
  );
}
