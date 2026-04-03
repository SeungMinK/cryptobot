import { NavLink, Outlet } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

export default function Layout() {
  const { user, logout } = useAuth();

  return (
    <div className="app-layout">
      <aside className="sidebar">
        <div className="sidebar-logo">CryptoBot</div>
        <nav className="sidebar-nav">
          <NavLink to="/" end className={({ isActive }) => `sidebar-link${isActive ? " active" : ""}`}>
            Dashboard
          </NavLink>
          <NavLink to="/trades" className={({ isActive }) => `sidebar-link${isActive ? " active" : ""}`}>
            Trades
          </NavLink>
          <NavLink to="/strategies" className={({ isActive }) => `sidebar-link${isActive ? " active" : ""}`}>
            Strategies
          </NavLink>
          <NavLink to="/profit" className={({ isActive }) => `sidebar-link${isActive ? " active" : ""}`}>
            Profit Analysis
          </NavLink>
        </nav>
        <div className="sidebar-footer">
          <div style={{ fontSize: 13, color: "var(--text-secondary)", marginBottom: 8 }}>
            {user?.display_name || user?.username}
          </div>
          <button onClick={logout}>Logout</button>
        </div>
      </aside>
      <main className="main-content">
        <Outlet />
      </main>
    </div>
  );
}
