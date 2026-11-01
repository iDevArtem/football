// frontend/src/pages/PublicSchedule.tsx
import React, { useEffect, useState } from "react";
import { Calendar, Clock, MapPin, Users, MessageCircle, ExternalLink, ChevronRight } from "lucide-react";
import { apiRequest } from "../api/client";
import { RosterList } from "../components/RosterList";

interface GameSummary {
  id: string;
  title: string;
  start_at: string;
  status: string;
  status_label: string;
  max_players: number;
  confirmed_count: number;
  reserve_count: number;
  format_description: string;
  friends_allowed: boolean;
  price: number;
  duration_minutes: number;
  linked_chats: { chat_id: number; title: string }[];
}

export function PublicSchedule({ onGoToCabinet }: { onGoToCabinet: (gameId?: string) => void }) {
  const [games, setGames] = useState<GameSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeGameDetail, setActiveGameDetail] = useState<any | null>(null);

  useEffect(() => {
    apiRequest<GameSummary[]>("/api/games")
      .then((data) => {
        setGames(data);
        if (data.length > 0) {
          loadGameDetail(data[0].id);
        }
      })
      .finally(() => setLoading(false));
  }, []);

  const loadGameDetail = async (id: string) => {
    try {
      const detail = await apiRequest(`/api/games/${id}`);
      setActiveGameDetail(detail);
    } catch (e) {}
  };

  const formatDate = (isoString: string) => {
    if (!isoString) return "";
    const d = new Date(isoString);
    return d.toLocaleDateString("ru-RU", { weekday: "short", day: "numeric", month: "long" });
  };

  const formatTime = (isoString: string) => {
    if (!isoString) return "";
    const d = new Date(isoString);
    return d.toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" });
  };

  return (
    <div className="max-w-4xl mx-auto px-4 py-6 space-y-8">
      {/* Hero Banner */}
      <div className="relative rounded-3xl p-6 sm:p-8 bg-gradient-to-r from-emerald-900/60 via-slate-900 to-slate-900 border border-emerald-500/20 shadow-2xl overflow-hidden">
        <div className="absolute top-0 right-0 w-64 h-64 bg-emerald-500/10 rounded-full blur-3xl pointer-events-none" />
        <div className="relative z-10 max-w-xl">
          <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-emerald-500/10 text-emerald-400 text-xs font-semibold border border-emerald-500/20 mb-3">
            ⚽ Регулярные футбольные матчи 5х5
          </span>
          <h2 className="text-2xl sm:text-3xl font-extrabold text-white tracking-tight mb-2">
            Афиша и расписание сборов
          </h2>
          <p className="text-sm text-slate-300 leading-relaxed mb-6">
            Записывайтесь на матчи, следите за основным составом и очередью резерва онлайн.
          </p>
          <div className="flex flex-wrap items-center gap-3">
            <button
              onClick={() => onGoToCabinet()}
              className="px-5 py-2.5 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-white font-bold text-xs shadow-lg shadow-emerald-500/20 transition flex items-center gap-2"
            >
              Войти в кабинет игрока
              <ChevronRight className="w-4 h-4" />
            </button>
            <a
              href="https://t.me/PlayGame_robot"
              target="_blank"
              rel="noreferrer"
              className="px-4 py-2.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-semibold transition flex items-center gap-2"
            >
              <MessageCircle className="w-4 h-4 text-sky-400" />
              Telegram бот
            </a>
          </div>
        </div>
      </div>

      {/* Match Schedule */}
      <div>
        <h3 className="text-lg font-bold text-white mb-4 flex items-center gap-2">
          <Calendar className="w-5 h-5 text-emerald-400" />
          Ближайшие матчи
        </h3>

        {loading ? (
          <div className="flex items-center justify-center p-12 text-slate-400 text-xs gap-2">
            <div className="w-5 h-5 border-2 border-emerald-500 border-t-transparent rounded-full animate-spin" />
            Загружаем актуальные матчи...
          </div>
        ) : games.length === 0 ? (
          <div className="p-8 rounded-3xl bg-slate-800/40 border border-slate-800 text-center">
            <p className="text-sm text-slate-400">На данный момент нет активных сборов.</p>
            <p className="text-xs text-slate-500 mt-1">Организатор опубликует следующий матч в ближайшее время.</p>
          </div>
        ) : (
          <div className="space-y-6">
            {games.map((g) => {
              const pct = Math.min(100, Math.round((g.confirmed_count / g.max_players) * 100));
              const isSelected = activeGameDetail?.id === g.id;

              return (
                <div
                  key={g.id}
                  className={`rounded-3xl p-6 border transition-all ${
                    isSelected
                      ? "bg-slate-900 border-emerald-500/40 shadow-xl shadow-emerald-500/5"
                      : "bg-slate-900/60 border-slate-800 hover:border-slate-700/80"
                  }`}
                >
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-4">
                    <div>
                      <div className="flex items-center gap-2 mb-1.5">
                        <span
                          className={`text-[10px] px-2.5 py-0.5 rounded-full font-bold uppercase tracking-wider ${
                            g.status === "registration_open" || g.status === "friends_allowed"
                              ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
                              : g.status === "payment_collection"
                              ? "bg-sky-500/10 text-sky-400 border border-sky-500/20"
                              : "bg-slate-700 text-slate-300"
                          }`}
                        >
                          {g.status_label}
                        </span>
                        <span className="text-xs font-semibold text-emerald-400">
                          {g.format_description}
                        </span>
                      </div>
                      <h4 className="text-lg font-bold text-white">{g.title}</h4>
                    </div>

                    <div className="flex items-center gap-4 text-xs font-medium text-slate-300">
                      <div className="flex items-center gap-1.5">
                        <Calendar className="w-4 h-4 text-slate-400" />
                        <span>{formatDate(g.start_at)}</span>
                      </div>
                      <div className="flex items-center gap-1.5">
                        <Clock className="w-4 h-4 text-slate-400" />
                        <span>{formatTime(g.start_at)}</span>
                      </div>
                    </div>
                  </div>

                  {/* Progress Bar */}
                  <div className="mb-4">
                    <div className="flex items-center justify-between text-xs mb-1.5">
                      <span className="text-slate-400">
                        Основа: <strong className="text-slate-200">{g.confirmed_count}</strong> / {g.max_players}
                      </span>
                      {g.reserve_count > 0 && (
                        <span className="text-amber-400 font-medium">
                          Резерв: {g.reserve_count} чел
                        </span>
                      )}
                    </div>
                    <div className="w-full h-2.5 rounded-full bg-slate-800 overflow-hidden">
                      <div
                        className="h-full bg-gradient-to-r from-emerald-500 to-teal-400 rounded-full transition-all duration-500"
                        style={{ width: `${pct}%` }}
                      />
                    </div>
                  </div>

                  {/* Action buttons & Links */}
                  <div className="flex flex-wrap items-center justify-between gap-3 pt-3 border-t border-slate-800">
                    <div className="flex items-center gap-2">
                      {g.linked_chats.map((c) => (
                        <span
                          key={c.chat_id}
                          className="text-[11px] px-2.5 py-1 rounded-lg bg-slate-800 text-slate-400 flex items-center gap-1.5"
                        >
                          <MessageCircle className="w-3 h-3 text-sky-400" />
                          {c.title}
                        </span>
                      ))}
                    </div>

                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => {
                          loadGameDetail(g.id);
                        }}
                        className="px-3.5 py-1.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-medium transition"
                      >
                        {isSelected ? "Состав открыт" : "Посмотреть состав"}
                      </button>
                      <button
                        onClick={() => onGoToCabinet(g.id)}
                        className="px-4 py-1.5 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-white text-xs font-bold transition shadow-sm"
                      >
                        Записаться ⚽
                      </button>
                    </div>
                  </div>

                  {/* Expanded Roster if selected */}
                  {isSelected && activeGameDetail?.participants && (
                    <div className="mt-6 pt-6 border-t border-slate-800 animate-fade-in">
                      <RosterList
                        participants={activeGameDetail.participants}
                        maxPlayers={g.max_players}
                        showPayments={g.status === "payment_collection"}
                      />
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
