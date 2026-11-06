import { DeskBar } from "@/components/shell";

export default function DeskLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="page-glow min-h-screen">
      <DeskBar />
      <main className="mx-auto max-w-[1400px] px-5 py-7">{children}</main>
    </div>
  );
}
