import { useId } from "react";

import { Badge } from "@/components/ui/badge";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";

export function SettingToggleField({
  label,
  description,
  checked,
  checkedLabel,
  uncheckedLabel,
  badgeLabel,
  onChange,
}: {
  label: string;
  description: string;
  checked: boolean;
  checkedLabel: string;
  uncheckedLabel: string;
  badgeLabel: string;
  onChange: (value: boolean) => void;
}) {
  const switchId = useId();
  const descriptionId = `${switchId}-description`;
  const stateId = `${switchId}-state`;
  const stateLabel = checked ? checkedLabel : uncheckedLabel;

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-3">
        <div>
          <Label
            htmlFor={switchId}
            className="cursor-pointer text-sm font-medium text-[var(--ph-text)]"
          >
            {label}
          </Label>
          <p
            id={descriptionId}
            className="mt-1 text-xs leading-5 text-[var(--ph-muted)]"
          >
            {description}
          </p>
        </div>
        <Badge variant="outline">{badgeLabel}</Badge>
      </div>
      <div className="flex items-center gap-3">
        <Switch
          id={switchId}
          checked={checked}
          onCheckedChange={onChange}
          aria-describedby={`${descriptionId} ${stateId}`}
        />
        <span
          id={stateId}
          aria-live="polite"
          className="text-sm text-[var(--ph-text)]"
        >
          <span className="sr-only">Current state: </span>
          {stateLabel}
        </span>
      </div>
    </div>
  );
}
