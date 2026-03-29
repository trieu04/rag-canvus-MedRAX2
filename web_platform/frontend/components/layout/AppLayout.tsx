/**
 * AppLayout Component
 *
 * Main application layout with:
 * - Header at top
 * - Left sidebar (patients/chats)
 * - Center content (chat interface)
 * - Right panel (tool outputs - conditionally shown)
 */

"use client";

import { AuthGuard } from "../auth/AuthGuard";
import { Header } from "./Header";
import { Sidebar } from "./Sidebar";
import { ChatInterface } from "../chat/ChatInterface";

export function AppLayout() {
  return (
    <AuthGuard>
      <div className="h-screen w-screen flex flex-col bg-zinc-950 overflow-hidden" style={{ backgroundImage: "radial-gradient(ellipse 80% 50% at 50% -20%, rgba(59,130,246,0.05) 0%, transparent 60%)" }}>
        {/* Header */}
        <Header />

        {/* Main Content: 3-column layout */}
        <div className="flex-1 flex overflow-hidden min-h-0">
          {/* Left Sidebar: Patients & Chats */}
          <Sidebar />

          {/* Center: Chat Interface */}
          <main className="flex-1 flex flex-col overflow-hidden min-h-0">
            <ChatInterface />
          </main>

        </div>
      </div>
    </AuthGuard>
  );
}
