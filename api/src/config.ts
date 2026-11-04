import path from "node:path";

export interface Config {
  port: number;
  databaseUrl: string;
  /** Signs and checks the short-lived tokens the website sends with each request. */
  apiJwtSecret: string;
  /** Proves a request to /internal/* comes from the website's server (sign-up, login). */
  internalSecret: string;
  ragServiceUrl: string;
  /** Proves to the Python service that the request comes from this API. */
  ragServiceSecret: string;
  uploadDir: string;
  maxUploadBytes: number;
  maxFilesPerUser: number;
}

const MIN_SECRET_LENGTH = 32;

function secret(env: Record<string, string | undefined>, name: string): string {
  const value = env[name] ?? "";
  if (value.length < MIN_SECRET_LENGTH || value.startsWith("change-me") || value === "your-key-here") {
    throw new Error(
      `${name} must be a random string of at least ${MIN_SECRET_LENGTH} characters in the .env file. ` +
        `Make one with:  node -e "console.log(require('crypto').randomBytes(32).toString('hex'))"`,
    );
  }
  return value;
}

export function loadConfig(env: Record<string, string | undefined> = process.env): Config {
  const apiJwtSecret = secret(env, "API_JWT_SECRET");
  const internalSecret = secret(env, "INTERNAL_SECRET");
  const ragServiceSecret = secret(env, "RAG_SERVICE_SECRET");
  if (new Set([apiJwtSecret, internalSecret, ragServiceSecret]).size !== 3) {
    throw new Error("API_JWT_SECRET, INTERNAL_SECRET and RAG_SERVICE_SECRET must all be different.");
  }
  return {
    port: Number(env.API_PORT ?? 4000),
    databaseUrl: env.DATABASE_URL ?? "postgresql://postgres:postgres@localhost:5432/docs_assistant",
    apiJwtSecret,
    internalSecret,
    ragServiceUrl: (env.RAG_SERVICE_URL ?? "http://127.0.0.1:8000").replace(/\/$/, ""),
    ragServiceSecret,
    uploadDir: path.resolve(env.UPLOAD_DIR ?? "../storage/uploads"),
    maxUploadBytes: Number(env.MAX_UPLOAD_BYTES ?? 10 * 1024 * 1024),
    maxFilesPerUser: Number(env.MAX_FILES_PER_USER ?? 1000),
  };
}
