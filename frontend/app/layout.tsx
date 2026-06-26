import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Painting Instructor — AI Art Tutor",
  description: "Upload a photo. Get a complete painting tutorial: outlines, value study, colour blocking, and a progressive video showing every step.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="h-full">
      <body className="min-h-full flex flex-col">{children}</body>
    </html>
  );
}
