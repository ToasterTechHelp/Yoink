import { Sparkles, GripHorizontal, Cloud } from "lucide-react";

const features = [
  {
    icon: Sparkles,
    title: "Smart Extraction",
    description:
      "Automatically identifies and crops diagrams from lecture slides.",
  },
  {
    icon: GripHorizontal,
    title: "Drag & Drop Ready",
    description:
      "Perfect for split-screen multitasking on iPad with GoodNotes.",
  },
  {
    icon: Cloud,
    title: "Cloud Sync",
    description: "Access your extracted components from any device.",
  },
];

export function FeatureCards() {
  return (
    <div className="space-y-3">
      {features.map((f) => (
        <div
          key={f.title}
          className="flex items-start gap-3 rounded-xl border p-4"
        >
          <div className="mt-0.5">
            <f.icon className="h-5 w-5 text-orange-500" />
          </div>
          <div>
            <h3 className="font-semibold text-sm">{f.title}</h3>
            <p className="text-sm text-muted-foreground">{f.description}</p>
          </div>
        </div>
      ))}
    </div>
  );
}
