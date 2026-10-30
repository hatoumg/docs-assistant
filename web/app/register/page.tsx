import { redirect } from "next/navigation";

import { auth, googleSignInEnabled } from "@/auth";
import { AuthForm } from "@/components/AuthForm";

export default async function RegisterPage() {
  if ((await auth())?.user) redirect("/");
  return <AuthForm mode="register" googleEnabled={googleSignInEnabled} />;
}
