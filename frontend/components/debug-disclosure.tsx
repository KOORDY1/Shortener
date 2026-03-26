"use client";

import { ReactNode } from "react";

type Props = {
  title?: string;
  children: ReactNode;
  defaultOpen?: boolean;
};

export function DebugDisclosure({ title = "디버그 정보 보기", children, defaultOpen = false }: Props) {
  return (
    <details className="panel soft" open={defaultOpen}>
      <summary style={{ cursor: "pointer", fontWeight: 600 }}>{title}</summary>
      <div className="stack" style={{ marginTop: 12 }}>
        {children}
      </div>
    </details>
  );
}
