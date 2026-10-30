import "server-only";

/** Calls from the website's server to the API's sign-up and login routes (the INTERNAL_SECRET proves who is calling). */

export interface AccountUser {
  id: string;
  email: string;
  name: string;
}

export const apiUrl = () => (process.env.API_URL ?? "http://127.0.0.1:4000").replace(/\/$/, "");

function internalSecret(): string {
  const secret = process.env.INTERNAL_SECRET;
  if (!secret) throw new Error("INTERNAL_SECRET is not set in the .env file.");
  return secret;
}

async function post(path: string, body: unknown): Promise<{ status: number; data: any }> {
  const response = await fetch(`${apiUrl()}${path}`, {
    method: "POST",
    headers: { "content-type": "application/json", "x-internal-secret": internalSecret() },
    body: JSON.stringify(body),
    cache: "no-store",
  });
  return { status: response.status, data: await response.json().catch(() => null) };
}

export async function loginUser(email: string, password: string) {
  const { status, data } = await post("/internal/login", { email, password });
  return { status, user: status === 200 ? (data as AccountUser) : null, message: data?.message as string | undefined };
}

export async function registerUser(email: string, password: string, name: string) {
  const { status, data } = await post("/internal/register", { email, password, name });
  return { status, message: (data?.message as string | undefined) ?? "Could not create the account." };
}

export async function oauthUser(provider: string, providerAccountId: string, email: string, emailVerified: boolean, name: string) {
  const { status, data } = await post("/internal/oauth", { provider, providerAccountId, email, emailVerified, name });
  return { status, user: status === 200 ? (data as AccountUser) : null, code: data?.error as string | undefined };
}
