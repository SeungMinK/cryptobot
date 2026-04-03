import { createContext, useContext, useState, useEffect, useRef, useCallback, type ReactNode } from "react";
import { login as apiLogin, getMe } from "../api/auth";
import type { UserResponse } from "../types/auth";

interface AuthContextType {
  user: UserResponse | null;
  token: string | null;
  isAuthenticated: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
  isLoading: boolean;
}

const AuthContext = createContext<AuthContextType | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<UserResponse | null>(null);
  const [token, setToken] = useState<string | null>(localStorage.getItem("token"));
  const [isLoading, setIsLoading] = useState(!!localStorage.getItem("token"));
  const isMounted = useRef(true);

  const verifyToken = useCallback(async (currentToken: string) => {
    try {
      const me = await getMe();
      if (isMounted.current) {
        setUser(me);
      }
    } catch (err: unknown) {
      if (isMounted.current) {
        // 401만 로그아웃 처리, 네트워크 오류 등은 유지
        const status = (err as { response?: { status?: number } })?.response?.status;
        if (status === 401) {
          localStorage.removeItem("token");
          setToken(null);
          setUser(null);
        }
      }
    } finally {
      if (isMounted.current) {
        setIsLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    isMounted.current = true;
    if (token) {
      verifyToken(token);
    } else {
      setUser(null);
      setIsLoading(false);
    }
    return () => {
      isMounted.current = false;
    };
  }, [token, verifyToken]);

  const login = async (username: string, password: string) => {
    const res = await apiLogin(username, password);
    localStorage.setItem("token", res.access_token);
    const me = await getMe();
    setUser(me);
    setToken(res.access_token);
  };

  const logout = () => {
    localStorage.removeItem("token");
    setToken(null);
    setUser(null);
  };

  return (
    <AuthContext.Provider value={{ user, token, isAuthenticated: !!token && !!user, login, logout, isLoading }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
