import { Component, OnInit, signal, computed, inject, ElementRef, ViewChild, AfterViewChecked } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { RouterModule, ActivatedRoute } from '@angular/router';
import { ApiService, ChatSessionSummary, ChatMessage } from '../../../../core/api.service';
import { ToastService } from '../../../../core/toast.service';
import { AuthModalService } from '../../../../core/auth-modal.service';
import { MarkdownPreviewComponent } from '../../../../shared/markdown-preview/markdown-preview.component';

@Component({
  selector: 'app-chat-tab',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterModule, MarkdownPreviewComponent],
  templateUrl: './chat-tab.component.html',
  styleUrls: ['./chat-tab.component.scss']
})
export class ChatTabComponent implements OnInit, AfterViewChecked {
  @ViewChild('messagesScroll') private messagesScrollContainer?: ElementRef;

  chats = signal<ChatSessionSummary[]>([]);
  activeChatId = signal<string | null>(null);
  activeChat = computed<ChatSessionSummary | null>(() => {
    const id = this.activeChatId();
    if (!id) return null;
    return this.chats().find(c => c.id === id) || null;
  });
  messages = signal<ChatMessage[]>([]);
  
  inputText: string = '';
  isSending = signal<boolean>(false);
  isLoadingChats = signal<boolean>(false);
  isLoadingMessages = signal<boolean>(false);
  expandedToolTraceIds = signal<Set<string>>(new Set());

  quickPrompts: string[] = [
    'Summarize key literature gaps',
    'Extract conflicting claims & disputes',
    'Explain methodology differences',
    'Draft a research introduction outline'
  ];

  public authModalService = inject(AuthModalService);
  private apiService = inject(ApiService);
  private route = inject(ActivatedRoute);
  private toastService = inject(ToastService);
  projectId: string | null = null;
  private shouldScrollToBottom: boolean = false;

  getEffectiveProjectId(): string | null {
    if (this.projectId) return this.projectId;
    const parentId = this.route.parent?.snapshot.paramMap.get('id');
    const selfId = this.route.snapshot.paramMap.get('id');
    if (parentId || selfId) return parentId || selfId;
    if (typeof window !== 'undefined' && window.location) {
      const parts = window.location.pathname.split('/projects/');
      if (parts.length > 1) {
        const id = parts[1].split('/')[0];
        if (id) return id;
      }
    }
    return null;
  }

  hasApiKey = computed(() => this.authModalService.hasValidCredentials());

  openAuthModal(): void {
    this.authModalService.open();
  }

  ngOnInit() {
    this.projectId = this.getEffectiveProjectId();
    if (this.projectId) {
      this.loadChats();
    }
    this.authModalService.refreshAuthStatus().subscribe({
      error: () => {}
    });
    this.route.parent?.paramMap.subscribe(params => {
      const id = params.get('id') || this.getEffectiveProjectId();
      if (id && id !== this.projectId) {
        this.projectId = id;
        this.loadChats();
      }
    });
  }

  ngAfterViewChecked() {
    if (this.shouldScrollToBottom) {
      this.scrollToBottom();
      this.shouldScrollToBottom = false;
    }
  }

  scrollToBottom() {
    try {
      if (this.messagesScrollContainer) {
        this.messagesScrollContainer.nativeElement.scrollTop = 
          this.messagesScrollContainer.nativeElement.scrollHeight;
      }
    } catch (err) {}
  }

  loadChats() {
    const pid = this.getEffectiveProjectId();
    if (!pid) return;
    this.projectId = pid;
    this.isLoadingChats.set(true);

    this.apiService.listProjectChats(pid).subscribe({
      next: chats => {
        this.isLoadingChats.set(false);
        this.chats.set(chats);
        if (chats.length > 0) {
          if (!this.activeChatId() || !chats.find(c => c.id === this.activeChatId())) {
            this.selectChat(chats[0].id);
          }
        } else {
          this.activeChatId.set(null);
          this.messages.set([]);
        }
      },
      error: err => {
        this.isLoadingChats.set(false);
        console.error('Error loading chats:', err);
        this.toastService.error('Error', 'Failed to load project chats');
      }
    });
  }

  loadProjectChats() {
    this.loadChats();
  }

  selectChat(chatId: string) {
    const pid = this.getEffectiveProjectId();
    if (!pid) return;
    this.activeChatId.set(chatId);
    this.isLoadingMessages.set(true);
    this.apiService.getChatMessages(pid, chatId).subscribe({
      next: msgs => {
        this.isLoadingMessages.set(false);
        this.messages.set(msgs);
        this.shouldScrollToBottom = true;
      },
      error: err => {
        this.isLoadingMessages.set(false);
        console.error('Error loading messages:', err);
        this.toastService.error('Error', 'Failed to load conversation messages');
      }
    });
  }

  createNewChat(showToast: boolean = true) {
    const pid = this.getEffectiveProjectId();
    if (!pid) return;
    const sessionCount = this.chats().length + 1;
    const defaultTitle = `Research Thread #${sessionCount}`;

    this.apiService.createProjectChat(pid, defaultTitle).subscribe({
      next: session => {
        this.chats.update(cs => [session, ...cs]);
        this.selectChat(session.id);
        if (showToast) {
          this.toastService.success('New Chat', 'New research conversation started');
        }
      },
      error: err => {
        console.error('Error creating chat:', err);
        this.toastService.error('Error', 'Failed to create new chat session');
      }
    });
  }

  deleteChat(chatId: string, event: Event) {
    event.stopPropagation();
    const pid = this.getEffectiveProjectId();
    if (!pid) return;

    this.apiService.deleteProjectChat(pid, chatId).subscribe({
      next: () => {
        this.chats.update(cs => cs.filter(c => c.id !== chatId));
        this.toastService.info('Chat Deleted', 'Conversation thread removed');
        const remaining = this.chats();
        if (this.activeChatId() === chatId) {
          if (remaining.length > 0) {
            this.selectChat(remaining[0].id);
          } else {
            this.activeChatId.set(null);
            this.messages.set([]);
          }
        }
      },
      error: err => {
        console.error('Error deleting chat:', err);
        this.toastService.error('Error', 'Failed to delete chat thread');
      }
    });
  }

  onInputKeyDown(event: KeyboardEvent): void {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      this.sendMessage();
    }
  }

  sendPromptChip(prompt: string): void {
    if (!this.authModalService.hasValidCredentials()) {
      this.inputText = prompt;
      this.authModalService.open();
      return;
    }
    this.sendMessage(prompt);
  }

  sendMessage(overrideText?: string) {
    const text = (overrideText !== undefined ? overrideText : this.inputText).trim();
    if (!text || this.isSending()) return;

    // Action Interceptor: Intercept unconfigured state before network dispatch
    if (!this.authModalService.hasValidCredentials()) {
      if (overrideText !== undefined) {
        this.inputText = overrideText;
      }
      this.authModalService.open();
      return;
    }

    const pid = this.getEffectiveProjectId();
    if (!pid) return;

    const cid = this.activeChatId();
    if (!cid) {
      // Auto-create chat session on the fly when no session is active
      const initialTitle = text.length > 30 ? text.substring(0, 30) + '...' : text;
      this.isSending.set(true);
      if (overrideText === undefined) {
        this.inputText = '';
      }
      this.apiService.createProjectChat(pid, initialTitle).subscribe({
        next: session => {
          this.chats.update(cs => [session, ...cs]);
          this.activeChatId.set(session.id);
          this._dispatchMessage(pid, session.id, text, text, overrideText);
        },
        error: err => {
          this.isSending.set(false);
          if (overrideText === undefined) {
            this.inputText = text;
          }
          console.error('Error auto-creating chat session:', err);
          this.toastService.error('Error', 'Failed to initialize chat session');
        }
      });
      return;
    }

    const previousInput = this.inputText;
    if (overrideText === undefined) {
      this.inputText = '';
    }
    this.isSending.set(true);
    this._dispatchMessage(pid, cid, text, previousInput, overrideText);
  }

  private _dispatchMessage(pid: string, cid: string, text: string, previousInput: string, overrideText?: string) {
    // Optimistic user message
    const tempUserMsg: ChatMessage = {
      id: `temp-${Date.now()}`,
      chat_id: cid,
      sender: 'user',
      content: text,
      timestamp: new Date().toISOString()
    };
    this.messages.update(ms => [...ms, tempUserMsg]);
    this.shouldScrollToBottom = true;

    this.apiService.sendChatMessage(pid, cid, text).subscribe({
      next: res => {
        this.isSending.set(false);
        // Replace optimistic placeholder with confirmed response
        this.messages.update(ms => {
          const filtered = ms.filter(m => m.id !== tempUserMsg.id);
          return [...filtered, res.user_message, res.assistant_message];
        });
        // Update chat list summary
        this.chats.update(cs => cs.map(c => {
          if (c.id === cid) {
            return {
              ...c,
              updated_at: new Date().toISOString(),
              message_count: (c.message_count || 0) + 2,
              last_message_preview: res.assistant_message.content.slice(0, 80),
              title: (c.message_count || 0) <= 2 ? (text.slice(0, 30) + (text.length > 30 ? '...' : '')) : c.title
            };
          }
          return c;
        }));
        this.shouldScrollToBottom = true;
      },
      error: err => {
        this.isSending.set(false);
        // Rollback optimistic message
        this.messages.update(ms => ms.filter(m => m.id !== tempUserMsg.id));
        if (overrideText === undefined) {
          this.inputText = previousInput;
        }
        console.error('Error sending message:', err);
        this.toastService.error('Error', 'Failed to get agent response');
      }
    });
  }

  toggleToolTrace(msgId: string) {
    this.expandedToolTraceIds.update(set => {
      const next = new Set(set);
      if (next.has(msgId)) {
        next.delete(msgId);
      } else {
        next.add(msgId);
      }
      return next;
    });
  }

  getActiveChatTitle(): string {
    const active = this.activeChat();
    return active ? active.title : 'Project Chat';
  }

  extractActionChips(msg: ChatMessage): { label: string; prompt: string }[] {
    if (msg.sender !== 'assistant' || !msg.content) return [];
    const chips: { label: string; prompt: string }[] = [];
    const seenDois = new Set<string>();

    // Scan for DOIs in msg.content or citations
    const doiRegex = /\b(10\.\d{4,9}\/[-._;()/:A-Za-z0-9]+)\b/g;
    let match: RegExpExecArray | null;
    while ((match = doiRegex.exec(msg.content)) !== null) {
      const doi = match[1].replace(/[.,;:)]+$/, '');
      if (!seenDois.has(doi)) {
        seenDois.add(doi);
        chips.push({
          label: `⚡ Expand ${doi} for Methodology`,
          prompt: `Expand 1 hop deeper on paper ${doi} for methodology`
        });
        chips.push({
          label: `⚡ Expand ${doi} for Benchmarks`,
          prompt: `Expand 1 hop deeper on paper ${doi} for empirical benchmarks`
        });
        chips.push({
          label: `+ Add ${doi} to Project`,
          prompt: `Add paper ${doi} to project library`
        });
      }
      if (chips.length >= 6) break;
    }

    if (msg.citations && msg.citations.length > 0) {
      for (const cit of msg.citations) {
        if (!seenDois.has(cit.doi)) {
          seenDois.add(cit.doi);
          chips.push({
            label: `⚡ Expand ${cit.doi}`,
            prompt: `Expand 1 hop deeper on paper ${cit.doi}`
          });
        }
        if (chips.length >= 6) break;
      }
    }

    if (chips.length > 0) {
      chips.push({
        label: `📊 Synthesize Current Graph`,
        prompt: `Synthesize current findings from the citation graph`
      });
    }

    return chips;
  }
}
