import { useEffect } from 'react';
import { useParams } from 'ice';
import ChatPanel from '@/components/ChatPanel';
import { useAgent } from '@/context/AgentContext';

// /mission/:id — a specific mission's own chat thread.
export default function MissionDetailPage() {
  const { id } = useParams();
  const { openMissionById } = useAgent();

  useEffect(() => {
    if (id) openMissionById(id);
  }, [id]);

  return <ChatPanel />;
}
