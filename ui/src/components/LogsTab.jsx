export default function LogsTab({ logs }) {
  return (
    <textarea
      className="w-full h-96 border p-2"
      value={logs?.join("\n\n") || ""}
      readOnly
    />
  );
}