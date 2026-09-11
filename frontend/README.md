# frontend

Next.js + Tailwind chat UI for the CBT/mental-health chatbot. Deliberately
standalone - its own `package.json`/lockfile, no dependency on the backend's
Python code (see `../Dockerfile.frontend`).

```bash
cp .env.local.example .env.local   # fill in the auth values
npm install
npm run dev          # -> http://localhost:3000, talks to NEXT_PUBLIC_BACKEND_URL
                      #    (defaults to http://localhost:8000)
```

`NEXT_PUBLIC_BACKEND_URL` is a build-time value (Next.js inlines
`NEXT_PUBLIC_*` vars into the client bundle) - set it in `.env.local` for
`npm run dev`, or via `--build-arg BACKEND_URL=...` / a Railway service
variable named `BACKEND_URL` for Docker builds (see the root README's
Deployment section). `AUTH_*` and `BACKEND_JWT_SECRET` are plain runtime env
vars (no build-time baking needed) - see `.env.local.example`.

Layout: `app/` (page + layout + global styles + `api/auth`, `api/backend-token`
route handlers), `components/` (Header, Sidebar, SignInGate, AuthProvider,
MessageBubble, FeedbackRow, PathChips, ThemeToggle), `lib/` (API client,
shared constants/types), `auth.ts` (Auth.js config - Google sign-in).
