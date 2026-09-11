import jwt from "jsonwebtoken";
import { auth } from "@/auth";

// Mints a short-lived HS256 token the browser attaches as `Authorization:
// Bearer <token>` on every FastAPI call (see lib/api.ts). This runs
// server-side in Next.js, so it can call auth() (verifies the NextAuth
// session cookie, which never leaves this app) before handing out anything -
// the backend then trusts this token's signature instead of needing to know
// anything about NextAuth. BACKEND_JWT_SECRET is a plain shared secret set
// on both Railway services (see src/auth.py on the backend side).
const SECRET = process.env.BACKEND_JWT_SECRET;

export async function GET() {
  const session = await auth();
  const userId = (session?.user as { id?: string } | undefined)?.id;
  if (!session?.user || !userId) {
    return Response.json({ error: "not signed in" }, { status: 401 });
  }
  if (!SECRET) {
    return Response.json({ error: "server misconfigured" }, { status: 500 });
  }

  const token = jwt.sign(
    { sub: userId, email: session.user.email, name: session.user.name },
    SECRET,
    { algorithm: "HS256", expiresIn: "10m" }
  );
  return Response.json({ token });
}
