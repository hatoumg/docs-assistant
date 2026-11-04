import { redirect } from "next/navigation";

import { auth, googleSignInEnabled } from "@/auth";
import { AuthForm } from "@/components/AuthForm";

export default async function LoginPage({ searchParams }: { searchParams: Promise<{ error?: string }> }) {
  if ((await auth())?.user) redirect("/");
  const { error } = await searchParams;
  return <AuthForm mode="login" googleEnabled={googleSignInEnabled} notice={error} />;
}
