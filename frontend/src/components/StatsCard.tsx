import clsx from "clsx";
import { LucideIcon } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";

interface StatsCardProps {
  title: string;
  value: string | number;
  icon: LucideIcon;
  trend?: {
    value: number;
    isPositive: boolean;
  };
  color?: "blue" | "green" | "red" | "yellow";
}

const colorClasses = {
  blue: "border border-[var(--ph-border)] bg-[var(--ph-bg-elevated)] text-[var(--ph-accent)]",
  green:
    "border border-[var(--ph-border)] bg-[var(--ph-bg-elevated)] text-emerald-400",
  red: "border border-[var(--ph-border)] bg-[var(--ph-bg-elevated)] text-rose-400",
  yellow:
    "border border-[var(--ph-border)] bg-[var(--ph-bg-elevated)] text-amber-400",
};

export default function StatsCard({
  title,
  value,
  icon: Icon,
  trend,
  color = "blue",
}: StatsCardProps) {
  return (
    <Card>
      <CardContent className="p-4 md:p-5">
        <div className="flex items-center gap-3">
          <div className={clsx("rounded-lg border p-2.5", colorClasses[color])}>
            <Icon className="h-5 w-5" />
          </div>
          <div className="min-w-0 flex-1">
            <p className="text-xs font-medium text-[var(--ph-muted)]">
              {title}
            </p>
            <div className="mt-1 flex items-baseline gap-2">
              <p className="text-2xl font-semibold text-[var(--ph-text)]">
                {value}
              </p>
              {trend && (
                <Badge
                  className="ml-0"
                  variant={trend.isPositive ? "success" : "destructive"}
                >
                  {trend.isPositive ? "+" : "-"}
                  {Math.abs(trend.value)}%
                </Badge>
              )}
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
