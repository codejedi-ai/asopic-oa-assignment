import { useAgent } from '@/context/AgentContext';
import styles from '@/styles/app.module.css';

export default function LiveVisionPage() {
  const { screenshot, currentUrl, currentStep, isNavigating } = useAgent();

  return (
    <section className={styles.pagePanel}>
      <header className={styles.panelHeader}>
        <div className={styles.panelHeaderTitle}>
          <h3>🖥️ AGENT BROWSER LIVE VISION</h3>
        </div>
        {isNavigating && <span className={styles.stepBadge}>Step {currentStep ?? '1'}</span>}
      </header>
      <div className={styles.viewportContainer}>
        {screenshot ? (
          <img src={`data:image/png;base64,${screenshot}`} alt="Viewport" className={styles.viewport} />
        ) : (
          <div className={styles.viewportPlaceholder}>No image yet — waiting for the agent's first screenshot.</div>
        )}
      </div>
      {currentUrl && (
        <div className={styles.addressBar}><strong>Location:</strong> <span>{currentUrl}</span></div>
      )}
    </section>
  );
}
