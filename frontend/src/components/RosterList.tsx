// frontend/src/components/RosterList.tsx
import React from "react";
import { User, Users, CheckCircle2, Clock, XCircle } from "lucide-react";

export interface Participant {
  id: string;
  telegram_id?: number | null;
  display_name: string;
  type: "player" | "friend" | "guest";
  status: "confirmed" | "reserve" | "declined" | "removed";
  position: number;
  added_by_telegram_id?: number | null;
  payment_status: "paid" | "not_played" | "unpaid" | "pending";
  payment_amount?: number | null;
  confirmed_by_user?: boolean;
  confirmed_by_admin?: boolean;
}

interface RosterListProps {
  participants: Participant[];
  maxPlayers: number;
  showPayments?: boolean;
  onParticipantAction?: (p: Participant, action: string) => void;
  isAdmin?: boolean;
}

export function RosterList({
  participants,
  maxPlayers = 15,
  showPayments = false,
  onParticipantAction,
  isAdmin = false,
}: RosterListProps) {
  const confirmed = participants.filter((p) => p.status === "confirmed");
  const reserve = participants.filter((p) => p.status === "reserve");

  return (
    <div className="space-y-6">
      {/* Confirmed Roster */}
      <div className="bg-slate-800/40 rounded-2xl p-4 border border-slate-800">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-bold text-slate-200 flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-emerald-400"></span>
            Основной состав ({confirmed.length}/{maxPlayers})
          </h3>
          <span className="text-xs text-slate-400 font-medium">№ 1 — {maxPlayers}</span>
        </div>

        {confirmed.length === 0 ? (
          <p className="text-xs text-slate-500 py-3 text-center">Пока никто не записался. Будь первым!</p>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {confirmed.map((p, idx) => (
              <div
                key={p.id}
                className="flex items-center justify-between p-2.5 rounded-xl bg-slate-900/60 border border-slate-800/80 hover:border-slate-700/80 transition"
              >
                <div className="flex items-center gap-2.5 overflow-hidden">
                  <span className="w-5 h-5 rounded-md bg-emerald-500/10 text-emerald-400 font-mono text-xs flex items-center justify-center font-bold">
                    {idx + 1}
                  </span>
                  <div className="truncate">
                    <p className="text-xs font-semibold text-slate-200 truncate flex items-center gap-1.5">
                      {p.display_name}
                      {(p.type === "friend" || p.type === "guest") && (
                        <span className="text-[10px] px-1.5 py-0.2 rounded bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 flex items-center gap-0.5">
                          <span>👥</span> друг
                        </span>
                      )}
                    </p>
                  </div>
                </div>

                {/* Payment badge or Admin actions */}
                <div className="flex items-center gap-1.5 shrink-0">
                  {showPayments && (
                    <span
                      className={`text-[10px] px-2 py-0.5 rounded-full font-medium flex items-center gap-1 ${
                        p.payment_status === "paid"
                          ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
                          : p.payment_status === "not_played"
                          ? "bg-slate-700 text-slate-400"
                          : "bg-amber-500/10 text-amber-400 border border-amber-500/20"
                      }`}
                    >
                      {p.payment_status === "paid" && <CheckCircle2 className="w-2.5 h-2.5" />}
                      {p.payment_status === "paid"
                        ? "Оплачено"
                        : p.payment_status === "not_played"
                        ? "Не играл"
                        : "Ожидает"}
                    </span>
                  )}

                  {isAdmin && onParticipantAction && (
                    <button
                      onClick={() => onParticipantAction(p, "toggle_reserve")}
                      title="Переместить в резерв"
                      className="text-[10px] p-1 text-slate-400 hover:text-amber-400"
                    >
                      ⬇
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Reserve Roster */}
      {reserve.length > 0 && (
        <div className="bg-slate-800/40 rounded-2xl p-4 border border-slate-800">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-bold text-slate-300 flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-amber-400"></span>
              Лист ожидания / Резерв ({reserve.length})
            </h3>
            <span className="text-xs text-slate-500">Авто-перевод при освобождении мест</span>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {reserve.map((p, idx) => (
              <div
                key={p.id}
                className="flex items-center justify-between p-2.5 rounded-xl bg-slate-900/40 border border-slate-800/60"
              >
                <div className="flex items-center gap-2.5 overflow-hidden">
                  <span className="w-5 h-5 rounded-md bg-amber-500/10 text-amber-400 font-mono text-xs flex items-center justify-center font-bold">
                    {idx + 1}
                  </span>
                  <div className="truncate">
                    <p className="text-xs font-semibold text-slate-300 truncate flex items-center gap-1.5">
                      {p.display_name}
                      {(p.type === "friend" || p.type === "guest") && (
                        <span className="text-[10px] px-1.5 py-0.2 rounded bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 flex items-center gap-0.5">
                          <span>👥</span> друг
                        </span>
                      )}
                    </p>
                  </div>
                </div>

                {isAdmin && onParticipantAction && (
                  <button
                    onClick={() => onParticipantAction(p, "toggle_confirmed")}
                    title="Переместить в основу"
                    className="text-[10px] p-1 text-slate-400 hover:text-emerald-400"
                  >
                    ⬆
                  </button>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
