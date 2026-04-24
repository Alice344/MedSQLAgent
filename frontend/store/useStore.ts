import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import type { ChatMessage, PendingTask } from '@/lib/types';

interface AppState {
  connectionId: string | null;
  connectedServer: string;
  chatMessages: ChatMessage[];
  pendingTask: PendingTask | null;
  lastTaskId: string | null;
  lastSqlQuery: string;

  setConnection: (id: string, server: string) => void;
  disconnect: () => void;
  addMessage: (msg: Omit<ChatMessage, 'id'>) => void;
  clearMessages: () => void;
  setPendingTask: (task: PendingTask | null) => void;
  setLastTaskId: (id: string) => void;
  setLastSqlQuery: (sql: string) => void;
}

let _msgId = 0;
const nextId = () => String(++_msgId);

export const useAppStore = create<AppState>()(
  persist(
    (set) => ({
      connectionId: null,
      connectedServer: '',
      chatMessages: [],
      pendingTask: null,
      lastTaskId: null,
      lastSqlQuery: '',

      setConnection: (id, server) =>
        set({ connectionId: id, connectedServer: server }),

      disconnect: () =>
        set({
          connectionId: null,
          connectedServer: '',
          chatMessages: [],
          pendingTask: null,
          lastTaskId: null,
          lastSqlQuery: '',
        }),

      addMessage: (msg) =>
        set((s) => ({
          chatMessages: [...s.chatMessages, { ...msg, id: nextId() }],
        })),

      clearMessages: () => set({ chatMessages: [], pendingTask: null }),

      setPendingTask: (task) => set({ pendingTask: task }),

      setLastTaskId: (id) => set({ lastTaskId: id }),

      setLastSqlQuery: (sql) => set({ lastSqlQuery: sql }),
    }),
    {
      name: 'medsql-store',
      partialize: (s) => ({
        connectionId: s.connectionId,
        connectedServer: s.connectedServer,
        lastSqlQuery: s.lastSqlQuery,
      }),
    },
  ),
);
