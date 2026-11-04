import Link from "next/link";
import { redirect } from "next/navigation";
import type { ReactNode } from "react";

import { signOutAction } from "@/app/login/actions";
import { auth } from "@/auth";
import { Chat } from "@/components/Chat";
import { ScopeProvider } from "@/components/Scope";

export default async function AppLayout({ children }: { children: ReactNode }) {
  const session = await auth();
  if (!session?.user?.id) redirect("/login");
  return (
    <ScopeProvider>
      <header className="topbar">
        <Link href="/" className="brand">Docs Assistant</Link>
        <div className="who">
          <span className="muted">{session.user.name ?? session.user.email}</span>
          <form action={signOutAction}><button className="btn small" type="submit">Sign out</button></form>
        </div>
      </header>
      <div className="shell">
        <main className="main">{children}</main>
        <Chat />
      </div>
    </ScopeProvider>
  );
}
