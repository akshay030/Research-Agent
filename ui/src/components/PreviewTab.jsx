import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

export default function PreviewTab({ content, title }) {
  if (!content) return <p>No content yet.</p>;

  const downloadMarkdown = () => {
    const blob = new Blob([content], { type: "text/markdown" });
    const url = URL.createObjectURL(blob);

    const a = document.createElement("a");
    a.href = url;
    a.download = `${title || "blog"}.md`;
    a.click();
  };

  return (
    <div>
      <button
        onClick={downloadMarkdown}
        className="mb-4 bg-green-600 text-white px-4 py-2 rounded hover:bg-green-700"
      >
        ⬇️ Download Markdown
      </button>

      <div className="prose max-w-none">
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          components={{
            a: ({ node, ...props }) => (
              <a
                {...props}
                target="_blank"
                rel="noopener noreferrer"
                className="text-blue-600 underline font-medium hover:text-blue-800"
              />
            ),
            h1: ({ node, ...props }) => (
              <h1 className="text-3xl font-bold mt-6 mb-4" {...props} />
            ),
            h2: ({ node, ...props }) => (
              <h2 className="text-2xl font-semibold mt-5 mb-3" {...props} />
            ),
            h3: ({ node, ...props }) => (
              <h3 className="text-xl font-semibold mt-4 mb-2" {...props} />
            ),
            p: ({ node, ...props }) => (
              <p className="mb-3 leading-relaxed" {...props} />
            ),
            ul: ({ node, ...props }) => (
              <ul className="list-disc ml-6 mb-3" {...props} />
            ),
            ol: ({ node, ...props }) => (
              <ol className="list-decimal ml-6 mb-3" {...props} />
            ),
            code: ({ node, inline, ...props }) =>
              inline ? (
                <code
                  className="bg-gray-200 px-1 py-0.5 rounded text-sm"
                  {...props}
                />
              ) : (
                <pre className="bg-gray-900 text-gray-100 p-4 rounded overflow-x-auto mb-4">
                  <code {...props} />
                </pre>
              ),
          }}
        >
          {content}
        </ReactMarkdown>
      </div>
    </div>
  );
}