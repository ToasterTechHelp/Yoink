"use client";

interface CategoryFilterProps {
  categories: string[];
  active: Set<string>;
  onChange: (active: Set<string>) => void;
}

const CATEGORY_COLORS: Record<string, string> = {
  text: "bg-orange-500",
  figure: "bg-orange-500",
  misc: "bg-orange-500",
};

export function CategoryFilter({
  categories,
  active,
  onChange,
}: CategoryFilterProps) {
  const toggle = (cat: string) => {
    const next = new Set(active);
    if (next.has(cat)) {
      next.delete(cat);
    } else {
      next.add(cat);
    }
    onChange(next);
  };

  return (
    <div className="flex flex-wrap gap-2">
      {categories.map((cat) => {
        const isActive = active.has(cat);
        return (
          <button
            key={cat}
            onClick={() => toggle(cat)}
            className={`flex items-center gap-1.5 rounded-md px-2.5 py-1 text-xs font-medium capitalize transition-colors ${
              isActive
                ? "bg-muted text-foreground"
                : "bg-muted/50 text-muted-foreground"
            }`}
          >
            <span
              className={`h-3 w-3 rounded-sm ${
                isActive
                  ? CATEGORY_COLORS[cat] || "bg-orange-500"
                  : "bg-muted-foreground/30"
              }`}
            />
            {cat}
          </button>
        );
      })}
    </div>
  );
}
