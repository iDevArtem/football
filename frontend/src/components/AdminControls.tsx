// frontend/src/components/AdminControls.tsx
import React, { useState, useEffect } from "react";
import { PlusCircle, Ban, Users, DollarSign, Send, Settings, Check } from "lucide-react";
import { apiRequest } from "../api/client";

interface AdminControlsProps {
  gameId: string;
  gameStatus: string;
  friendsAllowed: boolean;
  onRefresh: () => void;
}

export function AdminControls({
  gameId,
  gameStatus,
  friendsAllowed,
  onRefresh,
}: AdminControlsProps) {
  const [loading, setLoading] = useState(false);
  const [showPaymentModal, setShowPaymentModal] = useState(false);
  const [showPublishModal, setShowPublishModal] = useState(false);
  const [showCancelModal, setShowCancelModal] = useState(false);
  const [cancelReason, setCancelReason] = useState("");
  const [chats, setChats] = useState<{ chat_id: number; title: string }[]>([]);
  const [selectedChats, setSelectedChats] = useState<number[]>([]);

  useEffect(() => {
    if (showPublishModal) {
      apiRequest<any[]>("/api/admin/chats")
        .then((data) => {
          setChats(data);
          setSelectedChats(data.map((c) => c.chat_id));
        })
        .catch(() => {});
    }
  }, [showPublishModal]);

  const handleToggleFriends = async () => {
    setLoading(true);
    try {
      await apiRequest(`/api/admin/games/${gameId}/friends/toggle`, {
        method: "POST",
        body: JSON.stringify({ allowed: !friendsAllowed }),
      });
      onRefresh();
    } finally {
      setLoading(false);
    }
  };

  const handleStartPayment = async (durationMinutes: number) => {
    setLoading(true);
    try {
      await apiRequest(`/api/admin/games/${gameId}/payment/start`, {
        method: "POST",
        body: JSON.stringify({ duration_minutes: durationMinutes }),
      });
      setShowPaymentModal(false);
      onRefresh();
    } finally {
      setLoading(false);
    }
  };

  const handleCancelGame = async () => {
    setLoading(true);
    try {
      await apiRequest(`/api/admin/games/${gameId}/cancel`, {
        method: "POST",
        body: JSON.stringify({ reason: cancelReason || "Игра отменена организатором" }),
      });
      setShowCancelModal(false);
      onRefresh();
    } finally {
      setLoading(false);
    }
  };

  const handlePublish = async () => {
    if (selectedChats.length === 0) return;
    setLoading(true);
    try {
      await apiRequest(`/api/admin/games/${gameId}/publish`, {
        method: "POST",
        body: JSON.stringify({ chat_ids: selectedChats }),
      });
      setShowPublishModal(false);
      onRefresh();
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="bg-slate-900 border border-emerald-500/30 rounded-3xl p-5 mb-6 shadow-xl">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-bold text-white flex items-center gap-2">
          <Settings className="w-4 h-4 text-emerald-400" />
          Панель организатора
        </h3>
        <span className="text-[10px] px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 font-semibold border border-emerald-500/20">
          Admin UX
        </span>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
        {/* Toggle Friends */}
        <button
          onClick={handleToggleFriends}
          disabled={loading || gameStatus === "cancelled"}
          className={`p-2.5 rounded-xl text-xs font-semibold flex items-center justify-center gap-1.5 border transition ${
            friendsAllowed
              ? "bg-amber-500/10 border-amber-500/30 text-amber-300 hover:bg-amber-500/20"
              : "bg-slate-800 border-slate-700 text-slate-200 hover:bg-slate-700"
          }`}
        >
          <Users className="w-3.5 h-3.5" />
          {friendsAllowed ? "Закрыть друзей" : "Открыть друзей"}
        </button>

        {/* Start Payment */}
        <button
          onClick={() => setShowPaymentModal(true)}
          disabled={loading || gameStatus === "cancelled"}
          className="p-2.5 rounded-xl bg-slate-800 border border-slate-700 text-slate-200 hover:bg-slate-700 text-xs font-semibold flex items-center justify-center gap-1.5 transition"
        >
          <DollarSign className="w-3.5 h-3.5 text-emerald-400" />
          Сбор оплат
        </button>

        {/* Publish */}
        <button
          onClick={() => setShowPublishModal(true)}
          disabled={loading}
          className="p-2.5 rounded-xl bg-slate-800 border border-slate-700 text-slate-200 hover:bg-slate-700 text-xs font-semibold flex items-center justify-center gap-1.5 transition"
        >
          <Send className="w-3.5 h-3.5 text-sky-400" />
          Разослать
        </button>

        {/* Cancel */}
        <button
          onClick={() => setShowCancelModal(true)}
          disabled={loading || gameStatus === "cancelled"}
          className="p-2.5 rounded-xl bg-red-500/10 border border-red-500/20 text-red-400 hover:bg-red-500/20 text-xs font-semibold flex items-center justify-center gap-1.5 transition"
        >
          <Ban className="w-3.5 h-3.5" />
          Отменить
        </button>
      </div>

      {/* Payment Duration Modal */}
      {showPaymentModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-sm">
          <div className="bg-slate-900 border border-slate-800 rounded-3xl max-w-sm w-full p-6 shadow-2xl">
            <h4 className="text-base font-bold text-white mb-2">Запуск сбора оплат</h4>
            <p className="text-xs text-slate-400 mb-4">
              Выберите фактическую длительность матча для автоматического деления аренды поля:
            </p>
            <div className="space-y-2.5 mb-5">
              <button
                onClick={() => handleStartPayment(90)}
                className="w-full p-3 rounded-2xl bg-slate-800 hover:bg-slate-700 text-left border border-slate-700 transition flex items-center justify-between"
              >
                <div>
                  <p className="text-xs font-bold text-white">⏱ 1.5 часа (90 мин)</p>
                  <p className="text-[10px] text-slate-400">Аренда поля: 900 грн</p>
                </div>
                <span className="text-xs font-mono font-bold text-emerald-400">600 грн/ч</span>
              </button>

              <button
                onClick={() => handleStartPayment(120)}
                className="w-full p-3 rounded-2xl bg-slate-800 hover:bg-slate-700 text-left border border-slate-700 transition flex items-center justify-between"
              >
                <div>
                  <p className="text-xs font-bold text-white">⏱ 2.0 часа (120 мин)</p>
                  <p className="text-[10px] text-slate-400">Аренда поля: 1200 грн</p>
                </div>
                <span className="text-xs font-mono font-bold text-emerald-400">600 грн/ч</span>
              </button>
            </div>
            <button
              onClick={() => setShowPaymentModal(false)}
              className="w-full py-2.5 rounded-xl bg-slate-800 text-slate-400 text-xs font-semibold hover:text-white"
            >
              Отмена
            </button>
          </div>
        </div>
      )}

      {/* Publish Modal */}
      {showPublishModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-sm">
          <div className="bg-slate-900 border border-slate-800 rounded-3xl max-w-sm w-full p-6 shadow-2xl">
            <h4 className="text-base font-bold text-white mb-2">Публикация в Telegram-группы</h4>
            <p className="text-xs text-slate-400 mb-4">
              Бот отправит или обновит карточку игры с кнопками в выбранных группах:
            </p>
            <div className="space-y-2 mb-5 max-h-48 overflow-y-auto pr-1">
              {chats.map((c) => {
                const isSelected = selectedChats.includes(c.chat_id);
                return (
                  <div
                    key={c.chat_id}
                    onClick={() => {
                      if (isSelected) {
                        setSelectedChats(selectedChats.filter((id) => id !== c.chat_id));
                      } else {
                        setSelectedChats([...selectedChats, c.chat_id]);
                      }
                    }}
                    className={`p-2.5 rounded-xl border cursor-pointer text-xs flex items-center justify-between transition ${
                      isSelected
                        ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-300"
                        : "bg-slate-800/60 border-slate-700/60 text-slate-300"
                    }`}
                  >
                    <span className="font-medium truncate">{c.title}</span>
                    {isSelected && <Check className="w-3.5 h-3.5 text-emerald-400" />}
                  </div>
                );
              })}
            </div>
            <div className="grid grid-cols-2 gap-2">
              <button
                onClick={() => setShowPublishModal(false)}
                className="py-2.5 rounded-xl bg-slate-800 text-slate-400 text-xs font-semibold"
              >
                Отмена
              </button>
              <button
                onClick={handlePublish}
                disabled={selectedChats.length === 0 || loading}
                className="py-2.5 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-white text-xs font-semibold shadow-md shadow-emerald-500/20"
              >
                Отправить
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Cancel Modal */}
      {showCancelModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-sm">
          <div className="bg-slate-900 border border-slate-800 rounded-3xl max-w-sm w-full p-6 shadow-2xl">
            <h4 className="text-base font-bold text-white mb-2">Отмена матча</h4>
            <p className="text-xs text-slate-400 mb-3">Укажите причину для игроков:</p>
            <input
              type="text"
              value={cancelReason}
              onChange={(e) => setCancelReason(e.target.value)}
              placeholder="Например, Погодные условия / ремонт зала"
              className="w-full bg-slate-800 border border-slate-700 rounded-xl px-3 py-2 text-xs text-white mb-4"
            />
            <div className="grid grid-cols-2 gap-2">
              <button
                onClick={() => setShowCancelModal(false)}
                className="py-2.5 rounded-xl bg-slate-800 text-slate-400 text-xs font-semibold"
              >
                Назад
              </button>
              <button
                onClick={handleCancelGame}
                disabled={loading}
                className="py-2.5 rounded-xl bg-red-500 hover:bg-red-400 text-white text-xs font-semibold"
              >
                Подтвердить отмену
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
