"use client";

import Link from "next/link";
import { useActionState } from "react";

import { loginAction, registerAction, googleAction, type FormState } from "@/app/login/actions";

const NOTICES: Record<string, string> = {
  email_in_use: "An account with this email already exists. Sign in with your password.",
  google_failed: "Google sign-in did not work. Try again, or use email and password.",
  Configuration: "Sign-in is not set up correctly. Check AUTH_SECRET in the .env file.",
};

export function AuthForm({ mode, googleEnabled, notice }: { mode: "login" | "register"; googleEnabled: boolean; notice?: string }) {
  const [state, action, pending] = useActionState<FormState, FormData>(mode === "login" ? loginAction : registerAction, {});
  const message = state.error ?? (notice ? NOTICES[notice] ?? "Could not sign in." : "");
  return (
    <main className="auth">
      <h1>{mode === "login" ? "Sign in" : "Create your account"}</h1>
      <form action={action} className="stack">
        {mode === "register" && (
          <label>Name<input name="name" autoComplete="name" maxLength={100} /></label>
        )}
        <label>Email<input name="email" type="email" required autoComplete="email" /></label>
        <label>
          Password
          <input name="password" type="password" required minLength={mode === "register" ? 8 : undefined} maxLength={128}
            autoComplete={mode === "login" ? "current-password" : "new-password"} />
        </label>
        {mode === "register" && <p className="muted small">At least 8 characters.</p>}
        {message && <p className="error" role="alert">{message}</p>}
        <button className="btn primary" type="submit" disabled={pending}>
          {pending ? "Please wait…" : mode === "login" ? "Sign in" : "Create account"}
        </button>
      </form>
      {googleEnabled && (
        <form action={googleAction}>
          <div className="divider"><span>or</span></div>
          <button className="btn wide" type="submit">Continue with Google</button>
        </form>
      )}
      <p className="muted small center">
        {mode === "login" ? <>New here? <Link href="/register">Create an account</Link></> : <>Already have an account? <Link href="/login">Sign in</Link></>}
      </p>
    </main>
  );
}
