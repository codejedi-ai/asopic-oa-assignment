import { Outlet } from 'ice';
import VantaBackground from '@/components/VantaBackground';
import Sidebar from '@/components/Sidebar';
import { AgentProvider } from '@/context/AgentContext';
import styles from '@/styles/app.module.css';

export default function Layout() {
  return (
    <AgentProvider>
      <VantaBackground />
      <div className={styles.appContainer}>
        <Sidebar />
        <main className={styles.pageMain}>
          <Outlet />
        </main>
      </div>
    </AgentProvider>
  );
}
