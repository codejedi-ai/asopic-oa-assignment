import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'ice';
import { useAgent } from '@/context/AgentContext';
import styles from '@/styles/app.module.css';

export default function ChatPanel() {
  const {
    chatMessages, chatInput, setChatInput, handleChatSubmit, wsStatus, isNavigating, stopMission,
    selectedMissionId, missions, renameMission,
  } = useAgent();
  const navigate = useNavigate();
  const chatEndRef = useRef<HTMLDivElement>(null);

  const currentMission = missions.find(m => m.id === selectedMissionId);
  const currentTitle = currentMission?.title ?? (selectedMissionId ? 'Mission' : 'New Mission');

  const [editing, setEditing] = useState(false);
  const [draftTitle, setDraftTitle] = useState('');

  useEffect(() => {
    if (chatEndRef.current) chatEndRef.current.scrollIntoView({ behavior: 'smooth' });
  }, [chatMessages]);

  const onSubmit = (e: React.FormEvent) => {
    const newMissionId = handleChatSubmit(e);
    if (newMissionId) navigate(`/mission/${newMissionId}`);
  };

  const startEdit = () => {
    if (!selectedMissionId) return; // the fresh draft has no mission to rename yet
    setDraftTitle(currentTitle);
    setEditing(true);
  };
  const commitEdit = () => {
    if (selectedMissionId && draftTitle.trim()) renameMission(selectedMissionId, draftTitle);
    setEditing(false);
  };

  return (
    <section className={styles.pagePanel}>
      <header className={styles.panelHeader}>
        <div className={styles.panelHeaderTitle}>
          <span className={styles.chatHeaderIcon}>💬</span>
          {editing ? (
            <input
              className={styles.titleInput}
              value={draftTitle}
              autoFocus
              onChange={e => setDraftTitle(e.target.value)}
              onBlur={commitEdit}
              onKeyDown={e => {
                if (e.key === 'Enter') commitEdit();
                if (e.key === 'Escape') setEditing(false);
              }}
            />
          ) : (
            <button
              type="button"
              className={styles.titleButton}
              onClick={startEdit}
              title={selectedMissionId ? 'Click to rename this chat' : undefined}
            >
              <h3>{currentTitle}</h3>
              {selectedMissionId && <span className={styles.titleEdit}>✏️</span>}
            </button>
          )}
        </div>
      </header>
      <div className={styles.chatHistory}>
        {chatMessages.map(msg => (
          <div key={msg.id} className={`${styles.chatMessage} ${styles[msg.sender]}`}>
            <div className={styles.chatAvatar}>
              {msg.thought ? '🧠' : msg.sender === 'user' ? '👤' : msg.sender === 'agent' ? '🤖' : '⚙️'}
            </div>
            <div className={`${styles.chatBubble} ${msg.thought ? styles.thoughtBubble : ''}`}>
              {msg.thought && <span className={styles.thoughtLabel}>Clio is thinking…</span>}
              <p className={styles.chatText}>{msg.text}</p>
              {(msg.image || msg.imageUrl) && (
                <img
                  className={styles.chatScreenshot}
                  src={msg.image ? `data:image/png;base64,${msg.image}` : msg.imageUrl}
                  alt="Navigation screenshot"
                />
              )}
              <span className={styles.chatTime}>
                {new Date(msg.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
              </span>
            </div>
          </div>
        ))}
        <div ref={chatEndRef} />
      </div>
      <form onSubmit={onSubmit} className={styles.chatInputForm}>
        <input
          type="text"
          value={chatInput}
          onChange={e => setChatInput(e.target.value)}
          placeholder={wsStatus !== 'connected' ? 'Server offline...' : isNavigating ? 'Mission running…' : 'Ask Clio...'}
          disabled={wsStatus !== 'connected' || isNavigating}
          className={styles.chatTextInput}
        />
        {isNavigating ? (
          <button type="button" onClick={stopMission} className={styles.chatStopBtn}>
            ⏹ Stop
          </button>
        ) : (
          <button
            type="submit"
            disabled={wsStatus !== 'connected' || !chatInput.trim()}
            className={styles.chatSendBtn}
          >
            Send
          </button>
        )}
      </form>
    </section>
  );
}
