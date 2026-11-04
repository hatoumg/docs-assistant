/** An error the API wants to show the caller. Anything else becomes a plain 500 with no details. */
export class HttpError extends Error {
  readonly status: number;
  readonly code: string;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

export const notFound = (what: string) => new HttpError(404, "not_found", `${what} not found.`);
export const badRequest = (message: string) => new HttpError(400, "bad_request", message);
