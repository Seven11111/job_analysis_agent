import { BellRing, Bot, BriefcaseBusiness, FileSearch, Home, UserRound } from "lucide-react";
import { NavLink, Outlet } from "react-router-dom";

const navigation = [
  { to: "/", label: "工作台", icon: Home, end: true },
  { to: "/jobs/search", label: "岗位搜索", icon: FileSearch },
  { to: "/jobs/subscriptions", label: "岗位查新", icon: BellRing },
  { to: "/jobs/manage", label: "岗位管理", icon: BriefcaseBusiness },
  { to: "/profile", label: "个人画像", icon: UserRound },
  { to: "/agent", label: "求职 Agent", icon: Bot },
];

export function AppLayout() {
  return (
    <div className="min-h-screen bg-mist text-ink">
      <aside className="fixed inset-y-0 left-0 z-10 w-64 border-r border-slate-200 bg-white/95 px-5 py-8">
        <div className="mb-12 px-3">
          <div className="text-xl font-bold tracking-tight">求职研究工作台</div>
          <div className="mt-1 text-xs text-slate-400">Job Analysis Agent</div>
        </div>
        <nav className="space-y-2">
          {navigation.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                `flex items-center gap-3 rounded-xl px-4 py-3 text-sm font-medium transition ${
                  isActive ? "bg-blue-50 text-brand" : "text-slate-600 hover:bg-slate-50"
                }`
              }
            >
              <Icon size={19} strokeWidth={1.8} />
              {label}
            </NavLink>
          ))}
        </nav>
      </aside>
      <main className="ml-64 min-h-screen min-w-0 p-8 lg:p-12">
        <Outlet />
      </main>
    </div>
  );
}
