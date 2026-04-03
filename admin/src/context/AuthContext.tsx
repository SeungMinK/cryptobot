import { createContext, useContext, useState, useEffect, useRef, type ReactNode } from "react";
import { login as apiLogin, getMe } from "../api/auth";
import type { UserResponse } from "../types/auth";

interface AuthContextType {
  user: UserResponse | null;
  token: string | null;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
  isLoading: boolean;
}

const AuthContext = createContext<AuthContextType | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<UserResponse | null>(null);
  const [token, setToken] = useState<string | null>(localStorage.getItem("token"));
  const [isLoading, setIsLoading] = useState(true);
  const skipEffect = useRef(false);

  useEffect(() => {
    // login() 함수에서 이미 user를 세팅한 경우 중복 호출 방지
    if (skipEffect.current) {
      skipEffect.current = false;
      setIsLoading(false);
      return;
    }

    if (token) {
      getMe()
        .then(setUser)
        .catch(() => {
          localStorage.removeItem("token");
          setToken(null);
          setUser(null);
        })
        .finally(() => setIsLoading(false));
    } else {
      setUser(null);
      setIsLoading(false);
    }
  }, [token]);

  const login = async (username: string, password: string) => {
    const res = await apiLogin(username, password);
    localStorage.setItem("token", res.access_token);
    const me = await getMe();
    setUser(me);
    skipEffect.current = true;
    setToken(res.access_token);
  };

  const logout = () => {
    localStorage.removeItem("token");
    setToken(null);
    setUser(null);
  };

  return (
    <AuthContext.Provider value={{ user, token, login, logout, isLoading }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
