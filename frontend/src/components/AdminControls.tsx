// frontend/src/components/AdminControls.tsx
import React, { useState, useEffect } from "react";
import { Play, UserPlus, Ban, Users, DollarSign, Send, Settings, Check } from "lucide-react";
import { apiRequest } from "../api/client";

interface AdminControlsProps {
  gameId: string;
  gameStatus: string;
  friendsAllowed: boolean;
  initialCardNumber?: string;
  initialRecipient?: string;
  onRefresh: () => void;
}

export function AdminControls({
  gameId,
  gameStatus,
  friendsAllowed,
  initialCardNumber = "",
  initialRecipient = "",
  onRefresh,
}: AdminControlsProps) {
  const [loading, setLoading] = useState(false);
  const [showPaymentModal, setShowPaymentModal] = useState(false);
  const [showPublishModal, setShowPublishModal] = useState(false);
  const [showCancelModal, setShowCancelModal] = useState(false);
  const [showGuestModal, setShowGuestModal] = useState(false);
  const [guestName, setGuestName] = useState("");
  const [friendError, setFriendError] = useState<string | null>(null);
  const [cancelReason, setCancelReason] = useState("");
  const [chats, setChats] = useState<{ chat_id: number; title: string }[]>([]);
  const [selectedChats, setSelectedChats] = useState<number[]>([]);

  // Payment modal state
  const [durationMinutes, setDurationMinutes] = useState(90);
  const [cardNumber, setCardNumber] = useState(initialCardNumber);
  const [cardRecipient, setCardRecipient] = useState(initialRecipient);

  useEffect(() => {
    if (initialCardNumber) setCardNumber(initialCardNumber);
    if (initialRecipient) setCardRecipient(initialRecipient);
  }, [initialCardNumber, initialRecipient]);

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

  const handleStartGame = async () => {
    setLoading(true);
    try {
      await apiRequest(`/api/admin/games/${gameId}/start`, {
        method: "POST",
      });
      onRefresh();
    } finally {
      setLoading(false);
    }
  };

  const handleAddFriend = async () => {
    if (!guestName.trim()) return;
    setLoading(true);
    setFriendError(null);
    try {
      await apiRequest(`/api/games/${gameId}/friends`, {
        method: "POST",
        body: JSON.stringify({ friend_name: guestName.trim() }),
      });
      setGuestName("");
      setShowGuestModal(false);
      onRefresh();
    } catch (err: any) {
      setFriendError(err.message || "Не удалось добавить друга");
    } finally {
      setLoading(false);
    }
  };

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

  const handleStartPayment = async () => {
    setLoading(true);
    try {
      await apiRequest(`/api/admin/games/${gameId}/payment/start`, {
        method: "POST",
        body: JSON.stringify({
          duration_minutes: durationMinutes,
          card_number: cardNumber.trim(),
          card_recipient: cardRecipient.trim(),
        }),
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

  const canStartGame =
    gameStatus !== "game_started" &&
    gameStatus !== "payment_collection" &&
    gameStatus !== "closed" &&
    gameStatus !== "cancelled";

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

      <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
        {/* Start Game Button (if not started) */}
        {canStartGame && (
          <button
            onClick={handleStartGame}
            disabled={loading}
            className="p-2.5 rounded-xl bg-teal-500/20 border border-teal-500/40 text-teal-300 hover:bg-teal-500/30 text-xs font-semibold flex items-center justify-center gap-1.5 transition"
          >
            <Play className="w-3.5 h-3.5" />
            Начать игру
          </button>
        )}

        {/* Add Friend Button */}
        <button
          onClick={() => {
            setFriendError(null);
            setShowGuestModal(true);
          }}
          disabled={loading || !friendsAllowed || gameStatus === "cancelled" || gameStatus === "closed"}
          className={`p-2.5 rounded-xl border text-xs font-semibold flex items-center justify-center gap-1.5 transition ${
            friendsAllowed
              ? "bg-slate-800 border-slate-700 text-slate-200 hover:bg-slate-700"
              : "bg-slate-900 border-slate-800 text-slate-500 cursor-not-allowed"
          }`}
          title={!friendsAllowed ? "Сначала откройте друзей" : undefined}
        >
          <UserPlus className={`w-3.5 h-3.5 ${friendsAllowed ? "text-amber-400" : "text-slate-600"}`} />
          + Друг
        </button>

        {/* Toggle Friends */}
        {gameStatus !== "game_started" && gameStatus !== "payment_collection" && (
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
        )}

        {/* Start Payment */}
        <button
          onClick={() => setShowPaymentModal(true)}
          disabled={loading || gameStatus === "cancelled" || gameStatus === "closed"}
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

      {/* Friend Modal */}
      {showGuestModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-sm">
          <div className="bg-slate-900 border border-slate-800 rounded-3xl max-w-sm w-full p-6 shadow-2xl">
            <h4 className="text-base font-bold text-white mb-2">Добавить друга</h4>
            <p className="text-xs text-slate-400 mb-4">
              Введите имя друга для добавления в состав:
            </p>
            {friendError && (
              <div className="mb-4 p-2.5 rounded-xl bg-red-500/10 border border-red-500/20 text-red-400 text-xs">
                {friendError}
              </div>
            )}
            <div className="space-y-3 mb-5">
              <input
                type="text"
                placeholder="Имя друга (например, Игорь)"
                value={guestName}
                onChange={(e) => setGuestName(e.target.value)}
                className="w-full px-3.5 py-2.5 rounded-xl bg-slate-950 border border-slate-800 text-white text-xs placeholder:text-slate-500 focus:outline-none focus:border-emerald-500"
                autoFocus
              />
            </div>
            <div className="grid grid-cols-2 gap-2">
              <button
                onClick={() => {
                  setShowGuestModal(false);
                  setFriendError(null);
                }}
                className="py-2.5 rounded-xl bg-slate-800 text-slate-400 text-xs font-semibold hover:text-white"
              >
                Отмена
              </button>
              <button
                onClick={handleAddFriend}
                disabled={loading || !guestName.trim()}
                className="py-2.5 rounded-xl bg-emerald-500 hover:bg-emerald-400 disabled:opacity-50 text-white text-xs font-bold transition"
              >
                {loading ? "Добавляем..." : "Добавить"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Payment Modal with Card Details */}
      {showPaymentModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-sm">
          <div className="bg-slate-900 border border-slate-800 rounded-3xl max-w-sm w-full p-6 shadow-2xl">
            <h4 className="text-base font-bold text-white mb-2">Запуск сбора оплат</h4>
            <p className="text-xs text-slate-400 mb-4">
              Выберите фактическую длительность и проверьте реквизиты карты:
            </p>

            {/* Duration Selector */}
            <div className="grid grid-cols-2 gap-2 mb-4">
              <button
                type="button"
                onClick={() => setDurationMinutes(90)}
                className={`p-3 rounded-2xl border text-left transition ${
                  durationMinutes === 90
                    ? "bg-emerald-500/10 border-emerald-500/50 text-white"
                    : "bg-slate-800 border-slate-700 text-slate-400"
                }`}
              >
                <p className="text-xs font-bold">1.5 часа (90 мин)</p>
                <p className="text-[10px] text-emerald-400 mt-0.5">900 грн</p>
              </button>

              <button
                type="button"
                onClick={() => setDurationMinutes(120)}
                className={`p-3 rounded-2xl border text-left transition ${
                  durationMinutes === 120
                    ? "bg-emerald-500/10 border-emerald-500/50 text-white"
                    : "bg-slate-800 border-slate-700 text-slate-400"
                }`}
              >
                <p className="text-xs font-bold">2.0 часа (120 мин)</p>
                <p className="text-[10px] text-emerald-400 mt-0.5">1200 грн</p>
              </button>
            </div>

            {/* Card Inputs */}
            <div className="space-y-3 mb-5">
              <div>
                <label className="text-[11px] font-semibold text-slate-300 block mb-1">
                  Номер банковской карты:
                </label>
                <input
                  type="text"
                  placeholder="4441 1111 2222 3333"
                  value={cardNumber}
                  onChange={(e) => setCardNumber(e.target.value)}
                  className="w-full px-3.5 py-2.5 rounded-xl bg-slate-950 border border-slate-800 text-white text-xs font-mono placeholder:text-slate-500 focus:outline-none focus:border-emerald-500"
                />
              </div>

              <div>
                <label className="text-[11px] font-semibold text-slate-300 block mb-1">
                  Имя получателя (опционально):
                </label>
                <input
                  type="text"
                  placeholder="Иван И."
                  value={cardRecipient}
                  onChange={(e) => setCardRecipient(e.target.value)}
                  className="w-full px-3.5 py-2.5 rounded-xl bg-slate-950 border border-slate-800 text-white text-xs placeholder:text-slate-500 focus:outline-none focus:border-emerald-500"
                />
              </div>
            </div>

            <div className="grid grid-cols-2 gap-2">
              <button
                onClick={() => setShowPaymentModal(false)}
                className="py-2.5 rounded-xl bg-slate-800 text-slate-400 text-xs font-semibold hover:text-white"
              >
                Отмена
              </button>
              <button
                onClick={handleStartPayment}
                disabled={loading}
                className="py-2.5 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-white text-xs font-bold shadow-lg shadow-emerald-500/20 active:scale-95 transition"
              >
                {loading ? "Запуск..." : "Запустить сбор"}
              </button>
            </div>
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
                disabled={loading || selectedChats.length === 0}
                className="py-2.5 rounded-xl bg-emerald-500 hover:bg-emerald-400 disabled:opacity-50 text-white text-xs font-bold shadow-lg shadow-emerald-500/20 active:scale-95 transition"
              >
                Опубликовать
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Cancel Modal */}
      {showCancelModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-sm">
          <div className="bg-slate-900 border border-slate-800 rounded-3xl max-w-sm w-full p-6 shadow-2xl">
            <h4 className="text-base font-bold text-white mb-2">Отмена игры</h4>
            <p className="text-xs text-slate-400 mb-4">
              Укажите причину отмены игры (будет видно в сообщении группы):
            </p>
            <input
              type="text"
              placeholder="Причина (например, плохая погода)"
              value={cancelReason}
              onChange={(e) => setCancelReason(e.target.value)}
              className="w-full px-3.5 py-2.5 rounded-xl bg-slate-950 border border-slate-800 text-white text-xs placeholder:text-slate-500 focus:outline-none focus:border-red-500 mb-4"
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
                className="py-2.5 rounded-xl bg-red-500 hover:bg-red-400 text-white text-xs font-bold"
              >
                Подтвердить
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
