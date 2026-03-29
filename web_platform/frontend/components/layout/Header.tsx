/**
 * Header Component
 *
 * Top navigation bar with:
 * - App logo/title
 * - Profile dropdown (doctor name, logout)
 * - Settings button
 */

"use client";

import { useState, Fragment } from "react";
import { useRouter } from "next/navigation";
import { Menu, Transition } from "@headlessui/react";
import { Settings, LogOut, User, ChevronDown } from "lucide-react";
import { useAuthStore } from "../../lib/store/authStore";
import { logoutDoctor } from "../../lib/api/auth";
import { Avatar } from "../ui/Avatar";
import { classNames } from "../../lib/utils";

export function Header() {
  const router = useRouter();
  const { doctor, clearAuth } = useAuthStore();
  const [isLoggingOut, setIsLoggingOut] = useState(false);

  const handleLogout = async () => {
    setIsLoggingOut(true);
    try {
      await logoutDoctor();
    } catch (error) {
      console.error("Logout error:", error);
    } finally {
      clearAuth();
      router.push("/login");
    }
  };

  const handleSettings = () => {
    router.push("/app/settings");
  };

  return (
    <header className="h-14 bg-zinc-900/80 backdrop-blur-sm border-b border-zinc-800/60 flex items-center justify-between px-5 flex-shrink-0">
      {/* Left: Logo/Title */}
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-2">
          <div className="h-7 w-7 rounded-lg bg-gradient-to-br from-blue-500 to-cyan-500 flex items-center justify-center shadow-md shadow-blue-500/20">
            <span className="text-white text-xs font-bold">M</span>
          </div>
          <span className="text-lg font-bold bg-gradient-to-r from-blue-400 to-cyan-400 bg-clip-text text-transparent tracking-tight">
            MedRAX
          </span>
        </div>
        <div className="h-4 w-px bg-zinc-700" />
        <div className="text-xs text-zinc-500 font-medium">Medical Reasoning Agent</div>
      </div>

      {/* Right: Profile + Settings */}
      <div className="flex items-center gap-2">
        {/* Settings Button */}
        <button
          onClick={handleSettings}
          className="p-2 text-zinc-400 hover:text-white hover:bg-zinc-800 rounded-lg transition-all duration-150"
          title="Settings"
        >
          <Settings className="h-4.5 w-4.5" />
        </button>

        {/* Profile Dropdown */}
        <Menu as="div" className="relative">
          <Menu.Button className="flex items-center gap-2 px-3 py-1.5 text-zinc-300 hover:text-white hover:bg-zinc-800 rounded-lg transition-all duration-150">
            <Avatar name={doctor?.name || null} size="sm" />
            <span className="text-sm font-medium">{doctor?.name || "User"}</span>
            <ChevronDown className="h-3.5 w-3.5 text-zinc-500" />
          </Menu.Button>

          <Transition
            as={Fragment}
            enter="transition ease-out duration-100"
            enterFrom="transform opacity-0 scale-95"
            enterTo="transform opacity-100 scale-100"
            leave="transition ease-in duration-75"
            leaveFrom="transform opacity-100 scale-100"
            leaveTo="transform opacity-0 scale-95"
          >
            <Menu.Items className="absolute right-0 mt-2 w-52 origin-top-right bg-zinc-900 border border-zinc-800/80 rounded-xl shadow-2xl shadow-black/40 focus:outline-none z-50 overflow-hidden">
              <div className="py-1">
                <Menu.Item>
                  {({ active }) => (
                    <button
                      onClick={handleSettings}
                      className={classNames(
                        "w-full flex items-center px-3.5 py-2 text-sm gap-3",
                        active ? "bg-zinc-800/80 text-white" : "text-zinc-300"
                      )}
                    >
                      <User className="h-4 w-4 shrink-0" />
                      Profile Settings
                    </button>
                  )}
                </Menu.Item>

                <div className="border-t border-zinc-800/60 my-1" />

                <Menu.Item>
                  {({ active }) => (
                    <button
                      onClick={handleLogout}
                      disabled={isLoggingOut}
                      className={classNames(
                        "w-full flex items-center px-3.5 py-2 text-sm gap-3",
                        active ? "bg-zinc-800/80 text-red-400" : "text-red-500",
                        isLoggingOut && "opacity-50 cursor-not-allowed"
                      )}
                    >
                      <LogOut className="h-4 w-4 shrink-0" />
                      {isLoggingOut ? "Logging out..." : "Logout"}
                    </button>
                  )}
                </Menu.Item>
              </div>
            </Menu.Items>
          </Transition>
        </Menu>
      </div>
    </header>
  );
}
