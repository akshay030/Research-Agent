import { useState } from "react";

export default function Tabs({ tabs }) {
  const [active, setActive] = useState(Object.keys(tabs)[0]);

  return (
    <div className="flex-1 p-6">
      <div className="flex space-x-4 border-b mb-4">
        {Object.keys(tabs).map((key) => (
          <button
            key={key}
            onClick={() => setActive(key)}
            className={`pb-2 ${
              active === key
                ? "border-b-2 border-blue-600 font-semibold"
                : "text-gray-500"
            }`}
          >
            {key}
          </button>
        ))}
      </div>

      <div>{tabs[active]}</div>
    </div>
  );
}