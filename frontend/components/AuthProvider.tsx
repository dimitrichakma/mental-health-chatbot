"use client";

import { SessionProvider } from "next-auth/react";

// Thin client-boundary wrapper so app/layout.tsx (a server component) can
// still provide session context to everything below it - SessionProvider
// itself uses React context/hooks and must run client-side.
export default function AuthProvider({
  children,
}: {
  children: React.ReactNode;
}) {
  return <SessionProvider>{children}</SessionProvider>;
}
