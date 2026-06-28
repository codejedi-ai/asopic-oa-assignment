import { useEffect } from 'react';
import ChatPanel from '@/components/ChatPanel';
import { useAgent } from '@/context/AgentContext';

// /mission — the fresh "new mission" draft conversation.
export default function MissionIndexPage() {
  const { startNewMission } = useAgent();
  useEffect(() => { startNewMission(); }, []);
  return <ChatPanel />;
}
