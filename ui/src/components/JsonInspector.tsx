type Props = {
  value: unknown;
  emptyLabel?: string;
};

export function JsonInspector({ value, emptyLabel = "Nothing selected." }: Props) {
  if (value === null || value === undefined) {
    return <div className="empty-state">{emptyLabel}</div>;
  }
  return <pre className="json-inspector">{JSON.stringify(value, null, 2)}</pre>;
}
