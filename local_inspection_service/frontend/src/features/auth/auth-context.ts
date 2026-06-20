import { createContext, useContext } from "react";
import type { AuthUser } from "../../api/types";

export interface AuthContextValue {
  user: AuthUser;
  features: Record<string, string>;
  defaultUserPermissions: string[];
  legacyOwnerId: string;
  dataUserId: string;
  setDataUserId: (userId: string) => void;
  logout: () => Promise<void>;
}

export const AuthContext = createContext<AuthContextValue | null>(null);

export function useAuth() {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used inside AuthContext");
  return value;
}
