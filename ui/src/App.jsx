import { useState } from "react";
import Sidebar from "./components/Sidebar";
import Tabs from "./components/Tabs";
import PlanTab from "./components/PlanTab";
import EvidenceTab from "./components/EvidenceTab";
import PreviewTab from "./components/PreviewTab";
import LogsTab from "./components/LogsTab";
import { generateBlog } from "./api/blogApi";

function App() {
  const [data, setData] = useState(null);
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(false);

  const handleGenerate = async (topic) => {
    if (!topic) return alert("Enter topic");

    try {
      setLoading(true);
      setLogs((prev) => [...prev, "Starting blog generation..."]);
      const res = await generateBlog(topic);
      setData(res);
      setLogs((prev) => [...prev, "Blog generated successfully"]);
    } catch (err) {
      console.error(err);
      setLogs((prev) => [...prev, "Error generating blog"]);
    } finally {
      setLoading(false);
    }
  };

  const tabs = {
    "🧩 Plan": <PlanTab plan={data?.plan} />,
    "🔎 Evidence": <EvidenceTab evidence={data?.evidence} />,
    "📝 Preview": (
      <PreviewTab content={data?.content} title={data?.blog_title} />
    ),
    "🧾 Logs": <LogsTab logs={logs} />,
  };

  return (
    <div className="flex">
      <Sidebar onGenerate={handleGenerate} />
      {loading ? (
        <div className="flex-1 flex items-center justify-center text-xl">
          Generating...
        </div>
      ) : (
        <Tabs tabs={tabs} />
      )}
    </div>
  );
}

export default App;