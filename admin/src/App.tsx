import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { AuthProvider } from "./context/AuthContext";
import ProtectedRoute from "./components/ProtectedRoute";
import Layout from "./components/Layout";
import LoginPage from "./pages/LoginPage";
import DashboardPage from "./pages/DashboardPage";
import TradesPage from "./pages/TradesPage";
import StrategiesPage from "./pages/StrategiesPage";
import ProfitAnalysisPage from "./pages/ProfitAnalysisPage";
import ConfigPage from "./pages/ConfigPage";
import SignalsPage from "./pages/SignalsPage";
import NewsPage from "./pages/NewsPage";

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route
            element={
              <ProtectedRoute>
                <Layout />
              </ProtectedRoute>
            }
          >
            <Route path="/" element={<DashboardPage />} />
            <Route path="/trades" element={<TradesPage />} />
            <Route path="/strategies" element={<StrategiesPage />} />
            <Route path="/profit" element={<ProfitAnalysisPage />} />
            <Route path="/signals" element={<SignalsPage />} />
            <Route path="/news" element={<NewsPage />} />
            <Route path="/config" element={<ConfigPage />} />
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  );
}
