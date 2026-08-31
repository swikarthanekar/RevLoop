import { APP_NAME } from "@/lib/constants";

export default function Home() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-4 p-8">
      <h1 className="text-3xl font-semibold tracking-tight">{APP_NAME}</h1>
      <p className="max-w-md text-center text-sm text-neutral-600">
        Revenue recovery control plane. Phase 0 repository skeleton — dashboard
        features arrive in later milestones.
      </p>
    </main>
  );
}
