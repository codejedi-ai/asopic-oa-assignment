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
  image?: string;     // base64 PNG (live screenshot) shown inline
  imageUrl?: string;  // URL to a persisted screenshot (reconstructed history)
  thought?: boolean;  // styled as a reasoning bubble
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
  handleChatSubmit: (e: React.FormEvent) => string | null;
  loadHistoricalMission: (m: MissionHistory) => void;
  openMissionById: (id: string) => void;
  renameMission: (id: string, title: string) => void;
  startNewMission: () => void;
}

const AgentContext = createContext<AgentContextValue | null>(null);

// Thread key for the not-yet-started "new mission" conversation.
const DRAFT_KEY = '__draft__';

const makeMessage = (
  text: string,
  sender: ChatMessage['sender'],
  extra: Partial<Pick<ChatMessage, 'image' | 'imageUrl' | 'thought'>> = {},
): ChatMessage => ({
  id: Math.random().toString(36).substr(2, 9),
  sender,
  text,
  timestamp: new Date().toISOString(),
  ...extra,
});

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

  // Each mission has its own chat thread, keyed by mission id. The DRAFT_KEY
  // thread is the fresh "new mission" conversation shown at /mission (no id yet).
  const makeWelcome = (): ChatMessage => ({
    id: 'welcome',
    sender: 'agent',
    text: 'Hello! I am Clio, your vision‑based GitHub Release Navigator. Issue a command in the input below to start a mission, e.g., "Find the latest release for openclaw/openclaw"',
    timestamp: new Date().toISOString(),
  });
  const [threads, setThreads] = useState<Record<string, ChatMessage[]>>({ [DRAFT_KEY]: [makeWelcome()] });
  const [activeMissionId, setActiveMissionId] = useState<string | null>(null);
  const activeKeyRef = useRef<string>(DRAFT_KEY);
  const runningMissionIdRef = useRef<string | null>(null);
  useEffect(() => { activeKeyRef.current = activeMissionId ?? DRAFT_KEY; }, [activeMissionId]);

  const chatMessages = threads[activeMissionId ?? DRAFT_KEY] ?? [];

  const [missions, setMissions] = useState<MissionHistory[]>([]);
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

  // Derive the agent's HTTP base from the WebSocket URL (ws://host:port/ws -> http://host:port).
  const httpBase = () => agentUrl.replace(/^ws/, 'http').replace(/\/ws\/?$/, '');

  const mapStatus = (s: string): MissionHistory['status'] =>
    s === 'success' ? 'success' : s === 'failed' ? 'failed' : s === 'running' ? 'running' : 'idle';

  // Load persisted missions from ~/.clio (via the agent's /missions endpoint) so
  // the history list survives reloads.
  const loadPersistedMissions = async () => {
    try {
      const res = await fetch(`${httpBase()}/missions`);
      if (!res.ok) return;
      const json = await res.json();
      const persisted: MissionHistory[] = (json.missions || []).map((m: any) => ({
        id: m.id,
        title: m.title || (m.repo ? `Release info for ${m.repo}` : ((m.goal || 'Mission').slice(0, 40))),
        repo: m.repo || '',
        goal: m.goal || '',
        url: `/mission/${m.id}`,
        timestamp: m.created_at || new Date().toISOString(),
        status: mapStatus(m.status),
      }));
      setMissions(prev => {
        const ids = new Set(persisted.map(p => p.id));
        const extra = prev.filter(p => !ids.has(p.id));
        return [...extra, ...persisted];
      });
    } catch {
      /* agent offline — ignore */
    }
  };

  // Rebuild a chat thread from a persisted mission's event log + screenshots.
  const buildThreadFromMission = (id: string, detail: any): ChatMessage[] => {
    const out: ChatMessage[] = [];
    const push = (text: string, sender: ChatMessage['sender'], extra: any = {}) =>
      out.push(makeMessage(text, sender, extra));
    for (const ev of detail.events || []) {
      const d = ev.data || {};
      switch (ev.type) {
        case 'navigation_start':
          push(`🤖 Mission Started!\nTarget Repo: ${d.repo_name || 'unknown'}\nGoal: "${d.goal}"`, 'agent');
          break;
        case 'navigation_step':
          push(`🤖 [Step ${d.step}] Inspecting ${d.current_url}...`, 'agent');
          break;
        case 'screenshot':
          push(`📸 Step ${d.step ?? ''} — what Clio saw`, 'agent', {
            imageUrl: `${httpBase()}/missions/${id}/screenshot/step_${d.step}`,
          });
          break;
        case 'model_invoke_complete':
          if (d.result?.reasoning) push(`${d.result.reasoning}`, 'agent', { thought: true });
          break;
        case 'action_execute':
          push(`➡️ ${d.action_type === 'navigate' ? 'Navigating to' : 'Clicking'} "${d.target}"`, 'agent');
          break;
        default:
          break;
      }
    }
    const result = detail.meta?.result;
    if (result && typeof result === 'object' && Object.keys(result).length) {
      const details = Object.entries(result).map(([k, v]) => `• ${k}: ${v}`).join('\n');
      push(`✅ Result:\n${details}`, 'agent');
    }
    if (!out.length) push('This mission has no saved conversation.', 'system');
    return out;
  };

  const appendToThread = (
    key: string,
    text: string,
    sender: ChatMessage['sender'],
    extra: Partial<Pick<ChatMessage, 'image' | 'imageUrl' | 'thought'>> = {},
  ) => {
    setThreads(prev => ({ ...prev, [key]: [...(prev[key] ?? []), makeMessage(text, sender, extra)] }));
  };

  // Agent/system messages flow into the running mission's thread when a mission
  // is active, otherwise into whatever thread is currently being viewed.
  const addChatMessage = (
    text: string,
    sender: ChatMessage['sender'],
    extra: Partial<Pick<ChatMessage, 'image' | 'imageUrl' | 'thought'>> = {},
  ) => {
    appendToThread(runningMissionIdRef.current ?? activeKeyRef.current, text, sender, extra);
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
        // Reflect the resolved repo in the history title — but never touch m.url
        // (that is the /mission/<uuid> route the history list links to).
        if (data.repo_name && data.repo_name !== 'unknown') {
          setMissions(prev => prev.map(m => (m.status === 'running' ? { ...m, repo: data.repo_name, title: `Release info for ${data.repo_name}` } : m)));
        }
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
        // Also drop the screenshot inline into the chat so the per-step trace
        // shows text + thought + image together.
        if (data.screenshot_base64) {
          addChatMessage(`📸 Step ${data.step ?? ''} — what Clio sees`, 'agent', { image: data.screenshot_base64 });
        }
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
          const details = Object.entries(data.result || {}).map(([k, v]) => `• ${k}: ${v}`).join('\n');
          addChatMessage(
            `✅ All done! Here's what I found:\n${details}\n\nAsk me about another repo whenever you like.`,
            'agent',
          );
        }
        setMissions(prev => prev.map(m => (m.status === 'running' ? { ...m, status: 'success' } : m)));
        runningMissionIdRef.current = null;
        break;
      case 'navigation_complete':
        setIsNavigating(false);
        addSystemLog(`[${time}] Navigation mission finished.${data.reason ? ' ' + data.reason : ''}`, 'INFO');
        if (data.reason) addChatMessage(`🏁 ${data.reason}`, 'agent');
        runningMissionIdRef.current = null;
        break;
      // ---- Streamed "thoughts" (the agent reasoning out loud) ----
      case 'model_invoke_start':
        addSystemLog(`[${time}] 🧠 ${data.model}: ${data.purpose || 'thinking...'}`, 'INFO');
        break;
      case 'model_invoke_complete': {
        addSystemLog(`[${time}] 🧠 ${data.model} responded`, 'SUCCESS');
        const r = data.result;
        if (r && typeof r === 'object') {
          if (r.reasoning) {
            addChatMessage(`${r.reasoning}${r.confidence != null ? ` (confidence ${r.confidence})` : ''}`, 'agent', { thought: true });
          } else if (r.weights) {
            addChatMessage(`Prioritising links by: ${Object.keys(r.weights).slice(0, 6).join(', ')}`, 'agent', { thought: true });
          }
        }
        break;
      }
      case 'candidates_found':
        addSystemLog(`[${time}] Found ${data.count} candidate link(s)`, 'INFO');
        break;
      case 'action_execute': {
        const score = typeof data.score === 'number' ? data.score.toFixed(2) : data.score;
        addSystemLog(`[${time}] ${data.action_type} → "${data.target}" (score ${score})`, 'INFO');
        addChatMessage(`➡️ ${data.action_type === 'navigate' ? 'Navigating to' : 'Clicking'} "${data.target}"`, 'agent');
        break;
      }
      case 'action_result':
        addSystemLog(
          `[${time}] Action ${data.success ? 'succeeded' : 'failed'}${data.error ? ': ' + data.error : ''}`,
          data.success ? 'SUCCESS' : 'WARNING',
        );
        break;
      case 'disconnected':
        addSystemLog(`[${time}] ${data.status || 'Navigator disconnected'}`, 'INFO');
        break;
      case 'navigation_error':
      case 'error': {
        const errMsg = data.error || data.message || 'Unknown error';
        setIsNavigating(false);
        setGoalStatus('failed');
        addSystemLog(`[${time}] Agent Error: ${errMsg}`, 'ERROR');
        addChatMessage(`🛑 Mission Failed: ${errMsg}`, 'agent');
        setMissions(prev => prev.map(m => (m.status === 'running' ? { ...m, status: 'failed' } : m)));
        runningMissionIdRef.current = null;
        break;
      }
      default:
        break;
    }
  };

  const connectToAgent = () => {
    // Idempotency guard: never open a second socket if one is already open or
    // connecting. (StrictMode double-mount + the reconnect timer would otherwise
    // stack up multiple live sockets — each replaying every event -> "quadruple
    // executing" in the UI.)
    const existing = socketRef.current;
    if (existing && (existing.readyState === WebSocket.OPEN || existing.readyState === WebSocket.CONNECTING)) {
      return;
    }
    if (reconnectTimeoutRef.current) { clearTimeout(reconnectTimeoutRef.current); reconnectTimeoutRef.current = null; }
    setWsStatus('connecting');
    addSystemLog('Connecting to Clio Agent Service...', 'INFO');
    try {
      const socket = new WebSocket(agentUrl);
      socketRef.current = socket;

      // Any handler from a socket that is no longer the current one is ignored,
      // so a leaked/stale socket can't double-process events or trigger reconnects.
      const isCurrent = () => socketRef.current === socket;

      socket.onopen = () => {
        if (!isCurrent()) { socket.close(); return; }
        setWsStatus('connected');
        manualDisconnectRef.current = false;
        addSystemLog('Successfully connected to agent server.', 'SUCCESS');
        addChatMessage('System connected successfully. Agent is ready for commands.', 'system');
        loadPersistedMissions();
      };

      socket.onmessage = (event) => {
        if (!isCurrent()) return;
        try { handleAgentEvent(JSON.parse(event.data)); }
        catch { addSystemLog(`Failed to parse WebSocket message: ${event.data}`, 'ERROR'); }
      };

      socket.onclose = (event) => {
        if (!isCurrent()) return; // a stale socket closing — don't touch state or reconnect
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
        if (!isCurrent()) return;
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

  // Starts a brand‑new mission: mints a uuid, opens a fresh chat thread for it
  // (seeded with the user's command), and points the agent stream at it.
  const triggerNavigation = (customRepo: string, customGoal: string, customStartUrl: string): string | null => {
    if (!socketRef.current || wsStatus !== 'connected') { addChatMessage('Agent offline.', 'system'); return null; }
    const uuid = Math.random().toString(36).substr(2, 9);
    const payload = { type: 'navigate', url: customStartUrl, repo: customRepo, goal: customGoal, mission_id: uuid };
    const title = customRepo ? `Release info for ${customRepo}` : (customGoal.length > 40 ? `${customGoal.slice(0, 40)}…` : customGoal);
    const newMission: MissionHistory = { id: uuid, title, repo: customRepo, goal: customGoal, url: `/mission/${uuid}`, timestamp: new Date().toISOString(), status: 'running' };
    setMissions(prev => [newMission, ...prev]);
    setThreads(prev => ({ ...prev, [uuid]: [makeMessage(customGoal, 'user')] }));
    runningMissionIdRef.current = uuid;
    activeKeyRef.current = uuid;
    setActiveMissionId(uuid);
    setSelectedMissionId(uuid);
    socketRef.current.send(JSON.stringify(payload));
    setIsNavigating(true);
    return uuid;
  };

  // Continue an existing mission: reuse its id + chat thread (no new sidebar
  // entry), send a follow-up command under the same mission_id.
  const continueMission = (missionId: string, goal: string): string | null => {
    if (!socketRef.current || wsStatus !== 'connected') { addChatMessage('Agent offline.', 'system'); return null; }
    const mission = missions.find(m => m.id === missionId);
    const repoMatch = goal.match(/\b([a-zA-Z0-9_.-]+\/[a-zA-Z0-9_.-]+)\b/);
    const repo = (mission && mission.repo) || (repoMatch && repoMatch[1]) || '';
    const startUrl = repo ? `https://github.com/${repo}` : 'https://github.com';
    const payload = { type: 'navigate', url: startUrl, repo, goal, mission_id: missionId };
    appendToThread(missionId, goal, 'user');
    runningMissionIdRef.current = missionId;
    activeKeyRef.current = missionId;
    setActiveMissionId(missionId);
    setSelectedMissionId(missionId);
    setMissions(prev => prev.map(m => (m.id === missionId ? { ...m, status: 'running' } : m)));
    socketRef.current.send(JSON.stringify(payload));
    setIsNavigating(true);
    return missionId;
  };

  // Rename a mission (updates the sidebar + chat header, persisted to ~/.clio).
  const renameMission = (id: string, title: string) => {
    const t = title.trim();
    if (!t) return;
    setMissions(prev => prev.map(m => (m.id === id ? { ...m, title: t } : m)));
    fetch(`${httpBase()}/missions/${id}/rename`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title: t }),
    }).catch(() => { /* offline — local rename still applies */ });
  };

  const stopMission = () => {
    if (!socketRef.current || wsStatus !== 'connected') return;
    socketRef.current.send(JSON.stringify({ type: 'stop' }));
    setIsNavigating(false);
    addSystemLog('Stop command sent.', 'WARNING');
    addChatMessage('🛑 Command abort issued.', 'system');
    setMissions(prev => prev.map(m => (m.status === 'running' ? { ...m, status: 'failed' } : m)));
    runningMissionIdRef.current = null;
  };

  const handleChatSubmit = (e: React.FormEvent): string | null => {
    e.preventDefault();
    if (!chatInput.trim()) return null;
    const inputMsg = chatInput;
    setChatInput('');
    if (wsStatus !== 'connected') {
      appendToThread(activeKeyRef.current, inputMsg, 'user');
      appendToThread(activeKeyRef.current, 'Agent offline.', 'system');
      return null;
    }
    if (isNavigating) {
      appendToThread(activeKeyRef.current, inputMsg, 'user');
      appendToThread(activeKeyRef.current, 'A mission is already running. Stop it before sending another command.', 'system');
      return null;
    }
    // If we're viewing an existing mission, continue it (same id + chat thread)
    // instead of starting a new one. Only the fresh draft starts a new mission.
    if (activeMissionId) {
      return continueMission(activeMissionId, inputMsg);
    }
    // Only treat an explicit "owner/repo" as the target. Otherwise leave it
    // empty so the agent resolves the repo from the request via web search
    // (instead of defaulting to a hardcoded repo).
    const repoRegex = /\b([a-zA-Z0-9_.-]+\/[a-zA-Z0-9_.-]+)\b/;
    const match = inputMsg.match(repoRegex);
    const targetRepo = match && match[1] ? match[1] : '';
    const targetStartUrl = targetRepo ? `https://github.com/${targetRepo}` : 'https://github.com';
    setRepoName(targetRepo);
    setStartUrl(targetStartUrl);
    setGoal(inputMsg);
    return triggerNavigation(targetRepo, inputMsg, targetStartUrl);
  };

  // Show a mission's own chat thread (used by the /mission/:id route). If the
  // thread isn't already in memory, reconstruct it from the persisted log on disk.
  const openMissionById = (id: string) => {
    setActiveMissionId(id);
    setSelectedMissionId(id);
    if (threads[id]) return;
    // Seed a placeholder immediately, then hydrate from disk.
    setThreads(prev => (prev[id] ? prev : { ...prev, [id]: [makeMessage('Loading mission log…', 'system')] }));
    (async () => {
      try {
        const res = await fetch(`${httpBase()}/missions/${id}`);
        if (!res.ok) return;
        const detail = await res.json();
        const rebuilt = buildThreadFromMission(id, detail);
        setThreads(prev => ({ ...prev, [id]: rebuilt }));
      } catch {
        /* offline — leave placeholder */
      }
    })();
  };

  const loadHistoricalMission = (m: MissionHistory) => {
    setRepoName(m.repo);
    setStartUrl(m.url);
    setGoal(m.goal);
    openMissionById(m.id);
  };

  // Returns to the fresh "new mission" draft conversation at /mission.
  const startNewMission = () => {
    runningMissionIdRef.current = null;
    activeKeyRef.current = DRAFT_KEY;
    setActiveMissionId(null);
    setSelectedMissionId(null);
    setThreads(prev => ({ ...prev, [DRAFT_KEY]: [makeWelcome()] }));
    setRepoName('openclaw/openclaw');
    setStartUrl('https://github.com/explore');
    setGoal('Find the latest release version, date, and author');
    setGoalResult(null);
    setScreenshot(null);
    setDomPreview('');
    setIsNavigating(false);
  };

  // Auto‑connect on mount
  useEffect(() => {
    connectToAgent();
    return () => {
      // Mark manual so the closing socket doesn't schedule a reconnect, and drop
      // the ref so its onclose is treated as stale.
      manualDisconnectRef.current = true;
      if (reconnectTimeoutRef.current) clearTimeout(reconnectTimeoutRef.current);
      const s = socketRef.current;
      socketRef.current = null;
      if (s) s.close();
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
    openMissionById,
    renameMission,
    startNewMission,
  };

  return <AgentContext.Provider value={value}>{children}</AgentContext.Provider>;
}
