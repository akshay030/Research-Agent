export default function PlanTab({ plan }) {
  if (!plan) return <p>No plan available.</p>;

  return (
    <div>
      <h2 className="text-2xl font-bold mb-2">{plan.blog_title}</h2>
      <p><strong>Audience:</strong> {plan.audience}</p>
      <p><strong>Tone:</strong> {plan.tone}</p>

      <h3 className="mt-4 font-semibold">Tasks:</h3>
      <ul className="list-disc ml-6">
        {plan.tasks?.map((t) => (
          <li key={t.id}>
            {t.title} ({t.target_words} words)
          </li>
        ))}
      </ul>
    </div>
  );
}