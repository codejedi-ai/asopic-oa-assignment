import { Link, useLocation } from 'ice';
import logo from '@/assets/logo.png';
import { useAgent } from '@/context/AgentContext';
import styles from '@/styles/app.module.css';

const NAV_ITEMS = [
  { to: '/mission', label: '💬 Chat Assistant' },
  { to: '/live-vision', label: '🖥️ Live Vision' },
  { to: '/console', label: '💻 Console Logs' },
];

export default function Sidebar() {
  const {
    sidebarOpen, setSidebarOpen,
    agentUrl, setAgentUrl,
    wsStatus,
    connectToAgent, disconnectFromAgent,
    missions, selectedMissionId, loadHistoricalMission, startNewMission,
    isNavigating,
  } = useAgent();

  const location = useLocation();

  if (!sidebarOpen) {
    return <button className={styles.sidebarTrigger} onClick={() => setSidebarOpen(true)}>▶</button>;
  }

  return (
    <aside className={`${styles.sidebar} ${styles.sidebarOpen}`}>
      <div className={styles.sidebarHeader}>
        <img src={logo} className={styles.sidebarLogo} alt="Logo" />
        <h2 className={styles.sidebarTitle}>Gemini Control</h2>
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

      <button className={styles.newMissionBtn} onClick={startNewMission}>➕ New Mission</button>

      {/* Connection */}
      <div className={styles.sidebarConnection}>
        <div className={styles.connectionDetails}>
          <span className={`${styles.statusDot} ${styles[wsStatus]}`} />
          <span className={styles.connectionLabel}>
            {wsStatus === 'connected' && 'Agent Online'}
            {wsStatus === 'connecting' && 'Connecting...'}
            {wsStatus === 'disconnected' && 'Agent Offline'}
            {wsStatus === 'error' && 'Error'}
          </span>
        </div>
        {wsStatus !== 'connected' ? (
          <button className={styles.connectBtn} onClick={connectToAgent}>Connect</button>
        ) : (
          <button className={styles.disconnectBtn} onClick={disconnectFromAgent}>Disconnect</button>
        )}
      </div>

      {/* History */}
      <div className={styles.historyList}>
        <div className={styles.historySectionTitle}>Mission History</div>
        {missions.map(m => (
          <div
            key={m.id}
            className={`${styles.historyItem} ${selectedMissionId === m.id ? styles.activeHistoryItem : ''}`}
            onClick={() => loadHistoricalMission(m)}
          >
            <span className={styles.historyTitle}>{m.title}</span>
            <span className={`${styles.historyStatus} ${styles[`status_${m.status}`]}`}>
              {m.status === 'running' ? '🔄' : m.status === 'success' ? '✅' : m.status === 'failed' ? '❌' : ''}
            </span>
          </div>
        ))}
      </div>

      {/* Server config */}
      <div className={styles.sidebarConfig}>
        <label>Agent Server URL</label>
        <input type="text" value={agentUrl} onChange={e => setAgentUrl(e.target.value)} disabled={isNavigating} />
      </div>
    </aside>
  );
}
