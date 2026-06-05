import { get, post } from "./api.js";
import { getAuthSession } from "./api.js";

// Basic WhatsApp implementation + Advanced API fallback if wanted.
// The user prompt recommends WhatsApp as StartUp version, so we provide
// a hybrid. The floating widget will have a "Live Chat" panel or link to WA.

export function initChatWidget() {
  const mount = document.getElementById("live-chat-mount");
  if (!mount) {
    // try to append to body if no mount point
    const div = document.createElement("div");
    div.id = "live-chat-mount";
    document.body.appendChild(div);
  }
  
  const container = document.getElementById("live-chat-mount");
  
  // We build a hybrid widget that can do native or WhatsApp
  container.innerHTML = `
    <div class="chat-widget">
      <div class="chat-panel" id="live-chat-panel">
        <div class="chat-header">
          <div class="chat-header-title">Live Support</div>
          <button class="chat-header-close" id="chat-close-btn">✕</button>
        </div>
        <div class="chat-messages" id="chat-messages-container">
          <div class="chat-bubble admin">Hi there! How can we help you today?</div>
        </div>
        <form class="chat-input-area" id="chat-form">
          <input type="text" id="chat-input" placeholder="Type a message..." required autocomplete="off">
          <button type="submit" aria-label="Send message">
            <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2"><line x1="22" y1="2" x2="11" y2="13"></line><polygon points="22 2 15 22 11 13 2 9 22 2"></polygon></svg>
          </button>
        </form>
        <div style="background:#fafafa;text-align:center;padding-bottom:0.5rem;">
          <a href="https://wa.me/919876543210?text=Hi%20I%20need%20help" target="_blank" style="font-size:0.8rem;color:var(--success);text-decoration:none;font-weight:600;">
            Or chat with us on WhatsApp
          </a>
        </div>
      </div>
      <button class="chat-toggle" id="chat-toggle-btn" aria-label="Open Live Chat">
        💬
      </button>
    </div>
  `;

  const toggleBtn = document.getElementById("chat-toggle-btn");
  const closeBtn = document.getElementById("chat-close-btn");
  const panel = document.getElementById("live-chat-panel");
  const form = document.getElementById("chat-form");
  const input = document.getElementById("chat-input");
  const messagesContainer = document.getElementById("chat-messages-container");

  let threadId = localStorage.getItem("chat_thread_id") || null;

  async function loadMessages() {
    if (!threadId) return;
    try {
      const msgs = await get(`/api/v1/chat/messages?thread_id=${threadId}`);
      if (msgs && msgs.length > 0) {
        messagesContainer.innerHTML = "";
        msgs.forEach(m => appendMessage(m.role, m.message));
        scrollToBottom();
      }
    } catch(e) {
      console.warn("Could not load chat messages", e);
    }
  }

  function appendMessage(role, text) {
    const div = document.createElement("div");
    div.className = `chat-bubble ${role}`;
    div.textContent = text;
    messagesContainer.appendChild(div);
  }

  function scrollToBottom() {
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
  }

  toggleBtn.addEventListener("click", () => {
    panel.classList.toggle("open");
    if (panel.classList.contains("open")) {
      loadMessages();
      input.focus();
    }
  });

  closeBtn.addEventListener("click", () => {
    panel.classList.remove("open");
  });

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const text = input.value.trim();
    if (!text) return;

    appendMessage("user", text);
    input.value = "";
    scrollToBottom();

    try {
      const res = await post("/api/v1/chat/send", {
        message: text,
        thread_id: threadId
      });
      if (res.thread_id) {
        threadId = res.thread_id;
        localStorage.setItem("chat_thread_id", threadId);
      }
      
      // simulated delay response if no admins
      setTimeout(() => {
        appendMessage("admin", "We have received your message. Our team will review it shortly. For immediate assistance, use the WhatsApp link below.");
        scrollToBottom();
      }, 1500);

    } catch (err) {
      appendMessage("admin", "Network error. Please use WhatsApp.");
      scrollToBottom();
    }
  });

  // check if there's unread logic could go here
}
