import { createContext, useContext, useMemo, useState } from "react";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [token, setTokenState] = useState(() => localStorage.getItem("fedrepro_token"));
  const setToken = (value) => {
    if (value) localStorage.setItem("fedrepro_token", value);
    else localStorage.removeItem("fedrepro_token");
    setTokenState(value || null);
  };
  const value = useMemo(() => ({ token, authenticated: Boolean(token), setToken, logout: () => setToken(null) }), [token]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export const useAuth = () => useContext(AuthContext);

