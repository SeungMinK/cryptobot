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
  const verifyAttempts = useRef(0);

  const verifyToken = useCallback(async () => {
    const savedToken = localStorage.getItem("token");
    if (!savedToken) {
      setUser(null);
      setIsLoading(false);
      return;
    }

    try {
      const me = await getMe();
      if (isMounted.current) {
        setUser(me);
        verifyAttempts.current = 0;
      }
    } catch (err: unknown) {
      if (!isMounted.current) return;

      const status = (err as { response?: { status?: number } })?.response?.status;

      if (status === 401) {
        // 진짜 인증 실패 — 토큰 만료 또는 무효
        localStorage.removeItem("token");
        setToken(null);
        setUser(null);
      }
      // 500, 네트워크 오류 등은 토큰 유지. 서버 일시 오류일 수 있음.
      // user가 아직 null이면 이전 로그인 상태를 유지하기 위해 재시도하지 않음
    } finally {
      if (isMounted.current) {
        setIsLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    isMounted.current = true;
    if (token) {
      verifyToken();
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

  // token이 있으면 인증된 것으로 간주 (user는 서버 일시 오류로 null일 수 있음)
  const isAuthenticated = !!token;

  return (
    <AuthContext.Provider value={{ user, token, isAuthenticated, login, logout, isLoading }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
