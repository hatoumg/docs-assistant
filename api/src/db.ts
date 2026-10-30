export interface QueryResult<T> {
  rows: T[];
  rowCount: number;
}

/** The only thing the rest of the API knows about the database. Tests can swap it. */
export interface Db {
  query<T = Record<string, unknown>>(text: string, params?: unknown[]): Promise<QueryResult<T>>;
  end(): Promise<void>;
}

export function createDb(connectionString: string): Db {
  // The pg package is loaded the first time a query runs, so code that only needs the types does not load it.
  let pool: import("pg").Pool | undefined;
  const getPool = async () => {
    if (!pool) {
      const { default: pg } = await import("pg");
      pool = new pg.Pool({ connectionString, max: 10 });
    }
    return pool;
  };
  return {
    async query<T>(text: string, params: unknown[] = []) {
      const result = await (await getPool()).query(text, params as unknown[]);
      return { rows: result.rows as T[], rowCount: result.rowCount ?? 0 };
    },
    async end() {
      if (pool) await pool.end();
    },
  };
}

export function isUniqueViolation(error: unknown): boolean {
  return (error as { code?: string } | null)?.code === "23505";
}
