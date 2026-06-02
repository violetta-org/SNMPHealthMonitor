(function(){'use strict';const AI_API_URL='/api/ai/ask';const AI_HEALTH_URL='/api/ai/health-summary';const MAX_MESSAGE_LENGTH=500;let isOpen=false;let isLoading=false;let chatHistory=[];function getSysname(){const body=document.body;if(body.dataset.sysname)return body.dataset.sysname;const match=window.location.pathname.match(/\/dashboard\/([^/]+)/);if(match)return match[1];return null;}
function renderMarkdown(text){if(!text)return'';let html=text.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');html=html.replace(/```([\s\S]*?)```/g,'<pre><code>$1</code></pre>');html=html.replace(/`([^`]+)`/g,'<code>$1</code>');html=html.replace(/\*\*([^*]+)\*\*/g,'<strong>$1</strong>');html=html.replace(/(?<!\*)\*([^*]+)\*(?!\*)/g,'<em>$1</em>');html=html.replace(/^[\-\*] (.+)$/gm,'<li>$1</li>');html=html.replace(/(<li>.*<\/li>\n?)+/gs,'<ul>$&</ul>');html=html.replace(/^\d+\.\s(.+)$/gm,'<li>$1</li>');html=html.replace(/\n\n/g,'</p><p>');html=html.replace(/\n/g,'<br>');if(!html.startsWith('<')){html='<p>'+html+'</p>';}
return html;}
function createChatWidget(){const toggleBtn=document.createElement('button');toggleBtn.className='ai-chat-toggle';toggleBtn.id='ai-chat-toggle';toggleBtn.title='AI DevOps Assistant';toggleBtn.innerHTML=`
            <svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                <path d="M12 2C6.48 2 2 6.48 2 12c0 1.54.36 3 1 4.35L2 22l5.65-1C9 21.64 10.46 22 12 22c5.52 0 10-4.48 10-10S17.52 2 12 2zm-2 13.5l-3-3 1.41-1.41L10 12.67l5.59-5.59L17 8.5l-7 7z"/>
            </svg>`;const chatWindow=document.createElement('div');chatWindow.className='ai-chat-window';chatWindow.id='ai-chat-window';chatWindow.innerHTML=`
            <!-- Header -->
            <div class="ai-chat-header">
                <div class="ai-chat-header-left">
                    <div class="ai-chat-avatar">🤖</div>
                    <div class="ai-chat-header-info">
                        <h3>AIOps Assistant</h3>
                        <span>Đang hoạt động</span>
                    </div>
                </div>
                <div class="ai-chat-header-actions">
                    <button class="ai-header-btn" id="ai-btn-analyze" title="Tự động phân tích sức khỏe">
                        🔍
                    </button>
                    <button class="ai-header-btn" id="ai-btn-clear" title="Xóa lịch sử chat">
                        🗑️
                    </button>
                </div>
            </div>

            <!-- Messages -->
            <div class="ai-chat-messages" id="ai-chat-messages">
                <!-- Welcome message -->
            </div>

            <!-- Quick Actions -->
            <div class="ai-quick-actions" id="ai-quick-actions">
                <button class="ai-quick-btn" data-msg="Tình trạng server hiện tại thế nào?">📊 Tổng quan</button>
                <button class="ai-quick-btn" data-msg="CPU và RAM có đang ở mức an toàn không?">🔥 CPU & RAM</button>
                <button class="ai-quick-btn" data-msg="Ổ cứng còn bao nhiêu dung lượng trống?">💿 Disk</button>
                <button class="ai-quick-btn" data-msg="Có dấu hiệu bất thường nào không?">🚨 Bất thường</button>
            </div>

            <!-- Input Area -->
            <div class="ai-chat-input-area">
                <textarea class="ai-chat-input" id="ai-chat-input" 
                    placeholder="Hỏi AI về tình trạng server..." 
                    rows="1" maxlength="${MAX_MESSAGE_LENGTH}"></textarea>
                <button class="ai-send-btn" id="ai-send-btn" title="Gửi">
                    <svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                        <path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/>
                    </svg>
                </button>
            </div>
        `;document.body.appendChild(toggleBtn);document.body.appendChild(chatWindow);bindEvents(toggleBtn,chatWindow);addBotMessage('👋 Xin chào **Quản trị viên**! Tôi là **AIOps Assistant** — trợ lý AI chuyên phân tích sức khỏe hệ thống.\n\n'+'Bạn có thể hỏi tôi về tình trạng CPU, RAM, Disk, Network, hoặc bấm các nút gợi ý bên dưới để bắt đầu nhanh.');}
function bindEvents(toggleBtn,chatWindow){const input=document.getElementById('ai-chat-input');const sendBtn=document.getElementById('ai-send-btn');const clearBtn=document.getElementById('ai-btn-clear');const analyzeBtn=document.getElementById('ai-btn-analyze');const quickActions=document.getElementById('ai-quick-actions');toggleBtn.addEventListener('click',()=>{isOpen=!isOpen;chatWindow.classList.toggle('open',isOpen);toggleBtn.classList.toggle('active',isOpen);if(isOpen){toggleBtn.style.animation='none';input.focus();}else{toggleBtn.style.animation='';}});sendBtn.addEventListener('click',()=>sendMessage());input.addEventListener('keydown',(e)=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();sendMessage();}});input.addEventListener('input',()=>{input.style.height='auto';input.style.height=Math.min(input.scrollHeight,80)+'px';});clearBtn.addEventListener('click',()=>{const messages=document.getElementById('ai-chat-messages');messages.innerHTML='';chatHistory=[];addBotMessage('🔄 Lịch sử chat đã được xóa. Bạn có thể bắt đầu cuộc trò chuyện mới.');});analyzeBtn.addEventListener('click',()=>{const sysname=getSysname();if(!sysname){addBotMessage('⚠️ Không xác định được thiết bị. Vui lòng truy cập trang Dashboard của một thiết bị cụ thể để sử dụng tính năng phân tích tự động.');return;}
addUserMessage('🔍 Phân tích sức khỏe tổng quan');fetchHealthSummary(sysname);});quickActions.addEventListener('click',(e)=>{const btn=e.target.closest('.ai-quick-btn');if(btn&&btn.dataset.msg){input.value=btn.dataset.msg;sendMessage();}});}
function sendMessage(){if(isLoading)return;const input=document.getElementById('ai-chat-input');const message=input.value.trim();if(!message)return;if(message.length>MAX_MESSAGE_LENGTH){showToast(`Tin nhắn quá dài (tối đa ${MAX_MESSAGE_LENGTH} ký tự).`,'error');return;}
addUserMessage(message);input.value='';input.style.height='auto';const sysname=getSysname();fetchAIResponse(message,sysname);}
async function fetchAIResponse(message,sysname){setLoading(true);showTypingIndicator();try{const response=await fetch(AI_API_URL,{method:'POST',headers:{'Content-Type':'application/json','X-CSRFToken':getCSRFToken(),},body:JSON.stringify({message:message,sysname:sysname,}),});removeTypingIndicator();if(!response.ok){if(response.status===422){const errData=await response.json().catch(()=>null);const detail=errData?.detail;let errMsg='Dữ liệu không hợp lệ.';if(Array.isArray(detail)&&detail.length>0){errMsg=detail[0]?.msg||errMsg;}
addErrorMessage(errMsg);}else{addErrorMessage(`Lỗi server (HTTP ${response.status}). Vui lòng thử lại.`);}
return;}
const data=await response.json();if(!data.ok&&data.error){addErrorMessage(data.error);return;}
if(data.reply){addBotMessage(data.reply);}else{addErrorMessage('AI không trả về phản hồi. Vui lòng thử lại.');}}catch(err){removeTypingIndicator();console.error('AI Chat Error:',err);if(err.name==='TypeError'&&err.message.includes('fetch')){addErrorMessage('Không thể kết nối đến server. Kiểm tra lại kết nối mạng.');}else{addErrorMessage('Đã xảy ra lỗi không mong muốn. Vui lòng thử lại.');}}finally{setLoading(false);}}
async function fetchHealthSummary(sysname){setLoading(true);showTypingIndicator();try{const response=await fetch(`${AI_HEALTH_URL}/${sysname}`,{method:'GET',headers:{'X-CSRFToken':getCSRFToken()},});removeTypingIndicator();if(!response.ok){addErrorMessage(`Lỗi khi phân tích (HTTP ${response.status}).`);return;}
const data=await response.json();if(data.ok&&data.summary){addBotMessage(data.summary);}else if(data.error){addErrorMessage(data.error);}else{addErrorMessage('Không thể phân tích lúc này.');}}catch(err){removeTypingIndicator();addErrorMessage('Lỗi kết nối khi phân tích sức khỏe.');}finally{setLoading(false);}}
function addUserMessage(text){const messages=document.getElementById('ai-chat-messages');const msgEl=document.createElement('div');msgEl.className='ai-message user';msgEl.innerHTML=`
            <div class="ai-msg-avatar">👤</div>
            <div class="ai-msg-content">${escapeHtml(text)}</div>
        `;messages.appendChild(msgEl);scrollToBottom();chatHistory.push({role:'user',content:text});}
function addBotMessage(text){const messages=document.getElementById('ai-chat-messages');const msgEl=document.createElement('div');msgEl.className='ai-message bot';msgEl.innerHTML=`
            <div class="ai-msg-avatar">🤖</div>
            <div class="ai-msg-content">${renderMarkdown(text)}</div>
        `;messages.appendChild(msgEl);scrollToBottom();chatHistory.push({role:'bot',content:text});}
function addErrorMessage(text){const messages=document.getElementById('ai-chat-messages');const msgEl=document.createElement('div');msgEl.className='ai-message bot error';msgEl.innerHTML=`
            <div class="ai-msg-avatar">⚠️</div>
            <div class="ai-msg-content">❌ ${escapeHtml(text)}</div>
        `;messages.appendChild(msgEl);scrollToBottom();}
function showTypingIndicator(){const messages=document.getElementById('ai-chat-messages');removeTypingIndicator();const typing=document.createElement('div');typing.className='ai-typing';typing.id='ai-typing-indicator';typing.innerHTML=`
            <div class="ai-msg-avatar" style="background: linear-gradient(135deg, #6c63ff, #4834d4); border-radius: 50%; width: 28px; height: 28px; display: flex; align-items: center; justify-content: center; font-size: 14px;">🤖</div>
            <div class="ai-typing-dots">
                <span></span><span></span><span></span>
            </div>
        `;messages.appendChild(typing);scrollToBottom();}
function removeTypingIndicator(){const typing=document.getElementById('ai-typing-indicator');if(typing)typing.remove();}
function setLoading(loading){isLoading=loading;const sendBtn=document.getElementById('ai-send-btn');const input=document.getElementById('ai-chat-input');if(sendBtn)sendBtn.disabled=loading;if(input)input.disabled=loading;}
function scrollToBottom(){const messages=document.getElementById('ai-chat-messages');if(messages){requestAnimationFrame(()=>{const last=messages.lastElementChild;if(last)last.scrollIntoView({behavior:'smooth',block:'end'});});}}
function escapeHtml(text){const div=document.createElement('div');div.textContent=text;return div.innerHTML;}
function getCSRFToken(){const cookie=document.cookie.split(';').find(c=>c.trim().startsWith('csrftoken='));if(cookie)return cookie.split('=')[1];const meta=document.querySelector('meta[name="csrf-token"]');if(meta)return meta.content;return'';}
function showToast(message,type='error'){const toast=document.createElement('div');toast.className=`ai-toast ${type}`;toast.textContent=message;document.body.appendChild(toast);setTimeout(()=>toast.remove(),4000);}
if(document.readyState==='loading'){document.addEventListener('DOMContentLoaded',createChatWidget);}else{createChatWidget();}})();