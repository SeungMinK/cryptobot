import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

export default function Layout() {
  const { user, isAuthenticated, logout } = useAuth();
  const navigate = useNavigate();

  return (
    <div className="app-layout">
      <aside className="sidebar">
        <div className="sidebar-logo">CryptoBot</div>
        <nav className="sidebar-nav">
          <NavLink to="/" end className={({ isActive }) => `sidebar-link${isActive ? " active" : ""}`}>
            대시보드
          </NavLink>
          {isAuthenticated && (
            <>
              <NavLink to="/trades" className={({ isActive }) => `sidebar-link${isActive ? " active" : ""}`}>
                매매 내역
              </NavLink>
              <NavLink to="/strategies" className={({ isActive }) => `sidebar-link${isActive ? " active" : ""}`}>
                전략 관리
              </NavLink>
              <NavLink to="/signals" className={({ isActive }) => `sidebar-link${isActive ? " active" : ""}`}>
                매매 신호
              </NavLink>
              <NavLink to="/news" className={({ isActive }) => `sidebar-link${isActive ? " active" : ""}`}>
                뉴스
              </NavLink>
              <NavLink to="/profit" className={({ isActive }) => `sidebar-link${isActive ? " active" : ""}`}>
                수익률 분석
              </NavLink>
              <NavLink to="/llm" className={({ isActive }) => `sidebar-link${isActive ? " active" : ""}`}>
                LLM 관리
              </NavLink>
              <NavLink to="/config" className={({ isActive }) => `sidebar-link${isActive ? " active" : ""}`}>
                설정
              </NavLink>
            </>
          )}
        </nav>
        <div className="sidebar-footer">
          {isAuthenticated ? (
            <>
              <div style={{ fontSize: 13, color: "var(--text-secondary)", marginBottom: 8 }}>
                {user?.display_name || user?.username}
              </div>
              <button onClick={logout}>로그아웃</button>
            </>
          ) : (
            <button onClick={() => navigate("/login")}>관리자 로그인</button>
          )}
        </div>
      </aside>
      <main className="main-content">
        <Outlet />
      </main>
    </div>
  );
}
