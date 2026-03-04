"use client";

import { Slider as SliderPrimitive } from "radix-ui";
import { cn } from "@/lib/utils";

const LABELS = ["Min", "Low", "Mid", "High", "Max"];
const FULL_NAMES = ["Fastest", "Fast", "Balanced", "Thorough", "Most Thorough"];
const DESCRIPTIONS = [
  "Only high-confidence detections, least noise",
  "Fewer, more precise detections",
  "Good balance of coverage and precision",
  "More inclusive, catches smaller elements",
  "Maximum coverage, may include noise",
];

export const PRESET_KEYS = [
  "fastest",
  "fast",
  "balanced",
  "thorough",
  "most_thorough",
] as const;

interface SensitivitySliderProps {
  value: number;
  onChange: (value: number) => void;
  disabled?: boolean;
}

export function SensitivitySlider({
  value,
  onChange,
  disabled,
}: SensitivitySliderProps) {
  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium">Detection Coverage</span>
        <span className="text-sm font-medium text-primary">
          {FULL_NAMES[value]}
        </span>
      </div>

      <SliderPrimitive.Root
        min={0}
        max={4}
        step={1}
        value={[value]}
        onValueChange={([v]) => onChange(v)}
        disabled={disabled}
        className={cn(
          "relative flex w-full touch-none items-center select-none",
          disabled && "opacity-50 pointer-events-none"
        )}
      >
        <SliderPrimitive.Track className="relative h-1.5 w-full grow overflow-hidden rounded-full bg-muted">
          <SliderPrimitive.Range className="absolute h-full bg-orange-500" />
        </SliderPrimitive.Track>
        <SliderPrimitive.Thumb className="block size-4 shrink-0 rounded-full border-2 border-orange-500 bg-white shadow-sm ring-orange-500/30 transition-[box-shadow] hover:ring-4 focus-visible:ring-4 focus-visible:outline-none" />
      </SliderPrimitive.Root>

      <div className="flex justify-between text-[10px] text-muted-foreground">
        {LABELS.map((label) => (
          <span key={label}>{label}</span>
        ))}
      </div>

      <p className="text-xs text-muted-foreground">{DESCRIPTIONS[value]}</p>
    </div>
  );
}
