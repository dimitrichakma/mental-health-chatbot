# frontend

Next.js + Tailwind chat UI for the CBT/mental-health chatbot. Deliberately
standalone - its own `package.json`/lockfile, no dependency on the backend's
Python code (see `../Dockerfile.frontend`).

```bash
npm install
npm run dev          # -> http://localhost:3000, talks to BACKEND_URL
                      #    (defaults to http://localhost:8000)
```

`NEXT_PUBLIC_BACKEND_URL` is a build-time value (Next.js inlines
`NEXT_PUBLIC_*` vars into the client bundle) - set it in `.env.local` for
`npm run dev`, or via `--build-arg BACKEND_URL=...` / a Railway service
variable named `BACKEND_URL` for Docker builds (see the root README's
Deployment section).

Layout: `app/` (page + layout + global styles), `components/` (Header,
Sidebar, MessageBubble, FeedbackRow, PathChips, ThemeToggle), `lib/` (API
client, identity/localStorage helpers, shared constants/types).
