import { useAgent } from '@/context/AgentContext';
import styles from '@/styles/app.module.css';

export default function SettingsPage() {
  const { agentUrl, setAgentUrl, wsStatus, connectToAgent, disconnectFromAgent, isNavigating } = useAgent();

  return (
    <section className={styles.pagePanel}>
      <header className={styles.panelHeader}>
        <div className={styles.panelHeaderTitle}>
          <h3>⚙️ SETTINGS</h3>
        </div>
      </header>

      <div className={styles.settingsBody}>
        <div className={styles.settingsCard}>
          <h4 className={styles.settingsCardTitle}>Agent Connection</h4>

          <div className={styles.settingsRow}>
            <span className={`${styles.statusDot} ${styles[wsStatus]}`} />
            <span className={styles.connectionLabel}>
              {wsStatus === 'connected' && 'Agent Online'}
              {wsStatus === 'connecting' && 'Connecting...'}
              {wsStatus === 'disconnected' && 'Agent Offline'}
              {wsStatus === 'error' && 'Connection Error'}
            </span>
          </div>

          <div className={styles.settingsField}>
            <label className={styles.settingsLabel}>Agent Server URL</label>
            <input
              className={styles.settingsInput}
              type="text"
              value={agentUrl}
              onChange={e => setAgentUrl(e.target.value)}
              disabled={isNavigating}
              placeholder="ws://localhost:8000/ws"
            />
            {isNavigating && (
              <span className={styles.settingsHint}>Stop the running mission to change the server URL.</span>
            )}
          </div>

          {wsStatus !== 'connected' ? (
            <button className={styles.connectBtn} onClick={connectToAgent}>Connect</button>
          ) : (
            <button className={styles.disconnectBtn} onClick={disconnectFromAgent}>Disconnect</button>
          )}
        </div>
      </div>
    </section>
  );
}
