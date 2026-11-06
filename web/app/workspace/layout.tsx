import { WorkspaceBar } from "@/components/shell";

export default function WorkspaceLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="page-glow min-h-screen">
      <WorkspaceBar />
      <main className="mx-auto max-w-[1200px] px-5 py-8">{children}</main>
    </div>
  );
}
