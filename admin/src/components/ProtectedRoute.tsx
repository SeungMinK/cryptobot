import { Navigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

export default function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { token, isLoading } = useAuth();

  if (isLoading) return <div className="loading">로딩 중...</div>;
  if (!token) return <Navigate to="/login" replace />;

  return <>{children}</>;
}
