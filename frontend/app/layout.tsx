import type { Metadata } from "next";
import "./globals.css";

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
          <nav className="bg-white border-b border-gray-200 shadow-sm sticky top-0 z-50">
            <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
              <div className="flex justify-between h-16">
                <div className="flex">
                  <div className="flex-shrink-0 flex items-center">
                    <div className="flex items-center space-x-3">
                      <div className="w-10 h-10 bg-gradient-to-br from-indigo-500 to-purple-600 rounded-lg flex items-center justify-center">
                        <span className="text-white text-2xl">💰</span>
                      </div>
                      <h1 className="text-xl font-bold text-gray-900">
                        Finance Manager
                      </h1>
                    </div>
                  </div>
                  <div className="hidden sm:ml-12 sm:flex sm:space-x-1">
                    <a
                      href="/"
                      className="border-indigo-500 text-indigo-600 inline-flex items-center px-4 py-2 border-b-2 text-sm font-medium transition-colors hover:text-indigo-700"
                    >
                      Dashboard
                    </a>
                    <a
                      href="/imports"
                      className="border-transparent text-gray-600 hover:border-gray-300 hover:text-gray-900 inline-flex items-center px-4 py-2 border-b-2 text-sm font-medium transition-colors"
                    >
                      Import
                    </a>
                    <a
                      href="/transactions"
                      className="border-transparent text-gray-600 hover:border-gray-300 hover:text-gray-900 inline-flex items-center px-4 py-2 border-b-2 text-sm font-medium transition-colors"
                    >
                      Transactions
                    </a>
                  </div>
                </div>
              </div>
            </div>
          </nav>
          <main className="py-8">{children}</main>
        </div>
      </body>
    </html>
  );
}
