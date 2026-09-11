export default function Header() {
  return (
    <div className="mb-3">
      <div className="flex items-center gap-3 rounded-2xl bg-gradient-to-br from-emerald-700 to-sky-600 px-6 py-5 text-white shadow-lg shadow-emerald-900/20">
        <div className="flex h-11 w-11 flex-none items-center justify-center rounded-xl bg-white/20 text-2xl">
          🌿
        </div>
        <div>
          <h1 className="text-lg font-bold leading-tight sm:text-xl">
            CBT &amp; Mental Health Chatbot
          </h1>
          <p className="mt-1 text-sm text-white/90">
            Ask about cognitive behavioral therapy, common mental-health
            conditions, and coping skills — answered from a curated knowledge
            base and concept graph.
          </p>
        </div>
      </div>
      <div className="mt-2.5 flex items-start gap-2 rounded-lg bg-black/[0.04] px-3 py-2 text-xs text-neutral-600 dark:bg-white/[0.06] dark:text-neutral-400">
        <span>ℹ️</span>
        <span>
          Educational project, not medical advice or a substitute for
          professional care. If you are in crisis, contact a local crisis
          line or emergency services.
        </span>
      </div>
    </div>
  );
}
