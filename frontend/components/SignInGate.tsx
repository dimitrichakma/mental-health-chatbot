"use client";

import { signIn } from "next-auth/react";

export default function SignInGate() {
  return (
    <div className="flex flex-1 items-center justify-center px-4">
      <div className="w-full max-w-sm rounded-2xl border border-black/10 bg-[var(--background)] p-8 text-center shadow-sm dark:border-white/10">
        <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-br from-emerald-700 to-sky-600 text-3xl text-white shadow-lg shadow-emerald-900/20">
          🌿
        </div>
        <h1 className="mt-4 text-lg font-bold">CBT &amp; Mental Health Companion</h1>
        <p className="mt-1.5 text-sm text-neutral-500 dark:text-neutral-400">
          Sign in to start a conversation and keep it saved to your account.
        </p>

        <button
          onClick={() => signIn("google")}
          className="mt-6 flex w-full items-center justify-center gap-2 rounded-xl border border-black/10 bg-white px-4 py-2.5 text-sm font-medium text-neutral-800 shadow-sm transition hover:bg-neutral-50 dark:border-white/15 dark:bg-white/5 dark:text-neutral-100 dark:hover:bg-white/10"
        >
          <GoogleIcon />
          Continue with Google
        </button>

        <p className="mt-5 text-xs text-neutral-500 dark:text-neutral-400">
          Educational project, not medical advice. If you are in crisis,
          contact a local crisis line or emergency services.
        </p>
      </div>
    </div>
  );
}

function GoogleIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 18 18" aria-hidden="true">
      <path
        fill="#4285F4"
        d="M17.64 9.2c0-.64-.06-1.25-.16-1.84H9v3.48h4.84a4.14 4.14 0 0 1-1.8 2.72v2.26h2.9c1.7-1.57 2.68-3.88 2.68-6.62z"
      />
      <path
        fill="#34A853"
        d="M9 18c2.43 0 4.47-.8 5.96-2.18l-2.9-2.26c-.8.54-1.84.86-3.06.86-2.35 0-4.34-1.59-5.05-3.72H.95v2.33A9 9 0 0 0 9 18z"
      />
      <path
        fill="#FBBC05"
        d="M3.95 10.7A5.4 5.4 0 0 1 3.67 9c0-.59.1-1.17.28-1.7V4.97H.95A9 9 0 0 0 0 9c0 1.45.35 2.83.95 4.03l3-2.33z"
      />
      <path
        fill="#EA4335"
        d="M9 3.58c1.32 0 2.51.45 3.44 1.35l2.58-2.58C13.46.89 11.43 0 9 0A9 9 0 0 0 .95 4.97l3 2.33C4.66 5.17 6.65 3.58 9 3.58z"
      />
    </svg>
  );
}
