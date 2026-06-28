import { useEffect, useRef } from 'react';
import { useAgent } from '@/context/AgentContext';
import styles from '@/styles/app.module.css';

export default function ConsolePage() {
  const { logs, goalResult, isNavigating, stopMission } = useAgent();
  const terminalEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (terminalEndRef.current) terminalEndRef.current.scrollIntoView({ behavior: 'smooth' });
  }, [logs]);

  return (
    <section className={styles.pagePanel}>
      <header className={styles.panelHeader}>
        <div className={styles.panelHeaderTitle}>
          <h3>💻 REAL‑TIME CONSOLE LOGS</h3>
        </div>
        {isNavigating && <button className={styles.abortBtn} onClick={stopMission}>Abort</button>}
      </header>
      <div className={styles.terminal}>
        {logs.map((log, i) => {
          let colorClass = styles.logInfo;
          if (log.level === 'WARNING') colorClass = styles.logWarn;
          if (log.level === 'ERROR') colorClass = styles.logError;
          if (log.level === 'SUCCESS') colorClass = styles.logSuccess;
          return (
            <div key={i} className={`${styles.logRow} ${colorClass}`}>
              <span className={styles.logTime}>{new Date(log.timestamp).toLocaleTimeString()}</span>
              <span className={styles.logLevel}>[{log.level}]</span>
              <span className={styles.logMsg}>{log.message}</span>
            </div>
          );
        })}
        <div ref={terminalEndRef} />
      </div>
      {goalResult && (
        <div className={styles.resultPanel}>
          <h4 className={styles.resultTitle}>extracted_data.json</h4>
          <pre>{goalResult}</pre>
        </div>
      )}
    </section>
  );
}
