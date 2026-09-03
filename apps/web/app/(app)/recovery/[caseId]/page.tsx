import type { Metadata } from "next";

import { CaseDetailClient } from "@/app/(app)/recovery/[caseId]/case-detail-client";

export const metadata: Metadata = {
  title: "Recovery Case | RevLoop",
  description:
    "Recovery case detail: failure evidence, recommendation, candidate actions and outcome.",
};

interface RecoveryCaseDetailPageProps {
  params: Promise<{ caseId: string }>;
}

export default async function RecoveryCaseDetailPage({
  params,
}: RecoveryCaseDetailPageProps) {
  const { caseId } = await params;

  return <CaseDetailClient caseId={caseId} />;
}
