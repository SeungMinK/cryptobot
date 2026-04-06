import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { AuthProvider, useAuth } from "./context/AuthContext";
import Layout from "./components/Layout";
import LoginPage from "./pages/LoginPage";
import PublicDashboardPage from "./pages/PublicDashboardPage";
import DashboardPage from "./pages/DashboardPage";
import TradesPage from "./pages/TradesPage";
import StrategiesPage from "./pages/StrategiesPage";
import ProfitAnalysisPage from "./pages/ProfitAnalysisPage";
import ConfigPage from "./pages/ConfigPage";
import SignalsPage from "./pages/SignalsPage";
import LLMPage from "./pages/LLMPage";
import NewsPage from "./pages/NewsPage";

function AppRoutes() {
  const { isAuthenticated, isLoading } = useAuth();

  if (isLoading) return <div className="loading">로딩 중...</div>;

  // 비로그인: 공개 대시보드 (Layout 포함)
  if (!isAuthenticated) {
    return (
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route element={<Layout />}>
          <Route path="/" element={<PublicDashboardPage />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    );
  }

  // 로그인: 관리자 전체 기능
  return (
    <Routes>
      <Route path="/login" element={<Navigate to="/" replace />} />
      <Route element={<Layout />}>
        <Route path="/" element={<DashboardPage />} />
        <Route path="/trades" element={<TradesPage />} />
        <Route path="/strategies" element={<StrategiesPage />} />
        <Route path="/profit" element={<ProfitAnalysisPage />} />
        <Route path="/signals" element={<SignalsPage />} />
        <Route path="/news" element={<NewsPage />} />
        <Route path="/llm" element={<LLMPage />} />
        <Route path="/config" element={<ConfigPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <AppRoutes />
      </AuthProvider>
    </BrowserRouter>
  );
}
