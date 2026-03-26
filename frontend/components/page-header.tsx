import Link from "next/link";
import { ReactNode } from "react";

type Props = {
  title: string;
  subtitle?: string;
  actions?: ReactNode;
  backHref?: string;
};

export function PageHeader({ title, subtitle, actions, backHref }: Props) {
  return (
    <div className="spaced">
      <div>
        {backHref ? (
          <Link href={backHref} className="muted">
            뒤로
          </Link>
        ) : null}
        <h1 className="page-title">{title}</h1>
        {subtitle ? <p className="page-subtitle">{subtitle}</p> : null}
      </div>
      {actions ? <div className="row">{actions}</div> : null}
    </div>
  );
}
