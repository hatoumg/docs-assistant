"use server";

import { AuthError } from "next-auth";

import { signIn, signOut } from "@/auth";
import { registerUser } from "@/lib/serverApi";

export interface FormState {
  error?: string;
}

async function startSession(email: string, password: string): Promise<FormState> {
  try {
    await signIn("credentials", { email, password, redirectTo: "/" });
    return {};
  } catch (error) {
    if (error instanceof AuthError) {
      const code = (error as { code?: string }).code;
      if (code === "too_many_attempts") return { error: "Too many failed attempts. Try again in a few minutes." };
      return { error: "That email and password do not match." };
    }
    throw error; // the redirect after a successful sign-in is thrown on purpose; let it through
  }
}

export async function loginAction(_: FormState, form: FormData): Promise<FormState> {
  return startSession(String(form.get("email") ?? ""), String(form.get("password") ?? ""));
}

export async function registerAction(_: FormState, form: FormData): Promise<FormState> {
  const email = String(form.get("email") ?? "");
  const password = String(form.get("password") ?? "");
  const created = await registerUser(email, password, String(form.get("name") ?? ""));
  if (created.status !== 201) return { error: created.message };
  return startSession(email, password);
}

export async function googleAction() {
  await signIn("google", { redirectTo: "/" });
}

export async function signOutAction() {
  await signOut({ redirectTo: "/login" });
}
