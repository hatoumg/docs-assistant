"use client";

import { createContext, useContext, useMemo, useState, type ReactNode } from "react";

/** Which folder the user is in right now. The page sets it; the chat reads it so it knows where to search. */
export interface Scope {
  folderId: string | null;
  name: string | null;
}
/** A passage the chat wants shown highlighted inside its file. `key` changes on every click, so clicking twice reopens it. */
export interface Highlight {
  fileId: number;
  text: string;
  key: number;
}
const Ctx = createContext<{ scope: Scope; setScope: (scope: Scope) => void; highlight: Highlight | null; setHighlight: (h: Highlight | null) => void }>({
  scope: { folderId: null, name: null },
  setScope: () => {},
  highlight: null,
  setHighlight: () => {},
});

export function ScopeProvider({ children }: { children: ReactNode }) {
  const [scope, setScope] = useState<Scope>({ folderId: null, name: null });
  const [highlight, setHighlight] = useState<Highlight | null>(null);
  const value = useMemo(() => ({ scope, setScope, highlight, setHighlight }), [scope, highlight]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}
export const useScope = () => useContext(Ctx);
