import { useState } from "react";

export default function Sidebar({ onGenerate }) {
  const [topic, setTopic] = useState("");

  return (
    <div className="w-80 bg-gray-100 p-4 h-screen border-r">
      <h2 className="text-xl font-bold mb-4">Generate Blog</h2>

      <textarea
        className="w-full p-2 border rounded mb-4"
        rows="5"
        placeholder="Enter blog topic..."
        value={topic}
        onChange={(e) => setTopic(e.target.value)}
      />

      <button
        onClick={() => onGenerate(topic)}
        className="w-full bg-blue-600 text-white py-2 rounded hover:bg-blue-700"
      >
        🚀 Generate
      </button>
    </div>
  );
}