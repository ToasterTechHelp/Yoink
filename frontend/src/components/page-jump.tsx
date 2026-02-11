"use client";

interface PageJumpProps {
  totalPages: number;
  onJump: (page: number) => void;
  currentPage?: number;
}

export function PageJump({ totalPages, onJump, currentPage }: PageJumpProps) {
  if (totalPages <= 1) return null;

  return (
    <div className="fixed bottom-6 left-4 right-4 z-40 flex justify-center">
      <div className="max-w-full overflow-x-auto rounded-full border bg-card px-3 py-2 shadow-lg">
        <div className="flex items-center gap-1">
          {Array.from({ length: totalPages }, (_, i) => i + 1).map((page) => (
            <button
              key={page}
              onClick={() => onJump(page)}
              className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-sm font-medium transition-colors ${
                currentPage === page
                  ? "bg-primary text-primary-foreground"
                  : "hover:bg-muted"
              }`}
            >
              {page}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
