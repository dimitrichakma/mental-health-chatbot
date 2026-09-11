import NextAuth from "next-auth";
import Google from "next-auth/providers/google";

// Session strategy is JWT (default with no database adapter configured) - no
// DB access from the frontend at all, keeping the "frontend deploys
// standalone" boundary. The session cookie only proves who's signed in to
// *this* Next.js app; it's never sent to the backend. See
// app/api/backend-token/route.ts for how the backend actually verifies a
// caller's identity.
export const { handlers, auth, signIn, signOut } = NextAuth({
  providers: [Google],
  callbacks: {
    // Google's stable per-account id (the JWT's `sub` claim from the OAuth
    // token) becomes our durable user id - it's what threads/conversation_log
    // get keyed by server-side, so it needs to survive onto the session.
    async jwt({ token, account }) {
      if (account) token.sub = account.providerAccountId;
      return token;
    },
    async session({ session, token }) {
      if (session.user && token.sub) {
        (session.user as { id?: string }).id = token.sub;
      }
      return session;
    },
  },
});
