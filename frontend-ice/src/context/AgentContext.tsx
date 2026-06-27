import { createContext, useContext, useState, useRef, useEffect } from 'react';
import type { ReactNode } from 'react';

export interface LogMessage {
  timestamp: string;
  level: string;
  message: string;
}

export interface ChatMessage {
  id: string;
  sender: 'user' | 'agent' | 'system';
  text: string;
  timestamp: string;
}

export interface MissionHistory {
  id: string;
  title: string;
  repo: string;
  goal: string;
  url: string;
  timestamp: string;
  status: 'idle' | 'running' | 'success' | 'failed';
}

type WsStatus = 'disconnected' | 'connecting' | 'connected' | 'error';
type GoalStatus = 'idle' | 'checking' | 'reached' | 'failed';

interface AgentContextValue {
  agentUrl: string;
  setAgentUrl: (v: string) => void;
  wsStatus: WsStatus;
  sidebarOpen: boolean;
  setSidebarOpen: (v: boolean) => void;
  chatInput: string;
  setChatInput: (v: string) => void;
  chatMessages: ChatMessage[];
  missions: MissionHistory[];
  selectedMissionId: string | null;
  isNavigating: boolean;
  currentStep: number | null;
  currentUrl: string;
  screenshot: string | null;
  domPreview: string;
  logs: LogMessage[];
  goalStatus: GoalStatus;
  goalResult: string | null;
  connectToAgent: () => void;
  disconnectFromAgent: () => void;
  stopMission: () => void;
  handleChatSubmit: (e: React.FormEvent) => void;
  loadHistoricalMission: (m: MissionHistory) => void;
  startNewMission: () => void;
}

const AgentContext = createContext<AgentContextValue | null>(null);

export function useAgent() {
  const ctx = useContext(AgentContext);
  if (!ctx) throw new Error('useAgent must be used within <AgentProvider>');
  return ctx;
}

export function AgentProvider({ children }: { children: ReactNode }) {
  const [agentUrl, setAgentUrl] = useState('ws://localhost:8000/ws');
  const [wsStatus, setWsStatus] = useState<WsStatus>('disconnected');

  const [sidebarOpen, setSidebarOpen] = useState(true);

  const [chatInput, setChatInput] = useState('');
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([
    {
      id: 'welcome',
      sender: 'agent',
      text: 'Hello! I am Gemini, your vision‑based GitHub Release Navigator. Issue a command in the input below to start a mission, e.g., "Find the latest release for openclaw/openclaw"',
      timestamp: new Date().toISOString(),
    },
  ]);

  const [missions, setMissions] = useState<MissionHistory[]>([
    {
      id: 'default-1',
      title: 'Release info for openclaw/openclaw',
      repo: 'openclaw/openclaw',
      goal: 'Find the latest release version, date, and author',
      url: '/mission/default-1',
      timestamp: new Date(Date.now() - 3600000).toISOString(),
      status: 'success',
    },
  ]);
  const [selectedMissionId, setSelectedMissionId] = useState<string | null>(null);

  const [, setStartUrl] = useState('https://github.com/explore');
  const [, setRepoName] = useState('openclaw/openclaw');
  const [, setGoal] = useState('Find the latest release version, date, and author');

  const [isNavigating, setIsNavigating] = useState(false);
  const [currentStep, setCurrentStep] = useState<number | null>(null);
  const [currentUrl, setCurrentUrl] = useState<string>('');
  const [screenshot, setScreenshot] = useState<string | null>(null);
  const [domPreview, setDomPreview] = useState<string>('');

  const [logs, setLogs] = useState<LogMessage[]>([]);

  const [goalStatus, setGoalStatus] = useState<GoalStatus>('idle');
  const [goalResult, setGoalResult] = useState<string | null>(null);

  const socketRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<any>(null);
  const manualDisconnectRef = useRef<boolean>(false);

  const addSystemLog = (message: string, level: string = 'INFO') => {
    setLogs(prev => [...prev, { timestamp: new Date().toISOString(), level, message }]);
  };

  const addChatMessage = (text: string, sender: 'user' | 'agent' | 'system') => {
    setChatMessages(prev => [...prev, { id: Math.random().toString(36).substr(2, 9), sender, text, timestamp: new Date().toISOString() }]);
  };

  const handleAgentEvent = (event: any) => {
    const { type, data, timestamp } = event;
    const time = timestamp ? new Date(timestamp).toLocaleTimeString() : new Date().toLocaleTimeString();
    switch (type) {
      case 'connected':
        addSystemLog(`[${time}] Agent: ${data.message || 'Ready'}`, 'INFO');
        break;
      case 'log':
        setLogs(prev => [...prev, { timestamp: timestamp || new Date().toISOString(), level: data.level || 'INFO', message: data.message }]);
        break;
      case 'navigation_start':
        setIsNavigating(true);
        setCurrentStep(1);
        setCurrentUrl(data.start_url);
        setScreenshot(null);
        setDomPreview('');
        setGoalStatus('idle');
        setGoalResult(null);
        addSystemLog(`[${time}] Navigation task started for goal: "${data.goal}"`, 'INFO');
        addChatMessage(`🤖 Mission Started!\nTarget Repo: ${data.repo_name || 'unknown'}\nStart URL: ${data.start_url}\nGoal: "${data.goal}"`, 'agent');
        setMissions(prev => prev.map(m => (m.status === 'running' ? { ...m, url: data.start_url } : m)));
        break;
      case 'navigation_step':
        setCurrentStep(data.step);
        setCurrentUrl(data.current_url);
        addSystemLog(`[${time}] Step ${data.step}: Navigating to ${data.current_url}`, 'INFO');
        addChatMessage(`🤖 [Step ${data.step}] Inspecting ${data.current_url}...`, 'agent');
        break;
      case 'screenshot':
        setScreenshot(data.screenshot_base64);
        addSystemLog(`[${time}] Received page screenshot for step ${data.step}`, 'SUCCESS');
        break;
      case 'dom_update':
        setDomPreview(data.dom_preview || '');
        break;
      case 'goal_check':
        setGoalStatus(data.checking ? 'checking' : 'idle');
        if (data.checking) addSystemLog(`[${time}] Evaluating goal...`, 'INFO');
        break;
      case 'goal_reached':
        setGoalStatus('reached');
        setIsNavigating(false);
        setGoalResult(JSON.stringify(data.result, null, 2));
        addSystemLog(`[${time}] GOAL REACHED!`, 'SUCCESS');
        {
          const details = Object.entries(data.result).map(([k, v]) => `• **${k}**: ${v}`).join('\n');
          addChatMessage(`🎉 Goal Reached! Details extracted:\n${details}`, 'agent');
        }
        setMissions(prev => prev.map(m => (m.status === 'running' ? { ...m, status: 'success' } : m)));
        break;
      case 'navigation_complete':
        setIsNavigating(false);
        addSystemLog(`[${time}] Navigation mission finished.`, 'INFO');
        break;
      case 'error':
        setIsNavigating(false);
        setGoalStatus('failed');
        addSystemLog(`[${time}] Agent Error: ${data.message}`, 'ERROR');
        addChatMessage(`🛑 Mission Failed: ${data.message}`, 'agent');
        setMissions(prev => prev.map(m => (m.status === 'running' ? { ...m, status: 'failed' } : m)));
        break;
      default:
        break;
    }
  };

  const connectToAgent = () => {
    if (reconnectTimeoutRef.current) { clearTimeout(reconnectTimeoutRef.current); reconnectTimeoutRef.current = null; }
    if (socketRef.current) socketRef.current.close();
    setWsStatus('connecting');
    addSystemLog('Connecting to Gemini Agent Service...', 'INFO');
    try {
      const socket = new WebSocket(agentUrl);
      socketRef.current = socket;

      socket.onopen = () => {
        setWsStatus('connected');
        manualDisconnectRef.current = false;
        addSystemLog('Successfully connected to agent server.', 'SUCCESS');
        addChatMessage('System connected successfully. Agent is ready for commands.', 'system');
      };

      socket.onmessage = (event) => {
        try { handleAgentEvent(JSON.parse(event.data)); }
        catch { addSystemLog(`Failed to parse WebSocket message: ${event.data}`, 'ERROR'); }
      };

      socket.onclose = (event) => {
        setWsStatus('disconnected');
        setIsNavigating(false);
        addSystemLog(`Disconnected from agent server (Code: ${event.code}).`, 'WARNING');
        addChatMessage('Agent server disconnected.', 'system');
        socketRef.current = null;
        if (!manualDisconnectRef.current) {
          addSystemLog('Attempting to reconnect in 5 seconds...', 'INFO');
          reconnectTimeoutRef.current = setTimeout(connectToAgent, 5000);
        }
      };

      socket.onerror = () => {
        setWsStatus('error');
        setIsNavigating(false);
        addSystemLog('WebSocket connection encountered an error.', 'ERROR');
        addChatMessage('Connection error encountered.', 'system');
      };
    } catch (err: any) {
      setWsStatus('error');
      addSystemLog(`Error establishing connection: ${err.message}`, 'ERROR');
    }
  };

  const disconnectFromAgent = () => {
    manualDisconnectRef.current = true;
    if (reconnectTimeoutRef.current) { clearTimeout(reconnectTimeoutRef.current); reconnectTimeoutRef.current = null; }
    if (socketRef.current) socketRef.current.close();
  };

  const triggerNavigation = (customRepo: string, customGoal: string, customStartUrl: string) => {
    if (!socketRef.current || wsStatus !== 'connected') { addChatMessage('Agent offline.', 'system'); return; }
    const payload = { type: 'navigate', url: customStartUrl, repo: customRepo, goal: customGoal };
    const uuid = Math.random().toString(36).substr(2, 9);
    const newMission: MissionHistory = { id: uuid, title: `Release info for ${customRepo}`, repo: customRepo, goal: customGoal, url: `/mission/${uuid}`, timestamp: new Date().toISOString(), status: 'running' };
    setMissions(prev => [newMission, ...prev]);
    setSelectedMissionId(uuid);
    socketRef.current.send(JSON.stringify(payload));
    setIsNavigating(true);
  };

  const stopMission = () => {
    if (!socketRef.current || wsStatus !== 'connected') return;
    socketRef.current.send(JSON.stringify({ type: 'stop' }));
    setIsNavigating(false);
    addSystemLog('Stop command sent.', 'WARNING');
    addChatMessage('🛑 Command abort issued.', 'system');
    setMissions(prev => prev.map(m => (m.status === 'running' ? { ...m, status: 'failed' } : m)));
  };

  const handleChatSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!chatInput.trim()) return;
    const inputMsg = chatInput;
    setChatInput('');
    addChatMessage(inputMsg, 'user');
    if (wsStatus !== 'connected') { addChatMessage('Agent offline.', 'system'); return; }
    if (isNavigating) { addChatMessage('Mission already running.', 'system'); return; }
    const repoRegex = /([a-zA-Z0-9_-]+\/[a-zA-Z0-9_-]+)/;
    const match = inputMsg.match(repoRegex);
    const targetRepo = match && match[1] ? match[1] : 'openclaw/openclaw';
    const targetStartUrl = `https://github.com/${targetRepo}`;
    setRepoName(targetRepo);
    setStartUrl(targetStartUrl);
    setGoal(inputMsg);
    triggerNavigation(targetRepo, inputMsg, targetStartUrl);
  };

  const loadHistoricalMission = (m: MissionHistory) => {
    setSelectedMissionId(m.id);
    setRepoName(m.repo);
    setStartUrl(m.url);
    setGoal(m.goal);
    setGoalResult(null);
    setScreenshot(null);
    setDomPreview('');
    addChatMessage(`Loaded mission "${m.title}".`, 'system');
  };

  const startNewMission = () => {
    setSelectedMissionId(null);
    setRepoName('openclaw/openclaw');
    setStartUrl('https://github.com/explore');
    setGoal('Find the latest release version, date, and author');
    setGoalResult(null);
    setScreenshot(null);
    setDomPreview('');
    setIsNavigating(false);
    addChatMessage('Ready for a new mission.', 'system');
  };

  // Auto‑connect on mount
  useEffect(() => {
    connectToAgent();
    return () => {
      if (reconnectTimeoutRef.current) clearTimeout(reconnectTimeoutRef.current);
      if (socketRef.current) socketRef.current.close();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const value: AgentContextValue = {
    agentUrl, setAgentUrl,
    wsStatus,
    sidebarOpen, setSidebarOpen,
    chatInput, setChatInput,
    chatMessages,
    missions,
    selectedMissionId,
    isNavigating,
    currentStep,
    currentUrl,
    screenshot,
    domPreview,
    logs,
    goalStatus,
    goalResult,
    connectToAgent,
    disconnectFromAgent,
    stopMission,
    handleChatSubmit,
    loadHistoricalMission,
    startNewMission,
  };

  return <AgentContext.Provider value={value}>{children}</AgentContext.Provider>;
}
