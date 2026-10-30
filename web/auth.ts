import NextAuth, { CredentialsSignin } from "next-auth";
import Credentials from "next-auth/providers/credentials";
import Google from "next-auth/providers/google";

import { loginUser, oauthUser } from "@/lib/serverApi";

class TooManyAttempts extends CredentialsSignin {
  code = "too_many_attempts";
}

const googleEnabled = Boolean(process.env.AUTH_GOOGLE_ID && process.env.AUTH_GOOGLE_SECRET);
export const googleSignInEnabled = googleEnabled;

export const { handlers, auth, signIn, signOut } = NextAuth({
  session: { strategy: "jwt", maxAge: 60 * 60 * 24 * 7 },
  pages: { signIn: "/login", error: "/login" },
  trustHost: true,
  providers: [
    Credentials({
      credentials: { email: {}, password: {} },
      async authorize(raw) {
        const email = typeof raw?.email === "string" ? raw.email : "";
        const password = typeof raw?.password === "string" ? raw.password : "";
        if (!email || !password) return null;
        const result = await loginUser(email, password);
        if (result.status === 429) throw new TooManyAttempts();
        return result.user ? { id: result.user.id, email: result.user.email, name: result.user.name } : null;
      },
    }),
    ...(googleEnabled ? [Google] : []),
  ],
  callbacks: {
    async signIn({ user, account, profile }) {
      if (account?.provider !== "google") return true;
      const result = await oauthUser(
        "google",
        account.providerAccountId,
        profile?.email ?? "",
        profile?.email_verified === true,
        profile?.name ?? "",
      );
      if (!result.user) return `/login?error=${result.code === "email_in_use" ? "email_in_use" : "google_failed"}`;
      user.id = result.user.id; // our own user id, not Google's
      return true;
    },
    async jwt({ token, user }) {
      if (user?.id) token.userId = user.id;
      return token;
    },
    async session({ session, token }) {
      if (typeof token.userId === "string") session.user.id = token.userId;
      return session;
    },
  },
});
