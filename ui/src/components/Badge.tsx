type Props = {
  children: React.ReactNode;
  tone?: "neutral" | "positive" | "negative" | "warning" | "accent";
};

export function Badge({ children, tone = "neutral" }: Props) {
  return <span className={`badge badge-${tone}`}>{children}</span>;
}
