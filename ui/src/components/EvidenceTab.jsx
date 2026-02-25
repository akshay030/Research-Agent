export default function EvidenceTab({ evidence }) {
  if (!evidence || evidence.length === 0)
    return <p>No evidence available.</p>;

  return (
    <ul className="space-y-2">
      {evidence.map((e, idx) => (
        <li key={idx} className="border p-3 rounded">
          <a
            href={e.url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-blue-600 font-semibold"
          >
            {e.title}
          </a>
          <p className="text-sm text-gray-500">{e.published_at}</p>
        </li>
      ))}
    </ul>
  );
}