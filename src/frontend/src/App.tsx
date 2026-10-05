export default function App() {
  return (
    <div className="flex h-screen">
      <aside className="w-[280px] bg-gray-50 border-r border-gray-200 p-4">
        <h1 className="text-sm font-semibold text-gray-900">common_agent</h1>
      </aside>
      <main className="flex-1 flex items-center justify-center">
        <p className="text-gray-500 text-[13px]">Send a message to start</p>
      </main>
    </div>
  );
}
