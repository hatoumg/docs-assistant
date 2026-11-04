import { DUMMY_HASH, hashPassword, verifyPassword } from "../auth/password.js";
import { isUniqueViolation, type Db } from "../db.js";
import { HttpError } from "../errors.js";
import { asObject, json, type RouteSpec } from "../http.js";
import { RateLimiter } from "../limits.js";
import { createOAuthUser, createPasswordUser, findByEmail, findByProvider } from "../store/users.js";
import { cleanEmail, cleanName, cleanPassword } from "../validate.js";

const OAUTH_PROVIDERS = ["google"];

/** Sign-up and login. Only the website's server may call these (the INTERNAL_SECRET check happens in app.ts). */
export function internalRoutes(db: Db, loginLimiter: RateLimiter): RouteSpec[] {
  return [
    {
      method: "POST",
      path: "/internal/register",
      auth: "internal",
      async handle(ctx) {
        const body = asObject(await ctx.readJson());
        const email = cleanEmail(body.email);
        const password = cleanPassword(body.password);
        const name = body.name === undefined || body.name === "" ? email.split("@")[0]! : cleanName(body.name, "Name", 100);
        try {
          return json(201, await createPasswordUser(db, email, name, await hashPassword(password)));
        } catch (error) {
          if (isUniqueViolation(error)) throw new HttpError(409, "email_taken", "An account with this email already exists.");
          throw error;
        }
      },
    },
    {
      method: "POST",
      path: "/internal/login",
      auth: "internal",
      async handle(ctx) {
        const body = asObject(await ctx.readJson());
        const email = cleanEmail(body.email);
        const password = typeof body.password === "string" && body.password.length <= 128 ? body.password : "";
        if (loginLimiter.isBlocked(email)) {
          throw new HttpError(429, "too_many_attempts", "Too many failed attempts. Try again in a few minutes.");
        }
        const found = await findByEmail(db, email);
        const hash = found?.provider === "password" ? found.password_hash : null;
        // Always do one hash check, so an unknown email takes as long as a wrong password.
        const correct = await verifyPassword(password, hash ?? DUMMY_HASH);
        if (!found || !hash || !correct) {
          loginLimiter.record(email);
          throw new HttpError(401, "invalid_credentials", "That email and password do not match.");
        }
        loginLimiter.reset(email);
        return json(200, { id: found.id, email: found.email, name: found.name });
      },
    },
    {
      method: "POST",
      path: "/internal/oauth",
      auth: "internal",
      async handle(ctx) {
        const body = asObject(await ctx.readJson());
        const provider = typeof body.provider === "string" ? body.provider : "";
        if (!OAUTH_PROVIDERS.includes(provider)) throw new HttpError(400, "bad_request", "Unknown sign-in provider.");
        const accountId = typeof body.providerAccountId === "string" ? body.providerAccountId.trim() : "";
        if (!accountId || accountId.length > 200) throw new HttpError(400, "bad_request", "Missing provider account id.");
        if (body.emailVerified !== true) {
          throw new HttpError(403, "email_not_verified", "The provider has not verified this email address.");
        }
        const email = cleanEmail(body.email);

        const existing = await findByProvider(db, provider, accountId);
        if (existing) return json(200, existing);

        // Never attach a Google sign-in to an account that already exists for this email: someone could have
        // registered that email with a password they chose before the real owner ever signed in.
        if (await findByEmail(db, email)) {
          throw new HttpError(409, "email_in_use", "An account with this email already exists. Sign in with your password.");
        }
        const name = typeof body.name === "string" && body.name.trim() ? cleanName(body.name.slice(0, 100), "Name", 100) : email.split("@")[0]!;
        try {
          return json(200, await createOAuthUser(db, provider, accountId, email, name));
        } catch (error) {
          if (isUniqueViolation(error)) throw new HttpError(409, "email_in_use", "An account with this email already exists.");
          throw error;
        }
      },
    },
  ];
}
