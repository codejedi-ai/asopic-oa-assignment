import { Link, useLocation, useNavigate } from 'ice';
import logo from '@/assets/logo.png';
import { useAgent } from '@/context/AgentContext';
import styles from '@/styles/app.module.css';

const NAV_ITEMS = [
  { to: '/mission', label: 'Mission control' },
  { to: '/live-vision', label: '🖥️ Live Vision' },
  { to: '/console', label: '💻 Console Logs' },
];

export default function Sidebar() {
  const {
    sidebarOpen, setSidebarOpen,
    wsStatus,
    missions, selectedMissionId,
  } = useAgent();

  const location = useLocation();
  const navigate = useNavigate();

  const handleNewMission = () => navigate('/mission');

  if (!sidebarOpen) {
    return <button className={styles.sidebarTrigger} onClick={() => setSidebarOpen(true)}>▶</button>;
  }

  return (
    <aside className={`${styles.sidebar} ${styles.sidebarOpen}`}>
      <div className={styles.sidebarHeader}>
        <Link to="/mission" className={styles.sidebarBrand}>
          <img src={logo} className={styles.sidebarLogo} alt="Logo" />
          <h2 className={styles.sidebarTitle}>Mission control</h2>
        </Link>
        <button className={styles.toggleBtn} onClick={() => setSidebarOpen(false)}>◀</button>
      </div>

      {/* Page navigation */}
      <nav className={styles.sidebarPages}>
        {NAV_ITEMS.map(item => {
          const active = location.pathname === item.to;
          return (
            <Link
              key={item.to}
              to={item.to}
              className={`${styles.navItem} ${active ? styles.activeNavItem : ''}`}
            >
              {item.label}
            </Link>
          );
        })}
      </nav>

      <button className={styles.newMissionBtn} onClick={handleNewMission}>➕ New Mission</button>

      {/* History — each mission links to its own /mission/<uuid> thread */}
      <div className={styles.historyList}>
        <div className={styles.historySectionTitle}>Mission History</div>
        {missions.map(m => (
          <Link
            key={m.id}
            to={m.url}
            className={`${styles.historyItem} ${selectedMissionId === m.id ? styles.activeHistoryItem : ''}`}
          >
            <span className={styles.historyTitle}>{m.title}</span>
            <span className={`${styles.historyStatus} ${styles[`status_${m.status}`]}`}>
              {m.status === 'running' ? '🔄' : m.status === 'success' ? '✅' : m.status === 'failed' ? '❌' : ''}
            </span>
          </Link>
        ))}
      </div>

      {/* Settings — pinned to the bottom, opens the /settings page */}
      <Link
        to="/settings"
        className={`${styles.settingsBtn} ${location.pathname === '/settings' ? styles.activeNavItem : ''}`}
      >
        <span className={`${styles.statusDot} ${styles[wsStatus]}`} />
        <span className={styles.settingsBtnLabel}>⚙️ Settings</span>
      </Link>
    </aside>
  );
}
