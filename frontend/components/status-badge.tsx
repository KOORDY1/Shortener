import { badgeLabel } from "@/lib/labels";

type Props = {
  value: string;
  className?: string;
};

export function StatusBadge({ value, className }: Props) {
  const key = value.toLowerCase();
  return (
    <span className={`badge ${key} ${className ?? ""}`.trim()} title={value}>
      {badgeLabel(value)}
    </span>
  );
}
