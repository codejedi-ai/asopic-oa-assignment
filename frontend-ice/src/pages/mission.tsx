import { useEffect, useRef } from 'react';
import logo from '@/assets/logo.png';
import { useAgent } from '@/context/AgentContext';
import styles from '@/styles/app.module.css';

export default function MissionPage() {
  const { chatMessages, chatInput, setChatInput, handleChatSubmit, wsStatus, isNavigating } = useAgent();
  const chatEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (chatEndRef.current) chatEndRef.current.scrollIntoView({ behavior: 'smooth' });
  }, [chatMessages]);

  return (
    <section className={styles.pagePanel}>
      <header className={styles.panelHeader}>
        <div className={styles.panelHeaderTitle}>
          <img src={logo} className={styles.panelLogo} alt="Logo" />
          <h3>💬 GEMINI CHAT ASSISTANT</h3>
        </div>
      </header>
      <div className={styles.chatHistory}>
        {chatMessages.map(msg => (
          <div key={msg.id} className={`${styles.chatMessage} ${styles[msg.sender]}`}>
            <div className={styles.chatAvatar}>
              {msg.sender === 'user' && '👤'}{msg.sender === 'agent' && '🤖'}{msg.sender === 'system' && '⚙️'}
            </div>
            <div className={styles.chatBubble}>
              <p className={styles.chatText}>{msg.text}</p>
              <span className={styles.chatTime}>
                {new Date(msg.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
              </span>
            </div>
          </div>
        ))}
        <div ref={chatEndRef} />
      </div>
      <form onSubmit={handleChatSubmit} className={styles.chatInputForm}>
        <input
          type="text"
          value={chatInput}
          onChange={e => setChatInput(e.target.value)}
          placeholder={wsStatus !== 'connected' ? 'Server offline...' : 'Ask Gemini...'}
          disabled={wsStatus !== 'connected' || isNavigating}
          className={styles.chatTextInput}
        />
        <button
          type="submit"
          disabled={wsStatus !== 'connected' || isNavigating || !chatInput.trim()}
          className={styles.chatSendBtn}
        >
          Send
        </button>
      </form>
    </section>
  );
}
