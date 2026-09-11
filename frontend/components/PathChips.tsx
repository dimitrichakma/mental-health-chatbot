import { pathLabel } from "@/lib/constants";
import type { PathUsed } from "@/lib/types";

export default function PathChips({ paths }: { paths?: PathUsed[] }) {
  if (!paths || paths.length === 0) return null;
  return (
    <div className="mt-2 flex flex-wrap items-center gap-1.5 text-xs text-neutral-500 dark:text-neutral-400">
      <span>Sources:</span>
      {paths.map((p, i) => {
        const { icon, label } = pathLabel(p);
        return (
          <span
            key={`${p}-${i}`}
            className="inline-flex items-center gap-1 rounded-full bg-sky-600/10 px-2.5 py-0.5 font-medium text-sky-700 dark:bg-sky-400/10 dark:text-sky-300"
          >
            {icon} {label}
          </span>
        );
      })}
    </div>
  );
}
