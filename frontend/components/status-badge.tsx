type Props = {
  value: string;
  className?: string;
};

export function StatusBadge({ value, className }: Props) {
  return <span className={`badge ${value.toLowerCase()} ${className ?? ""}`.trim()}>{value}</span>;
}
