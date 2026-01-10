import type { Metadata } from "next";
import "./globals.css";
import Navigation from "./components/Navigation";

export const metadata: Metadata = {
  title: "Personal Finance Manager",
  description: "Track your spending with automatic transaction classification",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className="antialiased">
        <div className="min-h-screen bg-gradient-to-br from-gray-50 to-gray-100">
          <Navigation />
          <main className="py-8">{children}</main>
        </div>
      </body>
    </html>
  );
}
